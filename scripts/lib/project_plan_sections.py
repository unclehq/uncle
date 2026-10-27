#!/usr/bin/env python3
"""A project plan written in sections by parallel workers, then assembled by the driver.

One model writes the whole plan in a single decode stream (about 6k tokens, roughly
190 s on a local model).  Splitting it by section only helps if the sections do not have to
wait for each other, and they were: every worker read the *full text* of the one before it,
so the build ran core (48 s), then the tests worker (47 s), then traceability (16 s).  What
each of them actually needed from the earlier text was small: component and step names, the
files each step owns, decision and restriction IDs, which requirement maps to which component.

So the first worker writes only that, as a short outline (about 45 lines, ~12 s), and everything
else is written at the same time against it:

    phase 1  outline                       stack, components, steps (Owns/Depends), decision and
                                           restriction IDs, tests, requirement -> component map
    phase 2  design steps decisions restrictions behaviors invariants tests commands closing
             1-5 | 12 + .gitignore | Decision Record | Restriction Inventory | 6 8 9 11 | 7 | 10 |
             verification commands | 14 15
    driver   section 13, the traceability table, is built from `<!-- trace K: R-1=ID,ID -->` lines
             each worker ends its file with, plus the outline's component map; a plan whose workers
             left those out falls back to one traceability worker that reads everything

The workers share the investigation prompt as an identical prefix (so the server prefills it
once) and differ only in the contract appended after it.  What keeps the sections coherent is
not trust but ownership: the outline is binding, each worker may write only its own headings,
ID namespaces are fixed per worker, and `assemble` refuses a plan with a missing, duplicated or
unknown section.  The driver falls back to the single-pass plan whenever any of that fails, so
the split costs time, never correctness.  On by default for every runner;
WORKFLOW_PROJECT_PLAN_SECTIONS=0 turns it off.

usage:
  project_plan_sections.py phases
  project_plan_sections.py prompt NAME DIRECTORY BASE_PROMPT OUTPUT_PROMPT [--json]
  project_plan_sections.py render NAME PACKET.json SECTION.md   (a worker's schema-checked packet -> its section file)
  project_plan_sections.py trace-ready DIRECTORY     (exit 0 when section 13 can be built without a model)
  project_plan_sections.py recover WORKER_LOG SECTION_FILE   (a worker that answered in chat: take the answer)
  project_plan_sections.py assemble DIRECTORY OUTPUT
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from worker_schemas import SECTION_KIND

TITLES = {
    1: 'Architecture', 2: 'Authoritative state', 3: 'Domain model', 4: 'Components and responsibilities',
    5: 'Data flow', 6: 'Observable behaviors', 7: 'Domain invariants', 8: 'Failure handling',
    9: 'Concurrency model', 10: 'Automated-test strategy', 11: 'Manual-test strategy',
    12: 'Implementation order', 13: 'Requirement traceability', 14: 'Explicit non-goals',
    15: 'Risks and unresolved questions',
}
EXTRA = ('Decision Record', 'Restriction Inventory')
GROUPS = 'Parallel verification groups'      # optional; must precede the commands, which end the narrative
COMMANDS = 'Verification commands'
OUTLINE_HEADINGS = ('Stack', 'Components', 'Steps', 'Decisions', 'Restrictions', 'Tests', 'Requirement map')

WORKERS = {
    'outline': {'sections': (), 'extra': (), 'commands': False},
    'design': {'sections': (1, 2, 3, 4, 5), 'extra': (), 'commands': False},
    'steps': {'sections': (12,), 'extra': (), 'commands': False},
    'decisions': {'sections': (), 'extra': ('Decision Record',), 'commands': False},
    'restrictions': {'sections': (), 'extra': ('Restriction Inventory',), 'commands': False},
    'behaviors': {'sections': (6, 8, 9, 11), 'extra': (), 'commands': False},
    'invariants': {'sections': (7,), 'extra': (), 'commands': False},
    'tests': {'sections': (10,), 'extra': (), 'commands': False},
    'commands': {'sections': (), 'extra': (), 'commands': True},
    'closing': {'sections': (14, 15), 'extra': (), 'commands': False},
    'trace': {'sections': (13,), 'extra': (), 'commands': False},      # only when the driver cannot build it
}
PHASES = (('outline',),
          ('design', 'steps', 'decisions', 'restrictions', 'behaviors', 'invariants', 'tests', 'commands', 'closing'))
FALLBACK = ('trace',)

# What each worker reports for the traceability table, as `<!-- trace K: R-1=ID,ID; R-2=ID -->`.
TRACE_COLUMNS = (('B', 'Behavior'), ('I', 'Invariant'), ('C', 'Component'), ('T', 'Automated test'), ('M', 'Manual check'))
TRACE_KINDS = {'behaviors': 'B and M', 'invariants': 'I', 'tests': 'T'}
# One example per worker, in its own kind: a model copies the letter it is shown (noinit: the invariants and tests
# workers both wrote `trace B`, no test mapping was recognised, and the traceability worker had to run).
TRACE_EXAMPLES = {
    'behaviors': ('<!-- trace B: R-1=B-1,B-2; R-2=B-3 -->', '<!-- trace M: R-2=M-1 -->'),
    'invariants': ('<!-- trace I: R-1=I-1,I-2; R-2=I-3 -->',),
    'tests': ('<!-- trace T: R-1=T-1,T-2; R-2=T-3 -->',),
}
COLUMN_OF = re.compile(r'^([BICTM])-\d+$')
TRACE_LINE = re.compile(r'^[ \t]*<!--\s*trace\s+([A-Z])\s*:\s*(.*?)\s*-->[ \t]*$', re.M)
ID = re.compile(r'[A-Z][A-Z0-9]*-\d+')

SPECIFIC = {
    'outline': (
        'You are first. Every other worker starts the moment you finish and reads only this file, so it is the contract '
        'the whole plan is written to: keep it to about 45 lines, exact, with no prose. Use these headings, in this '
        'order (they are not plan sections):\n\n'
        '- `## Stack`: one line naming the framework, the build tool, and the test runners.\n'
        '- `## Components`: `- C-n Name -- one-phrase responsibility; files: `path`, `path``. Every component has an ID.\n'
        '- `## Steps`: numbered implementation steps, `1. Title -- Owns: `a`, `b` -- Depends on: 2`. Every file the '
        'project needs (source, tests, test and runner configuration, fixtures, `.gitignore`, `.uncle/launch.json`) is '
        'under exactly one step\'s `Owns:`. At most three dependencies per step; most steps have none.\n'
        '- `## Decisions`: `- D-n: the choice, one phrase`.\n'
        '- `## Restrictions`: `- R-n: the restriction, one phrase -- USER, REPOSITORY, PLATFORM or DESIGN`.\n'
        '- `## Tests`: each runner and, by path, the test file each automated test lives in.\n'
        '- `## Requirement map`: one line per requirement of the interpretation, `R-1: C-1, C-2`, naming the '
        'components that implement it.\n\n'
        'Decide everything here once; the other workers will not revisit it.'),
    'design': (
        'Write the architecture, state, domain model, components and data flow. The outline\'s component IDs, names '
        'and files are binding: the Components table lists every `C-n` exactly as the outline has it. Refer to '
        'decisions and restrictions by their outline IDs and do not restate them.'),
    'steps': (
        'Expand the outline\'s steps in the same order and numbering, each with a one-line description. Keep every '
        '`Owns:` and `Depends on:` exactly as the outline has them: do not add, drop or move a file or a dependency. '
        'Also write `.gitignore` at the project root now, as described above.'),
    'decisions': (
        'Write the Decision Record: one row per outline `D-n`, with its short reason. Use the outline\'s IDs exactly; '
        'add none.'),
    'restrictions': (
        'Write the Restriction Inventory: one row per outline `R-n`, with every field the plan requires for a '
        'restriction. Use the outline\'s IDs exactly; add none.'),
    'behaviors': (
        'Give every behavior an ID `B-n` in one table: trigger, observable result, failure behavior, requirement '
        'IDs. Cite requirements by their interpretation IDs. Do not name test IDs or test files here. List manual '
        'checks as `M-n`.'),
    'invariants': (
        'Give every invariant an ID `I-n` in the invariant table. In its "Automated test" column write `see 10`: '
        'the test strategy is written beside you by another worker and the traceability table joins invariants '
        'to tests afterwards. Enforcement points name components (`C-n`) and files from the outline.'),
    'tests': (
        'Give every automated test an ID `T-n`. Use only test files, configuration and the runner that the outline '
        'assigns to a step; never invent a path it does not own. Plan tests from the requirements and acceptance '
        'criteria, not from behaviors or invariants, which are being written beside you. Include the representative '
        'defect injections (each names the defect and the one test that must reject it) and the Protected '
        'verification paths. Do not write the verification commands: another worker owns them.'),
    'commands': (
        'Write the one `## Verification commands` section: a single fenced `sh` block and nothing else. Use only '
        'paths, scripts and the runner the outline assigns to a step. Cover install (reusing a valid installation), '
        'build, unit tests, browser tests and, when the plan has defect injections, one runner command that starts '
        'them concurrently. Before it, you may add a `## Parallel verification groups` section (one fenced `text` '
        'block of one-based command positions) for commands that share no port, output or fixture.'),
    'closing': (
        'Keep both sections short: a line each is the honest answer when it is. Non-goals and risks must be '
        'consistent with the outline\'s decisions and restrictions.'),
    'trace': (
        'The other sections are complete. Write one row per requirement joining the IDs they define: '
        'behavior `B-n`, invariant `I-n`, component `C-n`, automated test `T-n`, manual check `M-n`. '
        'Use only IDs that exist in the files listed above; an ID you cannot find is a gap, written as such.'),
}


def heading(number):
    return '## %d. %s' % (number, TITLES[number])


def expected_headings(name):
    if name == 'outline':
        return ['## ' + title for title in OUTLINE_HEADINGS]
    spec = WORKERS[name]
    rows = [heading(n) for n in spec['sections']] + ['## ' + extra for extra in spec['extra']]
    if spec['commands']:
        rows += ['## ' + GROUPS, '## ' + COMMANDS]
    return rows


def readable(name, directory):
    """Files a worker must read first: everything written in an earlier phase."""
    if name in FALLBACK:
        names = [worker for phase in PHASES for worker in phase]
    else:
        names = []
        for phase in PHASES:
            if name in phase:
                break
            names.extend(phase)
    return ['%s/%s.md' % (directory, earlier) for earlier in names]


def trace_letters(name):
    """The traceability letters a worker reports ('BM' for behaviors), '' for one that reports none."""
    return ''.join(re.findall(r'[A-Z]', TRACE_KINDS.get(name, '')))


def packet_example(name):
    trace = ''
    if trace_letters(name):
        letter = trace_letters(name)[0]
        trace = ',"trace":[{"kind":"%s","requirement":"R-1","ids":["%s-1","%s-2"]}]' % (letter, letter, letter)
    return ('{"schema":"uncle.artifact/v1","kind":"%s","sections":[{"heading":"%s","body":"..."}]%s}'
            % (SECTION_KIND, expected_headings(name)[0], trace))


def contract(name, directory, json_mode=False):
    spec = WORKERS[name]
    earlier = readable(name, directory)
    if json_mode:
        lines = ['', '## Section mode (binding; overrides the output instructions above)', '',
                 'This plan is written by several workers at once. You write only what is named below, '
                 'then stop. Your whole answer is one JSON object, checked against a schema:', '',
                 '`%s`' % packet_example(name), '',
                 'It has one `sections` entry per heading below. `heading` is the heading line exactly as listed; '
                 '`body` is everything under it as Markdown, without a heading line of its own. Do not write a file.', '',
                 'Write exactly these headings, in this order, spelled exactly like this:', '']
    else:
        lines = ['', '## Section mode (binding; overrides the output instructions above)', '',
                 'This plan is written by several workers at once. You write only what is named below, '
                 'to `%s/%s.md`, in a single Write call, then stop. Nobody else will edit your file.' % (directory, name), '',
                 'Write exactly these headings, in this order, spelled exactly like this:', '']
    lines += ['- `%s`' % row for row in expected_headings(name)]
    if spec['commands']:
        lines += ['', 'The `## %s` heading is optional: leave it out when no commands are independent.' % GROUPS]
    if name == 'outline':
        lines += ['', 'Do not write the `# Project plan` title or any plan section; the other workers write them.']
    else:
        lines += ['', 'Do not write the `# Project plan` title, any other numbered section, or any heading not listed. '
                  'Another worker owns every section you are not assigned: refer to its rows by ID and never restate them.']
    if not spec['commands']:
        lines.append('Do not write a `## Verification commands` heading; another worker owns it.')
    if earlier:
        lines += ['', 'Read these first. They are binding; do not contradict them:', '']
        lines += ['- `%s`' % path for path in earlier]
    if name in TRACE_KINDS and json_mode:
        lines += ['', 'Also fill `trace` (kinds: %s): one entry per requirement and kind, `requirement` being a requirement ID from '
                  'the outline\'s `## Requirement map`, nothing else, and `ids` the IDs of yours that cover it. The driver builds '
                  'the traceability table from `trace`.' % TRACE_KINDS[name]]
    elif name in TRACE_KINDS:
        lines += ['', 'End your file with one line per kind (%s), after the last section, exactly in this form: ' % TRACE_KINDS[name]]
        lines += ['`%s`' % example for example in TRACE_EXAMPLES[name]]
        lines += ['The left side of each entry is a requirement ID from the outline\'s `## Requirement map`, nothing else; '
                  'the right side is the IDs of yours that cover it. The driver builds the traceability table from these lines.']
    lines += ['', SPECIFIC[name], '']
    return '\n'.join(lines)


def build_prompt(name, directory, base_prompt, json_mode=False):
    return base_prompt.rstrip('\n') + '\n' + contract(name, directory, json_mode)


def render_packet(name, packet):
    """The Markdown file a worker's validated packet stands for: its sections, then its trace lines.

    Everything downstream (lane checks, assembly, the traceability table) reads that file, so a packet
    changes how a worker delivers, not what the driver does with the delivery."""
    if not isinstance(packet, dict) or packet.get('schema') != 'uncle.artifact/v1' or packet.get('kind') != SECTION_KIND:
        raise ValueError('%s: not a project-plan section packet' % name)
    rows = packet.get('sections')
    if not isinstance(rows, list) or not rows:
        raise ValueError('%s: the packet has no sections' % name)
    parts = []
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('heading'), str) or not row['heading'].startswith('## ')
                or not isinstance(row.get('body'), str) or not row['body'].strip()):
            raise ValueError('%s: every section needs a "## " heading and a body' % name)
        parts.append(row['heading'].rstrip() + '\n\n' + row['body'].strip('\n'))
    by_kind = {}
    for entry in packet.get('trace') or []:
        if (isinstance(entry, dict) and isinstance(entry.get('kind'), str) and isinstance(entry.get('requirement'), str)
                and isinstance(entry.get('ids'), list)):
            ids = [i for i in entry['ids'] if isinstance(i, str) and ID.fullmatch(i)]
            if ids and ID.fullmatch(entry['requirement']):
                by_kind.setdefault(entry['kind'], {}).setdefault(entry['requirement'], []).extend(ids)
    lines = ['<!-- trace %s: %s -->' % (kind, '; '.join('%s=%s' % (req, ','.join(dict.fromkeys(ids)))
                                                      for req, ids in rows_.items()))
             for kind, rows_ in sorted(by_kind.items())]
    return '\n\n'.join(parts) + '\n' + ('\n' + '\n'.join(lines) + '\n' if lines else '')


def blocks(text):
    """(heading line, body) for each `## ` block, ignoring `## ` inside code fences."""
    found, current, body, fenced = [], None, [], False
    for line in text.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
        if not fenced and line.startswith('## '):
            if current is not None:
                found.append((current, '\n'.join(body).rstrip()))
            current, body = line.rstrip(), []
        elif current is not None:
            body.append(line)
    if current is not None:
        found.append((current, '\n'.join(body).rstrip()))
    return found


def key(line):
    match = re.match(r'##\s+(\d+)\.\s', line)
    if match:
        return int(match.group(1))
    name = line[3:].strip()
    for extra in EXTRA + (GROUPS, COMMANDS):
        if name.lower() == extra.lower():
            return extra
    return None


def natural(identifier):
    return [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', identifier)]


def read_file(directory, name):
    try:
        return (Path(directory) / (name + '.md')).read_text(encoding='utf-8')
    except OSError:
        return ''


def trace_lines(text):
    """({kind: {requirement: [ids]}}, text with the trace lines removed)."""
    data = {}
    for kind, payload in TRACE_LINE.findall(text):
        for entry in payload.split(';'):
            if '=' not in entry:
                continue
            requirement, _, ids = entry.partition('=')
            requirement = requirement.strip()
            if not ID.fullmatch(requirement):
                continue
            found = ID.findall(ids)
            if found:
                bucket = data.setdefault(kind, {}).setdefault(requirement, [])
                bucket += [i for i in found if i not in bucket]
    return data, TRACE_LINE.sub('', text)


def outline_requirements(directory):
    """{requirement: [component ids]} from the outline's `## Requirement map`."""
    mapping = {}
    for line, body in blocks(read_file(directory, 'outline')):
        if line[3:].strip().lower() != 'requirement map':
            continue
        for row in body.splitlines():
            match = re.match(r'^[ \t]*[-*+]?[ \t]*`?(%s)`?[ \t]*(?::|=>|->|=|--|→)[ \t]*(.*)$' % ID.pattern, row)
            if match:
                mapping[match.group(1)] = ID.findall(match.group(2))
    return mapping


def merged_trace(directory):
    """{column letter: {requirement: [ids]}}.  Columns come from the IDs themselves (B-, I-, T-, M-, C-), not from the
    letter a worker wrote on its line, and only requirements of the outline's map are rows."""
    components = outline_requirements(directory)
    requirements = set(components)
    data = {}
    for name in TRACE_KINDS:
        found, _ = trace_lines(read_file(directory, name))
        for rows in found.values():
            for requirement, ids in rows.items():
                if requirements and requirement not in requirements:
                    continue                       # `B-1=I-1` style lines map something else, not a requirement
                for identifier in ids:
                    match = COLUMN_OF.match(identifier)
                    if match:
                        bucket = data.setdefault(match.group(1), {}).setdefault(requirement, [])
                        if identifier not in bucket:
                            bucket.append(identifier)
    for requirement, ids in components.items():
        data.setdefault('C', {})[requirement] = ids
    return data


def trace_ready(directory):
    """Section 13 can be built without a model: behaviors, tests and components all mapped some requirement."""
    data = merged_trace(directory)
    return all(data.get(kind) for kind in ('B', 'T', 'C'))


def trace_section(directory):
    data = merged_trace(directory)
    requirements = sorted({r for rows in data.values() for r in rows}, key=natural)
    header = '| Requirement | ' + ' | '.join(title for _, title in TRACE_COLUMNS) + ' |'
    rule = '|---|' + '---|' * len(TRACE_COLUMNS)
    rows = []
    for requirement in requirements:
        cells = [', '.join(data.get(kind, {}).get(requirement, [])) or 'none' for kind, _ in TRACE_COLUMNS]
        rows.append('| %s | %s |' % (requirement, ' | '.join(cells)))
    return '\n'.join([header, rule] + rows)


def assemble(directory):
    directory = Path(directory)
    found = {}
    for name in WORKERS:
        if name == 'outline':
            continue
        path = directory / (name + '.md')
        try:
            text = path.read_text(encoding='utf-8')
        except OSError:
            if name == 'trace':
                continue                                   # built by the driver when the workers mapped enough
            raise ValueError('%s: the section file was not written' % path.name)
        _, text = trace_lines(text)
        spec = WORKERS[name]
        allowed = set(spec['sections']) | set(spec['extra']) | ({GROUPS, COMMANDS} if spec['commands'] else set())
        previous = None
        for line, body in blocks(text):
            item = key(line)
            if item is None and previous is not None:
                # A heading no section owns (a worker's own sub-heading, such as "Defect injections" or
                # "Protected verification paths") is part of the section above it, one level down.  Refusing
                # the whole plan over it threw away nine workers' output and ran the single-pass plan.
                old_line, old_body = found[previous]
                found[previous] = (old_line, old_body + '\n\n### ' + line[3:].strip() + '\n' + body)
                continue
            if item not in allowed:
                raise ValueError('%s: unexpected heading %r' % (path.name, line))
            if item in found:
                raise ValueError('%s: section %r is written twice' % (path.name, line))
            if not body.strip():
                raise ValueError('%s: section %r is empty' % (path.name, line))
            found[item] = (line, body)
            previous = item
    if 13 not in found:
        if not trace_ready(directory):
            raise ValueError('section 13 cannot be built: the workers mapped too few requirements')
        found[13] = (heading(13), '\n' + trace_section(directory))
    missing = [str(n) for n in TITLES if n not in found]
    if missing:
        raise ValueError('sections missing: ' + ', '.join(missing))
    for needed in EXTRA + (COMMANDS,):
        if needed not in found:
            raise ValueError('section missing: ' + needed)
    order = list(TITLES) + list(EXTRA) + [GROUPS, COMMANDS]
    parts = ['# Project plan']
    for item in order:
        if item not in found and item == GROUPS:
            continue                                   # optional
        line, body = found[item]
        parts.append(line + ('\n' + body if body else ''))
    return '\n\n'.join(parts) + '\n'


def final_text(log):
    """What the worker said last: the result event's text, else its last assistant text."""
    result, last = '', ''
    try:
        lines = Path(log).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return ''
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'result' and isinstance(event.get('result'), str):
            result = event['result']
        elif event.get('type') == 'assistant':
            for part in (event.get('message') or {}).get('content') or []:
                if isinstance(part, dict) and part.get('type') == 'text':
                    last = part.get('text') or last
    return result or last


def recover(log, output):
    """A worker that answered in chat instead of writing its section file: take the answer.

    Only text that is plainly sections is taken -- it must open with a `## ` heading, after an optional
    wrapping fence -- and assembly still checks every heading against the worker's lane."""
    text = final_text(log).strip()
    match = re.match(r'^```(?:markdown|md)?\s*\n(.*)\n```$', text, re.S)
    if match:
        text = match.group(1).strip()
    if not text.startswith('## '):
        raise ValueError('nothing to recover: the worker\'s last message is not a section')
    Path(output).write_text(text + '\n', encoding='utf-8')


def main(argv):
    try:
        if argv[:1] == ['phases']:
            for phase in PHASES:
                print(' '.join(phase))
        elif argv[:1] == ['prompt'] and len(argv) in (5, 6):
            _, name, directory, base, output = argv[:5]
            Path(output).write_text(build_prompt(name, directory, Path(base).read_text(encoding='utf-8'),
                                                 json_mode=argv[5:] == ['--json']), encoding='utf-8')
        elif argv[:1] == ['render'] and len(argv) == 4:
            try:
                packet = json.loads(Path(argv[2]).read_text(encoding='utf-8'))
            except (OSError, ValueError) as error:
                raise ValueError('%s: the packet is not valid JSON: %s' % (argv[1], error))
            Path(argv[3]).write_text(render_packet(argv[1], packet), encoding='utf-8')
        elif argv[:1] == ['trace-ready'] and len(argv) == 2:
            return 0 if trace_ready(argv[1]) else 1
        elif argv[:1] == ['recover'] and len(argv) == 3:
            recover(argv[1], argv[2])
        elif argv[:1] == ['assemble'] and len(argv) == 3:
            Path(argv[2]).write_text(assemble(argv[1]), encoding='utf-8')
        else:
            raise SystemExit(__doc__)
    except ValueError as error:
        print('project plan sections: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
