"""Run independent gate integration groups without duplicating other suites."""
import os
import sys
from process_tree import bash_executable
from shell_suites import run_commands

if __name__ == '__main__':
    completion_only = os.environ.get('UNCLE_TEST_COMPLETION_ONLY') == '1'
    first = 10 if completion_only else 1
    names = ['diff-review', 'green-check', 'baseline', 'application-review',
             'repair', 'verification-integrity', 'document-budgets', 'compaction',
             'review-cache', 'delivery', 'delivery-resume', 'waivers',
             'waiver-integrity', 'driver-syntax']
    commands = {f'gates-{names[group - 1]}': [bash_executable(), sys.argv[1], '--group', str(group)]
                for group in range(first, 15)}
    # Groups 15 and 16 are the second halves of what were two independently
    # slow groups (verification-integrity and repair, each ~90s sequential
    # -- co-dominant long poles that set the whole run's wall-clock floor no
    # matter how many *other* groups ran alongside them). Split so each pair
    # runs concurrently; only in the full run, matching completion-only
    # mode's existing exclusion of groups 5 and 6 themselves.
    if not completion_only:
        commands['gates-verification-integrity-2'] = [bash_executable(), sys.argv[1], '--group', '15']
        commands['gates-repair-2'] = [bash_executable(), sys.argv[1], '--group', '16']
    # Default to one worker per group: there are at most 15 of them, each its
    # own process running a real driver against a scratch git repo, so this
    # is bounded, known-independent work, not an open-ended fan-out -- run it
    # in one wave rather than artificially queuing part of it behind a cap
    # sized for the much larger full-suite regression.
    raise SystemExit(run_commands(int(os.environ.get('WORKFLOW_TEST_JOBS', str(len(commands)))), commands))
