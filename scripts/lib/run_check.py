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
import tempfile
import shutil
import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from process_tree import check_timeout, finish_check, start_check, wait_check, kill_tree
from browser_install import prepare


def main(argv):
    if '--' not in argv:
        print('usage: run_check.py -- <command...>', file=sys.stderr)
        return 2
    command = argv[argv.index('--') + 1:]
    if not command:
        return 2
    flags = argv[:argv.index('--')]
    if '--config' in flags:
        os.environ['UNCLE_CONFIG'] = flags[flags.index('--config') + 1]
    shell_command = flags[flags.index('--shell-command') + 1] if '--shell-command' in flags else ''
    env = os.environ.copy()
    env.pop('UNCLE_CONFIG', None)
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        # A regular spool also supports idle detection when stdout is a pipe.
        with tempfile.TemporaryFile() as output:
            try:
                with prepare(shell_command, output, env):
                    output.flush()
                    child = start_check(command, env=env, stdout=output, stderr=subprocess.STDOUT)
                    try:
                        return wait_check(child, check_timeout(), output)
                    finally:
                        kill_tree(child)
                        child.wait()
                        finish_check(child)
            except (OSError, ValueError) as error:
                output.write((str(error) + '\n').encode())
                return 126
            finally:
                output.seek(0)
                shutil.copyfileobj(output, sys.stdout.buffer)
                sys.stdout.flush()
    finally:
        signal.signal(signal.SIGTERM, previous)



if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
