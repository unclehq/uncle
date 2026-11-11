#!/usr/bin/env python3
"""Per-stage input fingerprints, so `uncle --revalidate` re-runs only stages whose inputs changed.

usage: revalidate.py [--root DIR] record STAGE
       revalidate.py [--root DIR] run [--dry-run]
Exit: 0 all reused/passed; 1 any failed, blocked or needs-review; 2 no state or no recorded passes.

D-9 stage table (binding; input kinds are the keys of INPUT_KINDS below):
  stage             approved docs (+ .sha256)                      other inputs
  ANALYZE           CHANGE_REQUEST                                 prompt, config
  CHANGE_PLAN_DUTIES CHANGE_REQUEST, CHANGE_SPEC                   prompt, config
  PLAN              CHANGE_REQUEST, CHANGE_SPEC                    app, tests, prompt, config
  CLASSIFY          CHANGE_REQUEST, CHANGE_SPEC, CHANGE_PLAN       prompt, config
  ADVERSARIAL_REVIEW CHANGE_SPEC, CHANGE_PLAN                      prompt, config
  UPDATED_PLAN      CHANGE_SPEC, CHANGE_PLAN, ADVERSARIAL_REVIEW   prompt, config
  PREFLIGHT         CHANGE_PLAN                                    prompt, config
  MODULE_INTERFACES CHANGE_SPEC, CHANGE_PLAN                       prompt, config
  IMPLEMENT         CHANGE_SPEC, CHANGE_PLAN                       app, tests, protected, prompt, config
  TEST_REVIEW       CHANGE_SPEC, CHANGE_PLAN                       app, tests, protected, prompt, config
  MANUAL_CHECKLIST  CHANGE_SPEC, CHANGE_PLAN                       app, tests, protected, prompt, config
  EXECUTE_CHECKLIST CHANGE_SPEC, CHANGE_PLAN, MANUAL_CHECKLIST     app, tests, protected, prompt, config
  FINAL_AUDIT       CHANGE_SPEC, CHANGE_PLAN, VERIFICATION_REPORT  app, tests, protected, prompt, config
Downstream of a stage = every later stage in STAGES. A stage or input not in the table counts as changed.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

UNKNOWN = 'unmapped'

# (stage, approved-doc names, extra input kinds)
_TABLE = [
    ('ANALYZE', ['CHANGE_REQUEST'], ['prompt', 'config']),
    ('CHANGE_PLAN_DUTIES', ['CHANGE_REQUEST', 'CHANGE_SPEC'], ['prompt', 'config']),
    ('PLAN', ['CHANGE_REQUEST', 'CHANGE_SPEC'], ['app', 'tests', 'prompt', 'config']),
    ('CLASSIFY', ['CHANGE_REQUEST', 'CHANGE_SPEC', 'CHANGE_PLAN'], ['prompt', 'config']),
    ('ADVERSARIAL_REVIEW', ['CHANGE_SPEC', 'CHANGE_PLAN'], ['prompt', 'config']),
    ('UPDATED_PLAN', ['CHANGE_SPEC', 'CHANGE_PLAN', 'ADVERSARIAL_REVIEW'], ['prompt', 'config']),
    ('PREFLIGHT', ['CHANGE_PLAN'], ['prompt', 'config']),
    ('MODULE_INTERFACES', ['CHANGE_SPEC', 'CHANGE_PLAN'], ['prompt', 'config']),
    ('IMPLEMENT', ['CHANGE_SPEC', 'CHANGE_PLAN'], ['app', 'tests', 'protected', 'prompt', 'config']),
    ('TEST_REVIEW', ['CHANGE_SPEC', 'CHANGE_PLAN'], ['app', 'tests', 'protected', 'prompt', 'config']),
    ('MANUAL_CHECKLIST', ['CHANGE_SPEC', 'CHANGE_PLAN'], ['app', 'tests', 'protected', 'prompt', 'config']),
    ('EXECUTE_CHECKLIST', ['CHANGE_SPEC', 'CHANGE_PLAN', 'MANUAL_CHECKLIST'], ['app', 'tests', 'protected', 'prompt', 'config']),
    ('FINAL_AUDIT', ['CHANGE_SPEC', 'CHANGE_PLAN', 'VERIFICATION_REPORT'], ['app', 'tests', 'protected', 'prompt', 'config']),
]
STAGES = [{'name': n, 'docs': d, 'kinds': k} for n, d, k in _TABLE]
NAMES = [s['name'] for s in STAGES]
PROMPT_FILES = ['scripts/change-workflow.sh', 'scripts/stagegate.sh']


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file(path):
    try:
        return _sha(Path(path).read_bytes())
    except OSError:
        return 'missing'


def fp_dir(root):
    return Path(root) / '.uncle' / 'workflow' / 'stage-fingerprints'


def _project_files(root):
    from project_paths import project_files
    return sorted(set(project_files(root)))


def _protected_paths(root):
    for name in ('protected-paths', 'protected-verification-paths'):
        p = Path(root) / '.uncle' / 'workflow' / name
        if p.is_file():
            return [l.strip() for l in p.read_text(errors='replace').splitlines() if l.strip() and not l.startswith('#')]
    return []


def _tree(root, pick):
    from tree_fingerprint import is_application_file
    h = hashlib.sha256()
    for rel in _project_files(root):
        if any(part.startswith('.') for part in Path(rel).parts):
            continue  # hidden bookkeeping (.uncle, scratch markers) is not a stage input
        if pick(rel, is_application_file(rel)):
            h.update(rel.encode('utf-8', 'replace') + b'\0' + _file(Path(root) / rel).encode() + b'\n')
    return h.hexdigest()


def input_hash(kind, root):
    """Hash of one input; raises on error (callers treat any exception as changed)."""
    root = Path(root)
    docs = root / '.uncle' / 'docs'
    if kind.startswith('doc:'):
        name = kind[4:]
        return _sha((_file(docs / (name + '.md')) + _file(root / '.uncle/workflow/approvals' / (name + '.sha256'))).encode())
    if kind == 'app':
        return _tree(root, lambda rel, app: app and rel != 'README.md')
    if kind == 'tests':
        return _tree(root, lambda rel, app: not app and rel != 'README.md')  # only root README.md is exempt
    if kind == 'protected':
        return _sha('\0'.join(p + ':' + _file(root / p) for p in sorted(_protected_paths(root))).encode())
    if kind == 'prompt':
        return _sha('\0'.join(_file(root / p) for p in PROMPT_FILES).encode())
    if kind == 'config':
        return _file(root / '.uncle' / 'config')
    raise KeyError(kind)


def _kinds(stage):
    spec = next((s for s in STAGES if s['name'] == stage), None)
    if spec is None:
        raise KeyError(stage)
    return ['doc:' + d for d in spec['docs']] + list(spec['kinds'])


def inputs(stage, root):
    return {k: input_hash(k, root) for k in _kinds(stage)}


def fingerprint(stage, root):
    """Combined hash of a stage's inputs. Raises KeyError for an unmapped stage."""
    return _sha(json.dumps(inputs(stage, root), sort_keys=True).encode())


def _read(root, stage):
    try:
        data = json.loads((fp_dir(root) / (stage + '.json')).read_text())
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write(root, stage, data):
    d = fp_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ('.%s.%d.tmp' % (stage, os.getpid()))
    tmp.write_text(json.dumps(data, sort_keys=True))
    os.replace(tmp, d / (stage + '.json'))


def record(stage, root):
    """Write a pass record. Only call at an explicit stage-success point."""
    ins = inputs(stage, root)
    mark_ran(stage, root)
    _write(root, stage, {'stage': stage, 'hash': _sha(json.dumps(ins, sort_keys=True).encode()),
                         'inputs': ins, 'status': 'pass', 'time': int(time.time()),
                         'readme': _file(Path(root) / 'README.md')})


# Evidence a stage ran before fingerprints existed (legacy): a history marker, or its output artifact.
_LEGACY_EVIDENCE = {'ANALYZE': 'CHANGE_SPEC.md', 'PLAN': 'CHANGE_PLAN.md', 'ADVERSARIAL_REVIEW': 'ADVERSARIAL_REVIEW.md',
                    'IMPLEMENT': 'IMPLEMENTATION_NOTES.md', 'TEST_REVIEW': 'TEST_REVIEW.md',
                    'MANUAL_CHECKLIST': 'MANUAL_CHECKLIST.md', 'EXECUTE_CHECKLIST': 'VERIFICATION_REPORT.md',
                    'FINAL_AUDIT': 'FINAL_AUDIT.md'}


def mark_ran(stage, root):
    """Driver hook: note that STAGE started executing (workflow history)."""
    d = Path(root) / '.uncle' / 'workflow' / 'stage-history'
    d.mkdir(parents=True, exist_ok=True)
    (d / stage).write_text(str(int(time.time())) + '\n')


def has_run(root, stage):
    root = Path(root)
    if (root / '.uncle' / 'workflow' / 'stage-history' / stage).is_file():
        return True
    art = _LEGACY_EVIDENCE.get(stage)
    return bool(art) and (root / '.uncle' / 'docs' / art).is_file()


def _has_state(root):
    return (Path(root) / '.uncle').is_dir()


# Approved docs a stage produces; a stage re-run makes readers of that doc re-run (RI-4).
PRODUCES = {'ADVERSARIAL_REVIEW': 'ADVERSARIAL_REVIEW', 'MANUAL_CHECKLIST': 'MANUAL_CHECKLIST',
            'EXECUTE_CHECKLIST': 'VERIFICATION_REPORT'}


def _doc_names(stage):
    return next((s['docs'] for s in STAGES if s['name'] == stage), [])


def plan(root):
    """Return (None|'no-state'|'no-passes', rows). Row: {stage, action: reuse|run|needs-review, reason}."""
    root = Path(root)
    if not _has_state(root):
        return 'no-state', []
    recs = {n: _read(root, n) for n in NAMES}
    if not any(r and r.get('status') == 'pass' for r in recs.values()):
        return 'no-passes', []
    rows, bad = [], {}  # bad: stage -> 'run' | 'needs-review' for stages not reused
    for n in NAMES:
        rec = recs[n]
        if rec is None:
            if has_run(root, n):  # legacy: ran before, no fingerprint -> counts as changed
                rows.append({'stage': n, 'action': 'run', 'reason': 'legacy: ran earlier, no recorded fingerprint'})
                bad[n] = 'run'
            else:
                rows.append({'stage': n, 'action': 'skip', 'reason': 'never run in this project; not run'})
            continue
        up = next((d for d in sorted(bad) if PRODUCES.get(d) in _doc_names(n)), None)
        if up:
            act = 'needs-review' if bad[up] == 'needs-review' else 'run'
            rows.append({'stage': n, 'action': act, 'reason': ('blocked by %s' if act == 'needs-review' else 'upstream %s changed') % up})
            bad[n] = act
            continue
        if rec.get('status') != 'pass':
            rows.append({'stage': n, 'action': 'run', 'reason': 'invalidated'})
            bad[n] = 'run'
            continue
        try:
            cur = inputs(n, root)
        except Exception:
            rows.append({'stage': n, 'action': 'run', 'reason': 'input unreadable'})
            bad[n] = 'run'
            continue
        old = rec.get('inputs') or {}
        diff = sorted(k for k in set(cur) | set(old) if cur.get(k) != old.get(k))
        if not diff:
            rows.append({'stage': n, 'action': 'reuse', 'reason': 'inputs unchanged'})
            continue
        act = 'needs-review' if 'protected' in diff else 'run'
        rows.append({'stage': n, 'action': act, 'reason': 'changed: ' + ', '.join(diff)})
        bad[n] = act
    return None, rows


def _invalidate(root, stage):
    old = _read(root, stage) or {}
    _write(root, stage, {'stage': stage, 'hash': old.get('hash', ''), 'inputs': old.get('inputs', {}),
                         'status': 'invalidated', 'time': int(time.time())})


def _snapshot(root):
    out = {}
    base = Path(root) / '.uncle'
    for pat in ('**/approvals/*.sha256', '**/*.sha256', '**/attestation*', '**/attest*/**/*'):
        for p in base.glob(pat):
            if p.is_file() and 'stage-fingerprints' not in p.parts:
                out[str(p.relative_to(root))] = _file(p)
    return out


def plan_path(root):
    return Path(root) / '.uncle' / 'workflow' / 'revalidate-plan.json'


def write_plan(root, rows):
    p = plan_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name('.revalidate-plan.%d.tmp' % os.getpid())
    tmp.write_text(json.dumps({'rows': rows}, sort_keys=True))
    os.replace(tmp, p)


def driver_mode_flag(env):
    """The one mode flag the change driver accepts for this run: --attended only when the launcher resolved an attended run."""
    return '--attended' if env.get('UNCLE_ATTENDED') == '1' else '--unattended'


def default_runner(stage, root):
    """Resume the change driver at STAGE with approval/attestation writers disabled.
    Returns 'pass', 'failed' or 'blocked'."""
    state = Path(root) / '.uncle' / 'workflow' / 'state'
    # Hand-off contract for the driver: UNCLE_REVALIDATE_RESUME=<stage to resume at> and
    # UNCLE_REVALIDATE_PLAN=<path to JSON {"rows":[{stage,action,reason}]}>; driver runs only
    # stages whose action is 'run', skips 'reuse'/'skip', stops (exit 75) at 'needs-review'.
    # No-UI is an environment setting, not a driver flag: the driver rejects `--noui` as an unknown argument. The mode flag is
    # the one the launcher resolved (`--attended` sets UNCLE_ATTENDED); the driver accepts only these two.
    env = dict(os.environ, UNCLE_REVALIDATE='1', UNCLE_REVALIDATE_STAGE=stage, UNCLE_REVALIDATE_RESUME=stage,
               UNCLE_REVALIDATE_PLAN=str(plan_path(root)), UNCLE_NOUI='1')
    driver = Path(__file__).resolve().parent.parent / 'change-workflow.sh'
    before = _snapshot(root)
    try:
        state.write_text(stage + '\n')
        rc = subprocess.run(['bash', str(driver), driver_mode_flag(env)], cwd=root, env=env).returncode
    except OSError:
        return 'failed'
    if _snapshot(root) != before:
        print('revalidate: approval/attestation files changed during %s (violation)' % stage, file=sys.stderr)
        return 'failed'
    if rc == 0:
        # Exit 0 alone is not a pass: the driver also exits 0 after reopening a gate whose approval no longer matches ("re-run the
        # driver to review it"), having run nothing. It empties revalidate-pending.txt only as each run-marked stage finishes, so
        # the stage passed only if that file exists and no longer lists it.
        return 'pass' if _stage_completed(stage, root) else 'failed'
    return 'blocked' if rc == 3 else 'failed'


def _stage_completed(stage, root):
    pending = Path(root) / '.uncle' / 'workflow' / 'revalidate-pending.txt'
    try:
        remaining = [line.strip() for line in pending.read_text().splitlines() if line.strip()]
    except OSError:
        return False        # the driver never reached the revalidation hand-off: nothing says the stage ran
    if stage in remaining:
        print('revalidate: the driver stopped before running %s (a gate was reopened or an approval is missing)' % stage,
              file=sys.stderr)
        return False
    return True


def run(root, dry_run=False, runner=None, out=sys.stdout, supervisor=True, ask=None):
    """Returns the process exit code. `supervisor=False` (or --no-supervisor) uses the deterministic plan alone."""
    root = Path(root)
    why, rows = plan(root)
    names, mode, info, statement = NAMES, 'fingerprints', None, None
    if why == 'no-passes':
        # No stage fingerprints were ever recorded (a project built before they existed). The attestation is the baseline instead.
        try:
            import revalidate_attestation as ra
            statement = ra.load(root)[1]
            info = ra.plan(root, statement)
        except Exception as error:      # noqa: BLE001 - nothing to compare with is a refusal, never a traceback
            detail = error.args[0] if error.args else error
            detail = ' '.join(map(str, detail)) if isinstance(detail, (list, tuple)) else detail
            print('revalidate: no recorded passes exist (no-passes) and there is no attestation to compare with (%s); no stage run'
                  % detail, file=out)
            return 2
        rows, names, mode, why = info['rows'], list(ra.STAGES), 'attestation', None
        print('baseline: the attestation (no stage fingerprints were recorded for this project)', file=out)
    if why:
        print('revalidate: no recorded passes exist (%s); no stage run' % why, file=out)
        return 2
    notes = []
    if supervisor:
        # The supervisor may only add stages to this plan; see revalidate_planner. Headless: one bounded model call.
        import revalidate_planner
        rows, notes = revalidate_planner.refine(root, rows, names, ask=ask)
    for r in rows:
        print('%-18s %-12s %s' % (r['stage'], r['action'], r['reason']), file=out)
    for note in notes:
        print(note, file=out)
    if mode == 'attestation':
        return _finish_from_attestation(root, rows, info, statement, dry_run, out)
    cur_readme = _file(root / 'README.md')
    if any((_read(root, r['stage']) or {}).get('readme', cur_readme) != cur_readme for r in rows):
        print('README.md changed; 0 stages read it; %d stages reused' % sum(r['action'] == 'reuse' for r in rows), file=out)
    if all(r['action'] == 'reuse' for r in rows):
        _maybe_reissue(root, dry_run, out)
    _attestation_line(root, out)
    if dry_run:
        return 0 if all(r['action'] == 'reuse' for r in rows) else (1 if any(r['action'] == 'needs-review' for r in rows) else 0)
    if any(r['action'] == 'needs-review' for r in rows):
        return 1
    todo = [r['stage'] for r in rows if r['action'] == 'run']
    if not todo:
        return 0
    write_plan(root, rows)
    for n in todo:
        _invalidate(root, n)
    runner = runner or default_runner
    for n in todo:
        try:
            result = runner(n, root)
        except Exception as e:
            print('revalidate: %s runner error: %s' % (n, e), file=out)
            result = 'failed'
        if result == 'pass' or result is True or (isinstance(result, int) and not isinstance(result, bool) and result == 0):
            record(n, root)
            print('%-18s pass' % n, file=out)
        else:
            print('%-18s %s' % (n, 'blocked' if result == 'blocked' else 'failed'), file=out)
            return 1
    return 0


def _maybe_reissue(root, dry_run, out):
    """With every stage reusable, bring a stale attestation up to date when only documentation changed. Never raises."""
    try:
        import revalidate_attestation as ra
        statement = ra.load(root)[1]
        info = ra.plan(root, statement)
        if ra.eligible(info):
            _report_reissue(root, info, statement, dry_run, out)
    except Exception:                   # noqa: BLE001 - no attestation, or none usable: nothing to refresh
        return


def _report_reissue(root, info, statement, dry_run, out):
    import revalidate_attestation as ra
    ok, message = ra.reissue(root, info, statement, dry_run=dry_run)
    print('attestation: ' + message, file=out)
    if ok and not dry_run:
        print('  commit the changed files together with .uncle/attestation.json and .uncle/attestation.sig; `uncle verify` checks the '
              'committed tree.', file=out)
    return ok


def _finish_from_attestation(root, rows, info, statement, dry_run, out):
    """The tail of a revalidation planned from the attestation: report the change, re-issue the attestation if nothing the change
    touches needs to run again, and say what is left. Exit 0 only when no stage must run."""
    import revalidate_attestation as ra
    changed = info['changed']
    if changed:
        print('changed since the attestation: %s%s' % (', '.join(changed[:8]), ' and %d more' % (len(changed) - 8) if len(changed) > 8 else ''),
              file=out)
    elif info['stale'] and changed is None:
        print('changed since the attestation: cannot be listed (the attested tree is not in this repository)', file=out)
    else:
        print('no project file changed since the attestation', file=out)
    info = dict(info, rows=rows)
    if ra.eligible(info):
        _report_reissue(root, info, statement, dry_run, out)
    elif info['stale']:
        print('attestation: stale (it covers tree %s; the project is now %s) and cannot be re-issued while a stage the change touches '
              'must run again' % (info['short'](info['baseline']), info['short'](info['current'])), file=out)
    pending = [r['stage'] for r in rows if r['action'] == 'run']
    if pending:
        print('%d stage(s) must run again: %s' % (len(pending), ', '.join(pending)), file=out)
        print('This project was built without stage fingerprints, so revalidation cannot run its stages yet. `uncle --audit` re-runs only '
              'the final audit; `uncle --change-request --attended` re-runs the full change flow.', file=out)
        return 1
    return 0


def _attestation_line(root, out):
    """Informational only: never affects reuse and never writes."""
    verify = Path(__file__).resolve().parent.parent / 'uncle-verify.py'
    try:
        # From the project's own directory: a positional argument to the verifier names a PR, not a path.
        r = subprocess.run([sys.executable, '-B', str(verify)], cwd=str(root), capture_output=True, text=True, timeout=120)
        lines = (r.stdout or r.stderr).strip().splitlines()
        # The verdict is a line of its own; the verifier may print an explanation after it, so the last line is not it.
        verdict = next((l.strip() for l in reversed(lines)
                        if l.strip() in ('VERIFIED', 'NOT VERIFIED', 'NOT HUMAN VERIFIED') or l.startswith('INTEGRITY ONLY')), None)
        print('attestation: ' + (verdict or (lines[-1] if lines else 'exit %d' % r.returncode)), file=out)
    except Exception as e:
        print('attestation: unavailable (%s)' % e, file=out)


def main(argv):
    args = list(argv)
    root = Path.cwd()
    if len(args) >= 2 and args[0] == '--root':
        root, args = Path(args[1]), args[2:]
    if args[:1] == ['record'] and len(args) == 2:
        try:
            record(args[1], root)
        except Exception as e:
            print('revalidate: record %s failed: %s' % (args[1], e), file=sys.stderr)
            return 1
        return 0
    if args[:1] == ['run'] and set(args[1:]) <= {'--dry-run', '--no-supervisor'}:
        return run(root, dry_run='--dry-run' in args, supervisor='--no-supervisor' not in args)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
