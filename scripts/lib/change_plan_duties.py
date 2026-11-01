#!/usr/bin/env python3
"""The change-request counterpart of the new-application `project-plan-stage-duties`: one consistency check over the finished
change plan, before anyone approves it.

The new-application driver writes its plan in independent sections, so a model step finishes it: it finds contradictions between
sections (the commonest is one file with two names) and completes the `.gitignore` duties. A change plan is written in one pass
by one model, and a change request edits an existing repository, so this version differs in two deliberate ways:

  * The check is deterministic and the model is optional. A plan is flagged when it mentions a source file that no step owns, that
    does not exist in the repository, and that sits beside (or among) files a step does own: the same "one file, two names" mistake,
    without the noise of every existing file a plan merely reads for context. The model is asked to fix it only when there is
    a finding; a clean plan costs no model call at all.
  * There is no `.gitignore` duty. A change request must not make unrelated edits to an existing repository, and a plan that merely
    mentions an ecosystem is not a reason to rewrite its ignore rules.

The fix is a patch (scripts/lib/plan_patch.py) applied to the canonical CHANGE_PLAN.json by the driver, never an edit to the Markdown
view, so the canonical plan stays the only thing that is approved.

    change_plan_duties.py check  PROJECT [PLAN.md]        # one finding per line
    change_plan_duties.py prompt PROJECT PLAN.md OUT      # the fix prompt for the model
    change_plan_duties.py apply  PROJECT DELIVERY [LOG]   # apply the model's patch (file, else the runner's text); prints what remains
"""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB))
CANONICAL = Path('.uncle/workflow/documents/CHANGE_PLAN.json')


def _module(name):
    spec = importlib.util.spec_from_file_location(name, LIB / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def owned_files(plan):
    """The files the plan's steps declare they own, from the driver's own plan parser (plan-scope.sh)."""
    if not Path(plan).is_file():
        return set()
    done = subprocess.run(['bash', '-c', '. "%s/plan-scope.sh"; plan_step_owns "%s"' % (LIB, plan)], capture_output=True, text=True)
    owned = set()
    for row in done.stdout.splitlines():
        _, _, path = row.partition('\t')
        path = path.strip().strip('`')
        if path and path != '*':
            owned.add(path)
    return owned


def known_files(project):
    """Every file git knows in the project, tracked or not (empty when it is not a git checkout)."""
    names = set()
    for args in (['git', 'ls-files'], ['git', 'ls-files', '--others', '--exclude-standard']):
        done = subprocess.run(args, cwd=project, capture_output=True, text=True)
        names.update(line.strip() for line in done.stdout.splitlines() if line.strip())
    return names


def narrative_of(project, plan):
    try:
        payload = json.loads((Path(project) / CANONICAL).read_text(encoding='utf-8'))
        if isinstance(payload, dict) and isinstance(payload.get('narrative'), str):
            return payload['narrative']
    except (OSError, ValueError):
        pass
    try:
        return Path(plan).read_text(encoding='utf-8')
    except OSError:
        return ''


def findings(project, plan='.uncle/docs/CHANGE_PLAN.md'):
    text = narrative_of(project, Path(project) / plan if not Path(plan).is_absolute() else plan)
    consistency = _module('plan_consistency')
    owned = {consistency.clean(p) for p in owned_files(Path(project) / plan)}
    if not owned:
        return []
    directories = {str(Path(p).parent) for p in owned}
    known = known_files(project)
    basenames = {Path(p).name for p in owned | known}
    out = []
    for path in sorted(consistency.mentioned_files(text)):
        if path in owned or (Path(project) / path).exists():
            continue
        if '/' not in path and path in basenames:
            continue          # a bare file name is how prose refers to a file it has already named in full
        parent, suffix = str(Path(path).parent), Path(path).suffix
        beside = sorted(o for o in owned if str(Path(o).parent) == parent and Path(o).suffix == suffix)
        if beside:
            out.append('`%s` is mentioned but does not exist and no step owns it, and `%s` is owned beside it: one file with two names?'
                       % (path, '`, `'.join(beside)))
        elif parent in directories and parent != '.':
            out.append('`%s` is mentioned but does not exist and no step owns it (the plan owns other files in `%s/`).'
                       % (path, parent))
    return out


PROMPT = '''Fix the contradictions in a finished change plan, once. Do not review the plan, and do not rewrite it.

The authoritative plan is `.uncle/workflow/documents/CHANGE_PLAN.json` (its `narrative`). Read it, and read the request in
`CHANGE_REQUEST.md` if you need to choose between two readings.

The driver compared every file the plan mentions with the files its steps own and the files that exist in the repository, and found:

%s

For each one, choose the reading the request and most of the plan already use, and change the fewest places so the plan says one
thing. If a mentioned file really is one the plan forgot to give an owner, add it to the owning step's `Owns:` list; if it is a
second name for an owned file, use the owned name everywhere. Report nothing else, and change nothing else.

Reply with one JSON object and nothing else. If you can write files, also write the same object to the delivery path.

`{"schema":"uncle.artifact/v1","kind":"change-plan-duties","patch":{"replace_text":[{"heading":"<exact existing ## heading>","old":"<text copied exactly from that section, unique within it>","new":"<replacement>"}],"edit_sections":[],"insert_sections":[]}}`

`replace_text` changes a snippet inside a section (prefer it); `edit_sections` replaces one section's whole body
(`{"heading": ..., "content": ...}`); copy headings and `old` text exactly. Make the patch empty (`"patch":{}`) only if you decide
every finding is already consistent and say why in a `"note"` field.
'''


def prompt(project, plan, out):
    found = findings(project, plan)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(PROMPT % '\n'.join('- ' + line for line in found), encoding='utf-8')
    return found


def packet_from(delivery, log=None):
    """The model's packet: the delivery file if it wrote one, else the last such object in the runner's final text."""
    candidates = []
    try:
        candidates.append(Path(delivery).read_text(encoding='utf-8'))
    except OSError:
        pass
    if log:
        try:
            runner_events = _module('runner_events')
            for line in reversed(Path(log).read_text(encoding='utf-8', errors='replace').splitlines()):
                try:
                    candidates.extend(reversed(list(runner_events.texts(json.loads(line)))))
                except (ValueError, TypeError):
                    continue
        except (OSError, ImportError):
            pass
    for text in candidates:
        for chunk in [text] + re.findall(r'\{.*\}', text, re.S):
            try:
                payload = json.loads(chunk.strip().strip('`'))
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get('kind') == 'change-plan-duties' and isinstance(payload.get('patch'), dict):
                return payload
    raise ValueError('the model returned no change-plan-duties packet with a patch')


def apply(project, delivery, plan='.uncle/docs/CHANGE_PLAN.md', log=None):
    packet = packet_from(delivery, log)
    target = Path(project) / CANONICAL
    payload = json.loads(target.read_text(encoding='utf-8'))
    if any(packet['patch'].get(key) for key in ('replace_text', 'edit_sections', 'insert_sections')):
        payload['narrative'] = _module('plan_patch').apply_patch(payload['narrative'], packet['patch'])
        artifact = _module('artifact_json')
        rendered = artifact.render_change_plan(payload, require_dispositions=False)
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        temporary.replace(target)
        view = Path(project) / plan
        view.write_text(rendered + '\n', encoding='utf-8')
    return findings(project, plan)


def main(argv):
    try:
        if len(argv) in (3, 4) and argv[1] == 'check':
            for line in findings(argv[2], argv[3] if len(argv) == 4 else '.uncle/docs/CHANGE_PLAN.md'):
                print(line)
        elif len(argv) == 5 and argv[1] == 'prompt':
            for line in prompt(argv[2], argv[3], argv[4]):
                pass
        elif len(argv) in (4, 5) and argv[1] == 'apply':
            for line in apply(argv[2], argv[3], log=argv[4] if len(argv) == 5 else None):
                print(line)
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (ValueError, OSError) as error:
        print('change plan duties: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
