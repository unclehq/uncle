"""Run every Python and shell suite in one pool, longest first, sized to the machine.

The two suite runners each default to 16 workers, so running both at once put 32 workers on a 14-core machine, and
timing-sensitive suites failed under that load. gates-test.sh also runs its 22 groups in a pool of its own inside one slot.
Here there is a single pool: every Python suite, every shell suite except gates-test.sh, and each gates group as its own
entry. Entries start in order of recorded cost (scripts/tests/suite-weights.tsv), so the long ones begin first and the
short ones fill the gaps; the wall time approaches the larger of the longest entry and the total work over the worker count.

    all_suites.py [JOBS] [--shard I/N] [--list]
        JOBS defaults to one per available core (cpu_jobs.py; WORKFLOW_VERIFY_JOBS overrides).
        --shard I/N runs shard I (1-based) of N: the entries are dealt out longest-first to the least-loaded shard by recorded
        weight, so N machines (or CI jobs) each run about 1/N of the work and every entry runs in exactly one shard.
        --list prints the entry names of the chosen shard (or all of them) without running anything.
    UNCLE_UPDATE_SUITE_WEIGHTS=1 rewrites the weights file from this run's measured times.
"""
import glob
import os
from pathlib import Path
import sys
import tempfile

from cpu_jobs import default_jobs
from gate_suites import gate_commands
from process_tree import bash_executable
from suite_split import expand
from python_suites import suite_command
from shell_suites import UNKNOWN_WEIGHT, WEIGHTS, isolate_git, ordered, read_weights, run_commands

def build_commands():
    commands = {}
    for path in sorted(glob.glob('scripts/tests/*-test.py')):
        path = Path(path).as_posix()
        command = suite_command(path)
        plain = command[:2] == [sys.executable, '-B'] and os.environ.get('WORKFLOW_PYTHON_TESTS_RUNNER', 'python') == 'python'
        commands.update(expand(path, 'python', path, command) if plain else {path: command})
    for path in sorted(glob.glob('scripts/tests/*-test.sh')):
        path = Path(path).as_posix()
        if path == 'scripts/tests/gates-test.sh':
            commands.update(gate_commands(path))
        else:
            commands.update(expand(path, 'shell', path, [bash_executable(), path]))
    return commands


def shard_of(commands, weights, index, count):
    """The entries of shard `index` (1-based) of `count`: longest-processing-time-first dealing, deterministic from the weights."""
    loads, assigned = [0.0] * count, [[] for _ in range(count)]
    for name in commands:                       # already longest-first
        target = min(range(count), key=lambda i: (loads[i], i))
        loads[target] += weights.get(name, UNKNOWN_WEIGHT)
        assigned[target].append(name)
    return {name: commands[name] for name in assigned[index - 1]}


def run(jobs, shard=None, list_only=False):
    update = os.environ.get('UNCLE_UPDATE_SUITE_WEIGHTS') == '1'   # read before isolation clears UNCLE_* variables
    isolate_git()
    os.environ.setdefault('UNCLE_MODEL_REFRESH', '0')
    weights = read_weights()
    commands = ordered(build_commands(), weights)
    if shard:
        commands = shard_of(commands, weights, *shard)
        print(f'Shard {shard[0]} of {shard[1]}: {len(commands)} entries, about {sum(weights.get(n, UNKNOWN_WEIGHT) for n in commands):.0f}s of recorded work.', flush=True)
    if list_only:
        print('\n'.join(commands))
        return 0
    timings = None
    if update:
        handle, timings = tempfile.mkstemp(prefix='uncle-suite-weights-')
        os.close(handle)
        os.environ['WORKFLOW_SUITE_TIMINGS'] = timings
    status = run_commands(jobs, commands, kind='all')
    if update and status == 0:
        rows = []
        for line in Path(timings).read_text(encoding='utf-8').splitlines():
            seconds, _, rest = line.partition('\t')
            rows.append((float(seconds), rest.partition('\t')[2]))
        merged = {name: seconds for name, seconds in weights.items()}     # a shard run only measured its own entries
        merged.update({name: seconds for seconds, name in rows})
        WEIGHTS.write_text(''.join(f'{seconds:.1f}\t{name}\n' for name, seconds in sorted(merged.items(), key=lambda item: -item[1])), encoding='utf-8')
        print(f'Wrote {len(merged)} suite weights to {WEIGHTS}.', flush=True)
    return status


if __name__ == '__main__':
    args = sys.argv[1:]
    shard, list_only, jobs = None, False, default_jobs()
    while args:
        arg = args.pop(0)
        if arg == '--list':
            list_only = True
        elif arg == '--shard':
            index, _, count = args.pop(0).partition('/')
            shard = (int(index), int(count))
            if not 1 <= shard[0] <= shard[1]:
                raise SystemExit('--shard I/N needs 1 <= I <= N')
        else:
            jobs = int(arg)
    raise SystemExit(run(jobs, shard, list_only))
