"""Runs across the git worktrees of one project (Issue 64).

A run is a worktree holding `.uncle/workflow/state`. Git's own worktree list
is the registry; nothing else is written. Both `uncle --runs` and the TUI
homepage read `runs()`, so the two listings cannot drift.

`state` follows scripts/lib/state.sh: the first line, minus an all-digit
`<issue>:` prefix. The issue is `origin` field 2 when that file exists and the
field is all digits, else the state prefix (`state_issue`), else `?`.
"""
import os
import subprocess
import sys


class WorktreeListError(Exception):
    """`git worktree list` could not be run or failed."""


def worktrees(project):
    try:
        result = subprocess.run(['git', '-C', project, 'worktree', 'list', '--porcelain'],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        raise WorktreeListError(str(error)) from error
    if result.returncode:
        raise WorktreeListError(result.stderr.strip() or 'git worktree list failed')
    return [line[len('worktree '):] for line in result.stdout.splitlines() if line.startswith('worktree ')]


def _first_line(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return handle.readline().rstrip('\n')
    except (OSError, UnicodeError):
        return None


def _run(path):
    workflow = os.path.join(path, '.uncle', 'workflow')
    raw = _first_line(os.path.join(workflow, 'state'))
    if not raw:
        return None
    prefix, sep, rest = raw.partition(':')
    if sep and prefix.isdigit():
        state, issue = rest, prefix
    else:
        state, issue = raw, ''
    origin = _first_line(os.path.join(workflow, 'origin'))
    if origin:
        fields = origin.split('\t')
        if len(fields) >= 2 and fields[1].isdigit():
            issue = fields[1]
    return dict(path=path, issue=issue or '?', state=state,
                locked=os.path.isdir(os.path.join(workflow, 'lock')))


def runs(project):
    """One dict (path, issue, state, locked) per worktree with a state file,
    in `git worktree list` order (main checkout first)."""
    rows = []
    for path in worktrees(project):
        row = _run(path)
        if row is not None:
            rows.append(row)
    return rows


def main(argv):
    project = argv[1] if len(argv) > 1 else os.getcwd()
    try:
        rows = runs(project)
    except WorktreeListError:
        print('no worktrees')
        return 0
    if not rows:
        print('no runs')
        return 0
    for row in rows:
        print('#%s\t%s\t%s\t%s' % (row['issue'], row['state'], 'locked' if row['locked'] else 'idle', row['path']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
