"""Continuous admission for model units, shared by overlapping shell fan-outs.

A lease covers one unit, including its private validation/retry. Only the shell
that owns a unit waits for it; packet collation retains the stage's stable order.
No threads, model SDK, credentials, or network are needed by the scheduler.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def config_values():
    path = Path(os.environ.get('UNCLE_CONFIG') or
                Path(os.environ.get('PROJECT_ROOT', os.getcwd()), '.uncle/config'))
    values = {}
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            parts = line.split('#', 1)[0].split(None, 1)
            if len(parts) == 2:
                values.setdefault(parts[0], parts[1].strip())
    except FileNotFoundError:
        pass
    return values


def option(runner, stage, name, default, config=None):
    from self_hosted import config_stage
    values = config_values() if config is None else config
    parent = config_stage(stage, values)
    prefix = 'WORKFLOW_' + runner.upper().replace('-', '_') + '_' + name.upper().replace('-', '_')
    for suffix in dict.fromkeys((stage, parent, '')):
        key = prefix + ('_' + suffix.upper().replace('-', '_') if suffix else '')
        if key in os.environ:
            return os.environ[key].strip().lower()
    for scope in dict.fromkeys((stage, parent, runner)):
        if scope + '.' + name in values:
            return values[scope + '.' + name].strip().lower()
    return str(default)


def granularity(runner, stage='updated-plan', config=None):
    value = option(runner, stage, 'granularity', 'small' if runner == 'self-hosted' else 'large', config)
    if value not in ('small', 'large'):
        raise ValueError('granularity must be small or large')
    return value


def group_size(runner, stage='updated-plan', small=1, large=2, config=None):
    """Stages supply their existing large size; slicing policy stays with them."""
    values = config_values() if config is None else config
    # Explicit legacy pools keep their existing slice size until a profile is
    # selected. New installations use the provider's small/large default.
    legacy = os.environ.get('WORKFLOW_SELF_HOSTED_STAGE_JOBS') or values.get('self-hosted.stage-jobs')
    if runner == 'self-hosted' and legacy and not option(runner, stage, 'granularity', '', values):
        return large
    return small if granularity(runner, stage, values) == 'small' else large


def capacity(runner, stage, config=None):
    values = config_values() if config is None else config
    value = option(runner, stage, 'max-concurrency', '', values)
    if not value and runner == 'self-hosted':
        # Preserve the old explicitly configured 1-8 pool without limiting the
        # new setting to eight. Its historical invalid-value fallback is four.
        legacy = os.environ.get('WORKFLOW_SELF_HOSTED_STAGE_JOBS', values.get('self-hosted.stage-jobs', ''))
        if legacy:
            if legacy not in tuple(str(n) for n in range(1, 9)):
                print('Invalid self-hosted.stage-jobs (use 1–8); using 4.', file=sys.stderr)
                return 4
            return int(legacy)
    if not value:
        return 24 if runner == 'self-hosted' else 0
    if not value.isdecimal() or not 1 <= int(value) <= 256:
        raise ValueError('max-concurrency must be an integer from 1 to 256')
    return int(value)


def processes():
    rows = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,stat=,lstart='], text=True)
    result = {}
    for row in rows.splitlines():
        parts = row.split(None, 3)
        if len(parts) == 4:
            result[int(parts[0])] = (int(parts[1]), parts[2], parts[3])
    return result


def alive(pid, stamp, table):
    row = table.get(pid)
    return bool(row and not row[1].startswith('Z') and row[2] == stamp)


@contextlib.contextmanager
def locked(directory):
    import fcntl
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def acquire(directory, limit, pid, owner):
    directory = Path(directory)
    pid = pid or os.getppid()
    table = processes()
    if pid not in table or owner not in table:
        raise RuntimeError('unit or driver exited before admission')
    record = dict(pid=pid, stamp=table[pid][2], owner=owner,
                  owner_stamp=table[owner][2], active=False)
    path = directory / ('%d.json' % pid)
    while True:
        with locked(directory):
            table = processes()
            if (directory.parent / 'cancelled').exists() or not alive(owner, record['owner_stamp'], table):
                path.unlink(missing_ok=True)
                raise RuntimeError('model work cancelled')
            active = 0
            for entry in directory.glob('*.json'):
                unit = json.loads(entry.read_text())
                if not alive(unit['pid'], unit['stamp'], table):
                    entry.unlink()
                elif unit['active']:
                    active += 1
            if not limit or active < limit:
                record['active'] = True
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(record), encoding='utf-8')
            temporary.replace(path)
            if record['active']:
                print(pid, flush=True)
                return
        time.sleep(0.025)


def stop_trees(roots):
    table = processes()
    victims = set(roots)
    while True:
        children = {pid for pid, row in table.items() if row[0] in victims}
        if children <= victims:
            break
        victims |= children
    # Freeze first so a shell cannot launch another child during cancellation.
    victims.discard(os.getpid())
    for sig in (signal.SIGSTOP, signal.SIGTERM, signal.SIGCONT):
        for pid in victims:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        current = processes()
        if not any(alive(pid, table[pid][2], current) for pid in victims if pid in table):
            return
        time.sleep(0.025)
    current = processes()
    for pid in victims:
        if pid in table and alive(pid, table[pid][2], current):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def cancel(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'cancelled').touch()
    roots = []
    for pool in directory.iterdir():
        if not pool.is_dir():
            continue
        with locked(pool):
            table = processes()
            for path in pool.glob('*.json'):
                unit = json.loads(path.read_text())
                if alive(unit['pid'], unit['stamp'], table):
                    roots.append(unit['pid'])
    stop_trees(roots)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('capacity', 'granularity', 'group-size', 'acquire', 'release', 'cancel'))
    parser.add_argument('args', nargs='*')
    options = parser.parse_args()
    command, args = options.command, options.args
    try:
        if command == 'capacity':
            print(capacity(*args))
        elif command == 'granularity':
            print(granularity(*args))
        elif command == 'group-size':
            print(group_size(*args))
        elif command == 'acquire':
            acquire(args[0], *map(int, args[1:]))
        elif command == 'release':
            with locked(Path(args[0])):
                Path(args[0], args[1] + '.json').unlink(missing_ok=True)
        else:
            cancel(args[0])
    except (ValueError, RuntimeError) as error:
        parser.exit(2, 'unit scheduler: %s\n' % error)


if __name__ == '__main__':
    main()
