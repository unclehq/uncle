"""Run independent gate integration groups without duplicating other suites."""
import os
import sys
from process_tree import bash_executable
from shell_suites import run_commands

if __name__ == '__main__':
    first = 10 if os.environ.get('UNCLE_TEST_COMPLETION_ONLY') == '1' else 1
    names = ['diff-review', 'green-check', 'baseline', 'application-review',
             'repair', 'verification-integrity', 'document-budgets', 'compaction',
             'review-cache', 'delivery', 'delivery-resume', 'waivers',
             'waiver-integrity', 'driver-syntax']
    commands = {f'gates-{names[group - 1]}': [bash_executable(), sys.argv[1], '--group', str(group)]
                for group in range(first, 15)}
    raise SystemExit(run_commands(int(os.environ.get('WORKFLOW_TEST_JOBS', '8')), commands))
