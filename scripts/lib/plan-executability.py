#!/usr/bin/env python3
"""Evidence-bound plan assessment and durable recovery records (no probe execution)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time

STATE = Path('.uncle/workflow')
ASSESS = STATE / 'plan-executability'
JOURNAL = STATE / 'plan-recovery.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(tmp, path)


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def manifest(root, plan):
    change = plan == 'CHANGE_PLAN.md'
    files = [plan, 'ADVERSARIAL_REVIEW.md',
             'CHANGE_REQUEST.md' if change else 'REQUIREMENTS.md',
             'CHANGE_SPEC.md' if change else 'REQUIREMENTS_INTERPRETATION.md',
             os.environ.get('UNCLE_CONFIG', '.uncle/config'), str(STATE / 'authority-answer.json')]
    adapters = [str(x.relative_to(root)) for x in Path(root).glob('scripts/agent-*.sh')] + ['scripts/lib/native_stage.py',
                'scripts/lib/stage-config.sh', 'scripts/lib/plan-executability.py', 'scripts/lib/windows_driver.py']
    result = {'version': 1, 'root': str(Path(root).resolve()), 'plan': plan, 'files': {p: file_hash(p) for p in files},
              'adapters': {str(Path(root).resolve() / p): file_hash(Path(root) / p) for p in adapters},
              'settings': {k: v for k, v in os.environ.items()
                           if k.startswith(('WORKFLOW_AGENT_CMD', 'WORKFLOW_REVIEWER_CMD',
                                            'WORKFLOW_MODEL', 'WORKFLOW_EFFORT', 'WORKFLOW_CODEX_',
                                            'UNCLE_STEERING', 'UNCLE_CONFIG', 'UNCLE_SELF_HOSTED_MODEL'))}}
    # Record hashes, never executable contents or credentials, for selected commands.
    result['commands'] = {v: file_hash(v) for k, v in result['settings'].items() if '_CMD' in k}
    result['discovery'] = {name: shutil.which(name) for name in ('codex', 'claude', 'cline')}
    result['digest'] = digest(result)
    return result


def ids_in(path, prefix):
    return set(re.findall(r'\b' + prefix + r'-\d+\b', Path(path).read_text())) if Path(path).exists() else set()


def indexed(rows, label):
    require(isinstance(rows, list), label + ' must be an array')
    result = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get('id'), str) and row['id'], label + ': missing id')
        require(row['id'] not in result, label + ': duplicate ' + row['id'])
        result[row['id']] = row
    return result


def fields(row, names):
    for name in names.split():
        require(name in row and row[name] not in ('', None), row.get('id', 'assessment') + ': missing ' + name)


def validate(a, m):
    require(manifest(m['root'], m['plan'])['digest'] == m['digest'], 'manifest inputs changed')
    require(a.get('version') == 1, 'unsupported assessment version')
    require(a.get('input_digest') == m['digest'], 'stale assessment input digest')
    r = indexed(a.get('restrictions'), 'restrictions')
    c = indexed(a.get('capabilities'), 'capabilities')
    f = indexed(a.get('findings'), 'findings')
    steps = indexed(a.get('steps'), 'steps')
    decisions = indexed(a.get('decisions'), 'decisions')
    prereqs = indexed(a.get('prerequisites'), 'prerequisites')
    spec = 'CHANGE_SPEC.md' if m['plan'] == 'CHANGE_PLAN.md' else 'REQUIREMENTS_INTERPRETATION.md'
    requirements = ids_in(spec, 'AC')
    require(set(a.get('requirement_ids', [])) == requirements, 'lost or extra acceptance IDs')
    require(set(f) == ids_in('ADVERSARIAL_REVIEW.md', 'AR'), 'lost or extra reviewer findings')
    for archived in ASSESS.glob('archive-*/assessment.json'):
        old = read(archived)
        require({x['id'] for x in old['findings']} <= set(f), 'suppressed historical reviewer finding')
        for item in old['restrictions']:
            if item['source_kind'] != 'DESIGN':
                require(item['id'] in r, 'lost genuine constraint')
                current = r[item['id']]
                require(all(current.get(k) == item[k] for k in ('source_kind', 'source_location', 'property', 'requirement_ids')), 'weakened genuine constraint')
    require(ids_in(m['plan'], 'R') <= set(r), 'missing plan restrictions')
    require(ids_in(m['plan'], 'S') <= set(steps), 'missing plan steps')
    evidence = {}
    for item in c.values():
        fields(item, 'binding required_phase status evidence command observed_result dependent_ids')
        require(item['binding'] == m['digest'], item['id'] + ': wrong runner/config binding')
        require(item['required_phase'] in ('CODING', 'LIVE_VERIFICATION'), 'invalid capability phase')
        require(item['status'] in ('SUPPORTED', 'UNSUPPORTED', 'UNVERIFIED'), 'invalid capability status')
        require(isinstance(item['evidence'], list) and item['evidence'], 'missing support evidence')
        for ev in item['evidence']:
            fields(ev, 'path sha256')
            require(file_hash(ev['path']) == ev['sha256'], 'absent/stale evidence: ' + ev['path'])
            evidence[ev['path']] = ev['sha256']
    for item in r.values():
        fields(item, 'source_kind source_location requirement_ids property mechanism rationale capability_ids')
        require(item['source_kind'] in ('USER', 'REPOSITORY', 'PLATFORM', 'DESIGN'), 'invalid provenance')
        require(set(item['requirement_ids']) <= requirements, 'unknown restriction requirement')
        require(set(item['capability_ids']) <= set(c), 'unknown restriction capability')
        require(item['capability_ids'], 'restriction lacks feasibility evidence')
    for item in f.values():
        fields(item, 'property disposition evidence restriction')
        require(item['restriction'] in r, 'finding has unknown restriction')
        require(item['property'] == r[item['restriction']]['property'], 'finding property lost')
    for item in decisions.values():
        fields(item, 'question alternatives tradeoff')
        require(len(item['alternatives']) >= 2, 'decision needs alternatives')
    for item in prereqs.values():
        fields(item, 'phase status check_ids commands evidence_paths')
        require(item['phase'] in ('CODING', 'LIVE_VERIFICATION'), 'invalid prerequisite phase')
        require(item['status'] in ('SUPPORTED', 'UNSUPPORTED', 'UNVERIFIED'), 'invalid prerequisite status')
        require(item['check_ids'] and item['commands'], 'prerequisite lacks approved checks')
    eligible, visiting, done = set(), set(), set()
    def visit(sid):
        require(sid in steps, 'unknown step dependency: ' + sid)
        require(sid not in visiting, 'cyclic step dependencies')
        if sid in done:
            return sid in eligible
        visiting.add(sid)
        step = steps[sid]
        fields(step, 'paths requirement_ids depends_on capability_ids decision_ids')
        require(set(step['requirement_ids']) <= requirements, 'unknown step requirement')
        require(set(step['capability_ids']) <= set(c), 'unknown step capability')
        require(set(step['decision_ids']) <= set(decisions), 'unknown step decision')
        require(all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in step['paths']), 'unsafe step path')
        dependencies = [visit(dep) for dep in step['depends_on']]
        if all(dependencies) and not step['decision_ids'] and all(c[x]['status'] == 'SUPPORTED' or c[x]['required_phase'] == 'LIVE_VERIFICATION' for x in step['capability_ids']):
            eligible.add(sid)
        visiting.remove(sid)
        done.add(sid)
        return sid in eligible
    for sid in steps:
        visit(sid)
    verdict = a.get('verdict')
    require(verdict in ('READY', 'REVISE', 'DECISION'), 'invalid verdict')
    unsupported = [x['id'] for x in c.values() if x['required_phase'] == 'CODING' and x['status'] != 'SUPPORTED']
    unsupported += [x['id'] for x in prereqs.values() if x['phase'] == 'CODING' and x['status'] != 'SUPPORTED']
    require(verdict != 'READY' or not (unsupported or decisions), 'false READY: ' + ', '.join(unsupported or decisions))
    require(verdict != 'DECISION' or decisions, 'DECISION has no question')
    return {'verdict': verdict, 'eligible_steps': sorted(eligible), 'evidence': evidence}


def journal():
    if not JOURNAL.exists():
        return {'version': 1, 'design_count': 0, 'failures': [], 'phase': 'IDLE', 'launches': {}}
    j = read(JOURNAL)
    require(j.get('version') == 1 and isinstance(j.get('design_count'), int) and isinstance(j.get('launches'), dict), 'invalid recovery journal')
    require(j.get('phase') in ('IDLE', 'REVISE', 'DESIGN', 'AUTHORITY', 'WAIT_LIVE', 'VERIFYING', 'VERIFIED'), 'invalid recovery phase')
    require(0 <= j['design_count'] <= 2 and isinstance(j.get('failures'), list), 'invalid recovery bound')
    require(all(x.get('status') in ('STARTED', 'FINISHED') for x in j['launches'].values()), 'invalid launch status')
    return j


def blockers(path):
    text = Path(path).read_text() if Path(path).exists() else ''
    blocks = re.findall(r'```plan-blockers\s*\n(.*?)\n```', text, re.S)
    require(len(blocks) <= 1, 'duplicate blocker blocks')
    require('```plan-blockers' not in text or blocks, 'malformed blocker fence')
    if not blocks:
        return []
    rows = indexed(json.loads(blocks[0]), 'blockers')
    for row in rows.values():
        fields(row, 'class requirement_ids restriction_ids evidence independent_work')
        require(row['class'] in ('DESIGN', 'AUTHORITY', 'LIVE_VERIFICATION', 'CODING'), 'invalid blocker class')
        if row['class'] == 'AUTHORITY':
            fields(row, 'question alternatives')
    return list(rows.values())


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def lock_run(command):
    """One supervised launch, or several when an enabled supervisor permits a retry.

    Each retry re-enters `_lock_run_once`: the lock is released and
    reacquired, and the driver runs every approval, integrity and repair
    check again. With supervision disabled this is exactly one launch.
    """
    # No bytecode: this import runs inside project checkouts, and a stray
    # __pycache__ in a copied lib would show up in the change diff.
    sys.dont_write_bytecode = True
    from supervisor import supervised_lock_run
    from build_timing import BuildTiming
    # The timing environment must exist before supervision launches the driver
    # so stage streams, tools, caches and retries all share the same run ID.
    with BuildTiming(STATE) as timing:
        timing.status = supervised_lock_run(
            _lock_run_once, command, STATE, Path(__file__).resolve().parents[2])
        return timing.status


def _lock_run_once(command):
    """Permanent inode, supervised process group, orphan detection across driver families."""
    if os.name == 'nt':
        from windows_driver import lock_run as windows_lock_run
        return windows_lock_run(command, STATE)
    import fcntl
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'driver.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('another workflow holds this checkout')
        lock.seek(0)
        previous = lock.read()
        if previous:
            owner = json.loads(previous)
            require('pgid' in owner, 'malformed prior lock owner')
            if owner['pgid']:
                require(not alive(-owner['pgid']), 'previous workflow process group still alive')
        legacy = STATE / 'lock/pid'
        if legacy.exists():
            holder = int(legacy.read_text().strip())
            if alive(holder):
                print(f'Refusing to start: another change-workflow.sh run (pid {holder}) holds this checkout.', file=sys.stderr)
                return 1
            print(f'Clearing stale lock {legacy.parent} (pid {holder} is not running).', flush=True)
            legacy.unlink()
            legacy.parent.rmdir()
        # The child waits until its identity is durably recorded before executing Bash.
        rfd, wfd = os.pipe()
        env = dict(os.environ, UNCLE_DRIVER_SUPERVISED='1')
        child = subprocess.Popen([sys.executable, '-c',
            'import os,sys; token=os.read(int(sys.argv[1]),1); token == b"1" or sys.exit(125); os.execvpe(sys.argv[2],sys.argv[2:],os.environ)',
            str(rfd), *command], env=env, pass_fds=(rfd,), process_group=0)
        os.close(rfd)
        owner = {'supervisor': os.getpid(), 'pid': child.pid, 'pgid': child.pid,
                 'start': {'created_ns': time.time_ns(), 'nonce': os.urandom(16).hex()}}
        def save(value):
            lock.seek(0); lock.truncate(); lock.write(json.dumps(value)); lock.flush(); os.fsync(lock.fileno())
        save(owner)
        tty_group = None
        old_ttou = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
        if os.isatty(0):
            tty_group = os.tcgetpgrp(0)
            os.tcsetpgrp(0, child.pid)
        def stop(signum, _frame):
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass
        old = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
        os.write(wfd, b'1'); os.close(wfd)
        try:
            rc = child.wait()
        finally:
            stop(signal.SIGTERM, None)
            for _ in range(50):
                if not alive(-child.pid):
                    break
                time.sleep(.02)
            if alive(-child.pid):
                stop(signal.SIGKILL, None)
            if tty_group is not None:
                os.tcsetpgrp(0, tty_group)
            signal.signal(signal.SIGTTOU, old_ttou)
            for s, handler in old.items():
                signal.signal(s, handler)
            if not alive(-child.pid):
                save({'pgid': None})
        return rc if rc >= 0 else 128 - rc


def source_state():
    paths = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z']).decode().split('\0')
    reports = {'IMPLEMENTATION_NOTES.md', 'CHANGE_TEST_REPORT.md', 'AUTOMATED_TEST_REPORT.md'}
    return {p: file_hash(p) for p in sorted(set(paths)) if p and not p.startswith('.uncle/') and p not in reports}


def delivery_summary(j):
    notes = Path('IMPLEMENTATION_NOTES.md')
    text = notes.read_text() if notes.exists() else ''
    if not re.search(r'^##\s+Acceptance delivery\s*$', text, re.M | re.I):
        # Only prompts/change/implement-change.md (the existing-code change
        # driver) tells an agent to write this section, with AC-numbered
        # rows matching CHANGE_SPEC.md. A stagegate.sh (new-application) plan
        # was never asked for one, so its IMPLEMENTATION_NOTES.md structurally
        # never has it -- writing a permanently header-only file here is not
        # "delivery not yet reported", it is evidence this driver never
        # produces. A real run left that empty file in TEST_REVIEW's evidence
        # packet, and a reviewer read the header-only file as a live defect
        # ("still header-only despite three claimed rewrites") that no repair
        # pass could ever fix, since nothing was ever going to populate it.
        # Leaving the file absent instead reads as the ordinary "missing or
        # unreadable" status every other not-yet-applicable file gets.
        (STATE / 'delivery-summary.tsv').unlink(missing_ok=True)
        return 0
    rows = []
    for line in text.splitlines():
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(cells) == 4 and re.fullmatch(r'AC-\d+', cells[0]):
            status = 'INCOMPLETE'
            # Waivers are validated by the unchanged completion/waiver gate.
            waiver = STATE / 'waivers' / cells[0]
            if waiver.exists() and cells[1] != 'IMPLEMENTED':
                status = 'WAIVED'
            elif cells[1] == 'IMPLEMENTED' and j.get('phase') not in ('WAIT_LIVE', 'VERIFYING'):
                green = STATE / 'green-check.current.tsv'
                if green.exists() and green.read_text().strip() and all(x.startswith('0\t') for x in green.read_text().splitlines()):
                    status = 'VERIFIED'
            rows.append('\t'.join([cells[0], status, 'IMPLEMENTATION_NOTES.md']))
    (STATE / 'delivery-summary.tsv').write_text('ID\tStatus\tEvidence\n' + '\n'.join(rows) + '\n')
    if any('\tWAIVED\t' in row for row in rows):
        print('Acceptance includes waivers; waived rows are not verified delivery.')
    return 0


def runtime(action, args=()):
    if action == 'summary':
        # Reporting delivery and waivers does not require an executability review.
        recovery = journal() if os.environ.get('WORKFLOW_EXECUTABILITY_REVIEW') == '1' else {}
        return delivery_summary(recovery)
    j = journal()
    m = read(ASSESS / 'manifest.json')
    a = read(ASSESS / 'assessment.json')
    v = validate(a, m)
    if action == 'live-retry':
        require(j.get('phase') == 'WAIT_LIVE', 'no pending live verification')
        j.pop('live_fingerprint', None)
        atomic(JOURNAL, j)
        return 0
    if action == 'retry':
        active = j.get('active_launch')
        if active and j['launches'].get(active, {}).get('status') == 'STARTED':
            j['launches'][active] = {'status': 'FINISHED', 'interrupted': True, 'notes': file_hash('IMPLEMENTATION_NOTES.md')}
        j.pop('active_launch', None)
        j['retry'] = j.get('retry', 0) + 1
        atomic(JOURNAL, j)
        return 0
    if action == 'preflight-check':
        text = Path('PREFLIGHT_REPORT.md').read_text()
        parts = re.split(r'^##\s+(?:\d+\.\s*)?Acceptance gate\s*$', text, flags=re.M | re.I)
        if len(parts) == 2:
            gate = re.split(r'^## ', parts[1], maxsplit=1, flags=re.M)[0]
            live = {x for item in a['prerequisites'] if item['phase'] == 'LIVE_VERIFICATION' for x in [item['id'], *item['check_ids']]}
            for line in gate.splitlines():
                cells = [c.strip() for c in line.strip().strip('|').split('|')]
                if cells and cells[0] in live and any(c.startswith('BLOCKED') for c in cells):
                    raise ValueError('Correct PREFLIGHT_REPORT.md: live-only ' + cells[0] + ' belongs in Findings, not the coding Acceptance gate')
        return 0
    if action == 'snapshot':
        atomic(ASSESS / 'source-before.json', source_state())
        return 0
    if action == 'source-check':
        before = read(ASSESS / 'source-before.json'); after = source_state()
        changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
        if j.get('phase') == 'VERIFYING':
            atomic(ASSESS / 'verification-source-changes.json', sorted(changed))
            require(not changed, 'verification-only source mutation: ' + ', '.join(sorted(changed)))
        elif a['verdict'] == 'DECISION':
            allowed = {p for step in a['steps'] if step['id'] in v['eligible_steps'] for p in step['paths']}
            require(changed <= allowed, 'source mutation outside approved independent subset: ' + ', '.join(sorted(changed - allowed)))
        return 0
    if action == 'dispatch':
        if j.get('phase') == 'AUTHORITY':
            if j.get('authority_answer') == file_hash(STATE / 'authority-answer.json'):
                print(json.dumps(j.get('blockers', [])))
                return 23
            j['phase'] = 'IDLE'
            atomic(JOURNAL, j)
        if j.get('phase') == 'DESIGN':
            return 10
        if j.get('phase') == 'REVISE' and j.get('failed_plan_digest') == m['files'][m['plan']]:
            return 10
        if j.get('phase') == 'WAIT_LIVE':
            fingerprint = digest({p: file_hash(p) for item in a['prerequisites'] if item['phase'] == 'LIVE_VERIFICATION' for p in item['evidence_paths']})
            if j.get('live_fingerprint') == fingerprint:
                print('Live verification remains pending; prerequisite/evidence unchanged.')
                return 20
            j['live_fingerprint'] = fingerprint; j['phase'] = 'VERIFYING'
            atomic(JOURNAL, j)
            return 21
        require(j.get('phase') != 'VERIFYING', 'interrupted verification; explicit reconciliation required')
        if a['verdict'] == 'DECISION' and j.get('completed_subset') == digest([m['digest'], v['eligible_steps']]):
            print('Independent subset already executed; authority decision remains pending.')
            return 20
        active = j.get('active_launch')
        if active and j['launches'].get(active, {}).get('status') == 'STARTED':
            print('Previous source-writing attempt was interrupted; explicit retry required.')
            return 25
        key = digest([m['digest'], list(args), j.get('retry', 0)])
        previous = j['launches'].get(key)
        if previous:
            if previous['status'] != 'FINISHED':
                print('Previous source-writing attempt was interrupted; explicit retry required.')
                return 25
            require(previous.get('notes') == file_hash('IMPLEMENTATION_NOTES.md'), 'launch result/report changed; explicit reconciliation required')
            return 22
        j['active_launch'] = key
        j['launches'][key] = {'status': 'STARTED'}
        atomic(JOURNAL, j)
        return 0
    if action == 'classify':
        key = j.get('active_launch')
        if key:
            j['launches'][key] = {'status': 'FINISHED', 'notes': file_hash('IMPLEMENTATION_NOTES.md')}
            atomic(JOURNAL, j)
        rows = blockers('IMPLEMENTATION_NOTES.md')
        if any(row['class'] == 'DESIGN' for row in rows):
            j['blockers'] = rows; j['phase'] = 'DESIGN'; atomic(JOURNAL, j)
            return 10
        if any(row['class'] == 'AUTHORITY' for row in rows):
            j['blockers'] = rows; j['phase'] = 'AUTHORITY'
            j['authority_answer'] = file_hash(STATE / 'authority-answer.json')
            atomic(JOURNAL, j)
            print(json.dumps(rows)); return 20
        if any(row['class'] == 'LIVE_VERIFICATION' for row in rows):
            j['blockers'] = rows; j['phase'] = 'WAIT_LIVE'
            j['live_fingerprint'] = digest({p: file_hash(p) for item in a['prerequisites'] if item['phase'] == 'LIVE_VERIFICATION' for p in item['evidence_paths']})
            atomic(JOURNAL, j)
            print('Independent coding retained; live verification remains incomplete.'); return 20
        if a['verdict'] == 'DECISION':
            j['completed_subset'] = digest([m['digest'], v['eligible_steps']]); atomic(JOURNAL, j)
            print('Independent subset completed; authority decision remains pending.'); return 20
        if m['plan'] == 'UPDATED_PROJECT_PLAN.md' and a['requirement_ids']:
            check = subprocess.run([sys.executable, str(Path(__file__).with_name('implementation-completion.py')),
                                    'REQUIREMENTS_INTERPRETATION.md', 'IMPLEMENTATION_NOTES.md'], capture_output=True, text=True)
            if check.returncode:
                print(check.stdout.strip())
                if j.get('phase') == 'VERIFYING':
                    j['phase'] = 'WAIT_LIVE'; atomic(JOURNAL, j)
                    return 20
                return 24
        if j.get('phase') == 'VERIFYING':
            j['phase'] = 'VERIFIED'; atomic(JOURNAL, j)
        return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'lock-run':
        return lock_run(sys.argv[2:])
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['manifest', 'validate', 'render', 'blockers', 'recover', 'launch', 'result', 'lock-run', 'lock-child', 'dispatch', 'snapshot', 'source-check', 'classify', 'summary', 'retry', 'live-retry', 'preflight-check'])
    p.add_argument('args', nargs='*')
    ns = p.parse_args()
    args = ns.args
    if ns.action == 'lock-run':
        return lock_run(args)
    if ns.action == 'lock-child':
        owner = read(STATE / 'driver.lock')
        if os.name == 'nt':
            from windows_driver import child_valid
            require(child_valid(owner), 'driver is not the supervised lock owner')
            return 0
        require(owner.get('pid') == int(args[0]) and owner.get('supervisor') == int(args[1])
                and alive(int(args[1])) and owner.get('pgid') == os.getpgid(int(args[0])),
                'driver is not the supervised lock owner')
        return 0
    if ns.action == 'manifest':
        atomic(ASSESS / 'manifest.json', manifest(*args))
        return 0
    if ns.action in ('validate', 'render'):
        m = read(ASSESS / 'manifest.json')
        try:
            a = read(ASSESS / 'assessment.json')
        except json.JSONDecodeError as exc:
            raise ValueError('assessment.json is not valid JSON. The reviewer must return '
                             'the complete assessment as its final response; the driver saves it.') from exc
        require(isinstance(a, dict), 'assessment.json must contain one JSON object')
        result = validate(a, m)
        if ns.action == 'render':
            text = '# Plan executability\n\nInput digest: ' + m['digest'] + '\n\n'
            text += 'Verdict: ' + result['verdict'] + '\n\nExecutable steps: ' + ', '.join(result['eligible_steps']) + '\n\n'
            text += '```json\n' + json.dumps(a, indent=2) + '\n```\n'
            (ASSESS / 'assessment.md').write_text(text)
            atomic(ASSESS / 'validated.json', result)
        return {'READY': 0, 'REVISE': 10, 'DECISION': 11}[result['verdict']]
    if ns.action == 'blockers':
        rows = blockers(args[0]); print(json.dumps(rows))
        return 0
    if ns.action in ('dispatch', 'snapshot', 'source-check', 'classify', 'summary', 'retry', 'live-retry', 'preflight-check'):
        return runtime(ns.action, args)
    j = journal()
    if ns.action == 'recover':
        m = read(ASSESS / 'manifest.json'); a = read(ASSESS / 'assessment.json')
        identity = digest({k: v for k, v in m['files'].items() if k in ('CHANGE_REQUEST.md', 'CHANGE_SPEC.md', 'REQUIREMENTS.md', 'REQUIREMENTS_INTERPRETATION.md')})
        require(j.get('identity', identity) == identity, 'source/spec identity changed; explicit reconciliation required')
        j['identity'] = identity
        failure = digest({'restrictions': a['restrictions'], 'capabilities': [{k: v for k, v in c.items() if k != 'binding'} for c in a['capabilities']]})
        require(j['design_count'] < 2, 'two design revisions exhausted; explicit new authority required')
        require(failure not in j['failures'], 'same failed mechanism/evidence; explicit decision required')
        j['design_count'] += 1; j['failures'].append(failure); j['phase'] = 'REVISE'
        j['failed_plan_digest'] = m['files'][m['plan']]
        j['origin'] = (STATE / 'origin').read_text() if (STATE / 'origin').exists() else None
    elif ns.action == 'launch':
        key = args[0]
        require(key not in j['launches'], 'launch already recorded; explicit reconciliation required: ' + key)
        j['launches'][key] = {'status': 'STARTED'}
    elif ns.action == 'result':
        require(args[0] in j['launches'], 'missing launch intent')
        j['launches'][args[0]] = {'status': 'FINISHED', 'notes': file_hash('IMPLEMENTATION_NOTES.md')}
    atomic(JOURNAL, j)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('Plan executability: ' + str(exc), file=sys.stderr)
        sys.exit(12)
