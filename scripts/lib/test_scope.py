#!/usr/bin/env python3
"""Run only the tests a change can affect, for the changes where that is a defensible thing to do -- and say so plainly.

The baseline always runs the full approved commands, and the driver's own result is the evidence a change is judged on. Scoping
only ever shortens the *final* check, only for the two Uncle runners that accept `-- suite ...` (scripts/run-python-tests.sh and
scripts/run-shell-tests.sh), and only when the mapping is confident:

  * every changed file is covered by at least one suite (a test maps to itself; any other file maps to the suites that name it);
  * no changed file is a hot file named by more than MAX_FAN_IN suites (a driver or shared library that most of the suite
    exercises is not "impacted tests" at all -- it is the full suite);
  * a runner command with no impacted suite is *omitted and reported NOT RUN*, never replaced by something that passes.

Any other command (a linter, `node --check`, `pytest`, ...) is left exactly as approved, so it still runs in full. A project with
no rewritable command gets no scoping at all. A scoped command is a new command string to the green check, so a failure of it is
classified as a REGRESSION, never excused by a failing baseline: scoping can lose coverage, it cannot hide a failure it ran.

    test_scope.py impact   PROJECT [FILE ...]        # JSON: the impacted suites, confidence and reasons
    test_scope.py rewrite  PROJECT COMMANDS OUT SCOPE_JSON CLASS [FILE ...]
    test_scope.py preview  PROJECT [FILE ...]        # "IMPACTED TOTAL confident|unsure" on one line
    test_scope.py report   SCOPE_JSON                # the Markdown "Test scope" section (empty when nothing was scoped)
"""
import json
from pathlib import Path
import re
import subprocess
import sys

MAX_FAN_IN = 12
GENERIC = {'readme', 'main', 'index', 'test', 'tests', 'utils', 'common', 'config', 'setup', 'init'}
NON_CODE = re.compile(r'(?i)\.(md|markdown|txt|rst)$|(^|/)(docs?|documentation)/|(^|/)(LICENSE|CHANGELOG)[^/]*$|^\.gitignore$')
RUNNER = re.compile(r'^(?P<head>(?:bash\s+)?(?:\./)?scripts/run-(?P<kind>python|shell)-tests\.sh)(?P<rest>(?:\s.*)?)$')
SUITE_FILE = re.compile(r'^scripts/tests/(?P<name>[a-z0-9][a-z0-9-]*)-test\.(?P<ext>py|sh)$')
WORKFLOW_DOCS = {'REQUIREMENTS.md', 'REQUIREMENTS_INTERPRETATION.md', 'PROJECT_PLAN.md', 'UPDATED_PROJECT_PLAN.md',
                 'ADVERSARIAL_REVIEW.md', 'PREFLIGHT_REPORT.md', 'AUTOMATED_TEST_REPORT.md', 'IMPLEMENTATION_NOTES.md',
                 'TEST_REVIEW.md', 'MANUAL_CHECKLIST.md', 'VERIFICATION_REPORT.md', 'FINAL_AUDIT.md', 'CHANGE_REQUEST.md',
                 'CHANGE_SPEC.md', 'CHANGE_PLAN.md', 'BASELINE_REPORT.md', 'CHANGE_TEST_REPORT.md', 'DEFECTS.md'}


def changed_files(project):
    files = []
    for args in (['git', 'diff', '--name-only', 'HEAD'], ['git', 'ls-files', '--others', '--exclude-standard']):
        done = subprocess.run(args, cwd=project, capture_output=True, text=True)
        for name in done.stdout.splitlines():
            name = name.strip()
            if not name or name.startswith('.uncle/') or name.rsplit('/', 1)[-1] in WORKFLOW_DOCS or name in files:
                continue
            files.append(name)
    return files


def suites(project):
    found = {'python': {}, 'shell': {}}
    for path in sorted(Path(project, 'scripts/tests').glob('*-test.*')):
        match = SUITE_FILE.match('scripts/tests/' + path.name)
        if match:
            kind = 'python' if match['ext'] == 'py' else 'shell'
            try:
                found[kind][match['name']] = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                found[kind][match['name']] = ''
    return found


def tokens(path):
    stem = path.rsplit('/', 1)[-1].rsplit('.', 1)[0]
    base = path.rsplit('/', 1)[-1]
    found = {base, stem, stem.replace('_', '-'), stem.replace('-', '_'), path}
    return {t for t in found if len(t) >= 5 and t.lower() not in GENERIC}


def impact(project, files=None):
    files = changed_files(project) if files is None else list(files)
    index = suites(project)
    per_file, reasons = {}, []
    chosen = {'python': set(), 'shell': set()}
    for f in files:
        match = SUITE_FILE.match(f)
        if match:
            kind = 'python' if match['ext'] == 'py' else 'shell'
            per_file[f] = [kind + ':' + match['name']]
            chosen[kind].add(match['name'])
            continue
        hits = []
        for kind in ('python', 'shell'):
            for name, text in index[kind].items():
                if any(t in text for t in tokens(f)):
                    hits.append((kind, name))
        per_file[f] = [k + ':' + n for k, n in hits]
        if not hits:
            reasons.append('%s is named by no suite%s' % (f, ' (documentation)' if NON_CODE.search(f) else ''))
        elif len(hits) > MAX_FAN_IN:
            reasons.append('%s is named by %d suites; that is the full suite, not an impacted set' % (f, len(hits)))
        else:
            for kind, name in hits:
                chosen[kind].add(name)
    if not files:
        reasons.append('no changed files were found')
    total = {kind: len(index[kind]) for kind in index}
    return {'files': files, 'per_file': per_file, 'suites': {k: sorted(v) for k, v in chosen.items()},
            'totals': total, 'confident': not reasons, 'reasons': reasons}


def rewrite(project, commands, out, scope_json, cls, files=None):
    """Write the scoped commands file; return the scope record (applied=False when nothing was reduced)."""
    found = impact(project, files)
    lines = [line.rstrip('\n') for line in Path(commands).read_text(encoding='utf-8').splitlines() if line.strip()]
    record = {'scope': 'impacted', 'class': cls, 'applied': False, 'files': found['files'], 'confident': found['confident'],
              'reasons': found['reasons'], 'not_run_commands': [], 'scoped_commands': [], 'suites_run': found['suites'],
              'suites_total': found['totals']}
    if not found['confident']:
        Path(out).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        Path(scope_json).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        return record
    scoped, reduced = [], False
    for line in lines:
        match = RUNNER.match(line.strip())
        if not match or re.search(r'(^|\s)--(\s|$)', match['rest']):
            scoped.append(line)           # not a runner we can scope, or the plan already chose its suites
            continue
        names = found['suites'][match['kind']]
        if not names:
            record['not_run_commands'].append(line)
            reduced = True
            continue
        if len(names) >= found['totals'][match['kind']]:
            scoped.append(line)           # every suite is impacted: this is the full run
            continue
        scoped.append('%s%s -- %s' % (match['head'], match['rest'], ' '.join(names)))
        record['scoped_commands'].append(scoped[-1])
        reduced = True
    if not scoped:                         # nothing left to run is not a scope, it is no verification
        reduced = False
        record['reasons'].append('every approved command would have been omitted')
    record['applied'] = reduced
    Path(out).write_text('\n'.join(scoped if reduced else lines) + '\n', encoding='utf-8')
    Path(scope_json).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def report(scope_json):
    try:
        record = json.loads(Path(scope_json).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ''
    if not record.get('applied'):
        return ''
    run, total = record['suites_run'], record['suites_total']
    out = ['## Test scope', '',
           'This %s change was verified with an IMPACTED subset of the test suites, not the full suite. Everything below that '
           'was not named as run was NOT RUN; none of it is claimed to pass.' % record['class'], '']
    for kind in ('python', 'shell'):
        out.append('- %s suites: ran %d of %d (%s); the other %d were NOT RUN.' % (
            kind, len(run[kind]), total[kind], ', '.join(run[kind]) or 'none', total[kind] - len(run[kind])))
    for command in record['not_run_commands']:
        out.append('- NOT RUN (no impacted suite): `%s`' % command)
    out += ['', 'Changed files: ' + ', '.join('`%s`' % f for f in record['files'][:20]),
            '', 'Set `WORKFLOW_TEST_SCOPE=full` to run every approved command in full.']
    return '\n'.join(out) + '\n'


def main(argv):
    command = argv[1] if len(argv) > 1 else ''
    if command == 'impact' and len(argv) >= 3:
        print(json.dumps(impact(argv[2], argv[3:] or None), indent=2))
    elif command == 'rewrite' and len(argv) >= 7:
        record = rewrite(argv[2], argv[3], argv[4], argv[5], argv[6], argv[7:] or None)
        print('impacted scope %s: %s' % ('applied' if record['applied'] else 'not applied',
                                         '; '.join(record['reasons']) or 'confident'))
    elif command == 'preview' and len(argv) >= 3:
        found = impact(argv[2], argv[3:] or None)
        print('%d %d %s' % (sum(len(v) for v in found['suites'].values()), sum(found['totals'].values()),
                            'confident' if found['confident'] else 'unsure'))
    elif command == 'report' and len(argv) == 3:
        sys.stdout.write(report(argv[2]))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
