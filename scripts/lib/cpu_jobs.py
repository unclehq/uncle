"""How many test workers this machine should run at once.

Test suites and verification commands are CPU-bound (process spawns, git, interpreters): measured here, workers beyond the
core count made the suite slower, not faster (see gate_suites.py). So the default is one worker per core this process may use,
on whatever machine uncle runs on. WORKFLOW_VERIFY_JOBS overrides it.

    cpu_jobs.py        # prints the worker count
"""
import os
import sys

MAX_JOBS = 64


def available_cores():
    try:
        return len(os.sched_getaffinity(0))      # honours taskset and container CPU sets where the OS has it
    except (AttributeError, OSError):
        return os.cpu_count() or 4


def default_jobs():
    """WORKFLOW_VERIFY_JOBS when it is a valid number, otherwise one worker per available core."""
    raw = os.environ.get('WORKFLOW_VERIFY_JOBS', '')
    if raw.isdigit() and 1 <= int(raw) <= MAX_JOBS:
        return int(raw)
    return max(1, min(available_cores(), MAX_JOBS))


TEST_MAX_JOBS = 4


def default_test_jobs():
    """Workers for uncle's own regression suites: a third of the cores, at most four.

    One worker per core kept the machine saturated for minutes (fans, a sluggish desktop) to save a little wall time on work that
    is mostly waiting on process spawns. The test runners also lower their own priority (shell_suites.lower_priority), so a
    run in the background never starves what the person is doing. WORKFLOW_VERIFY_JOBS still overrides, and project
    verification (green-check.sh) keeps `default_jobs` unchanged.
    """
    raw = os.environ.get('WORKFLOW_VERIFY_JOBS', '')
    if raw.isdigit() and 1 <= int(raw) <= MAX_JOBS:
        return int(raw)
    return max(1, min(available_cores() // 3, TEST_MAX_JOBS))


if __name__ == '__main__':
    sys.stdout.write(f'{default_test_jobs() if sys.argv[1:] == ["tests"] else default_jobs()}\n')
