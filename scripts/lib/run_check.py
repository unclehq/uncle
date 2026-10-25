#!/usr/bin/env python3
"""Run one verification command with a time limit: run_check.py -- <command...>

The driver's sequential check loop ran each approved command with no limit, so a
command that waits forever (a test runner probing a port that something else
holds without answering, for example) stalled the whole run with no output.  The
parallel runner already bounded its checks; this gives the sequential path the
same limit (WORKFLOW_CHECK_TIMEOUT_SECONDS, default 900) and the same way of
ending it: the command's whole process tree is terminated and the result is exit
status 124 with a plain line in the log saying so.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from process_tree import check_timeout, finish_check, start_check, wait_check


def main(argv):
    if '--' not in argv:
        print('usage: run_check.py -- <command...>', file=sys.stderr)
        return 2
    command = argv[argv.index('--') + 1:]
    if not command:
        return 2
    sys.stdout.flush()
    child = start_check(command, env=os.environ.copy(), stdout=sys.stdout.buffer, stderr=subprocess.STDOUT)
    try:
        return wait_check(child, check_timeout(), sys.stdout.buffer)
    finally:
        finish_check(child)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
