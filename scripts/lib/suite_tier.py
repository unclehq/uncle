"""Which suites the test runners run by default.

Every suite stays on disk and runnable. By default the runners run the critical tier only (scripts/tests/critical-suites.txt):
the suites whose failure means Uncle could publish, approve or destroy something it must not, lose a run's state, or not start.
`--all` on a runner, or WORKFLOW_TEST_TIER=all, runs every suite. Naming suites explicitly always runs exactly those.
"""
import os
import re
from pathlib import Path

MANIFEST = Path('scripts/tests/critical-suites.txt')    # relative to the project the runner was started in


def tier():
    value = os.environ.get('WORKFLOW_TEST_TIER', 'critical').strip().lower()
    if value not in ('critical', 'all'):
        raise ValueError("WORKFLOW_TEST_TIER must be 'critical' or 'all'")
    return value


def critical_names():
    """Suite names in the project's manifest, in file order; raises when the manifest is unreadable or empty."""
    try:
        lines = MANIFEST.read_text(encoding='utf-8').splitlines()
    except OSError as error:
        raise ValueError(f'critical-suite manifest unreadable: {error}') from error
    names = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith('#')]
    if not names:
        raise ValueError('critical-suite manifest is empty')
    return names


def suite_name(path):
    return re.sub(r'-test\.(py|sh)$', '', Path(path).name)


def select(files):
    """`files` narrowed to the active tier. A project with no manifest of its own (any project other than uncle, or a scratch
    directory under test) gets every suite: a tier is something a project opts into by committing the manifest."""
    if tier() == 'all' or not MANIFEST.is_file():
        return list(files)
    wanted = set(critical_names())
    return [path for path in files if suite_name(path) in wanted]


def consume_all_flag(argv):
    """Remove a leading/anywhere `--all` from argv and set the environment; return the remaining arguments."""
    rest = [arg for arg in argv if arg != '--all']
    if len(rest) != len(argv):
        os.environ['WORKFLOW_TEST_TIER'] = 'all'
    return rest
