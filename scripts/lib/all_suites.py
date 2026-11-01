"""Run every Python and shell suite in one pool, longest first, sized to the machine.

The two suite runners each default to 16 workers, so running both at once put 32 workers on a 14-core machine, and
timing-sensitive suites failed under that load. gates-test.sh also runs its 22 groups in a pool of its own inside one slot.
Here there is a single pool: every Python suite, every shell suite except gates-test.sh, and each gates group as its own
entry. Entries start in order of recorded cost (scripts/tests/suite-weights.tsv), so the long ones begin first and the
short ones fill the gaps; the wall time approaches the larger of the longest entry and the total work over the worker count.

    all_suites.py [JOBS]        JOBS defaults to one per available core (cpu_jobs.py; WORKFLOW_VERIFY_JOBS overrides)
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
from shell_suites import WEIGHTS, isolate_git, run_commands

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


def run(jobs):
    update = os.environ.get('UNCLE_UPDATE_SUITE_WEIGHTS') == '1'   # read before isolation clears UNCLE_* variables
    isolate_git()
    os.environ.setdefault('UNCLE_MODEL_REFRESH', '0')
    commands = build_commands()
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
        WEIGHTS.write_text(''.join(f'{seconds:.1f}\t{name}\n' for seconds, name in sorted(rows, reverse=True)), encoding='utf-8')
        print(f'Wrote {len(rows)} suite weights to {WEIGHTS}.', flush=True)
    return status


if __name__ == '__main__':
    raise SystemExit(run(int(sys.argv[1]) if len(sys.argv) > 1 else default_jobs()))
