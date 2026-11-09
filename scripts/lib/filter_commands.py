#!/usr/bin/env python3
"""Split the plan's verification commands into the ordinary ones and the defect-injection (mutation) ones.

    filter_commands.py COMMANDS_FILE GROUPS_FILE main|mutation

Rewrites COMMANDS_FILE in place to hold only the commands of the chosen kind, and GROUPS_FILE (one row of consecutive one-based
positions per parallel group) to match: positions are renumbered, and a group left with fewer than two commands is dropped. The
defect-injection runner works in copies of the project and is never needed by the checklist, so the driver runs it after the other
commands have published their result instead of making everything wait for it. The pattern is the one parallel_checks.py uses to
recognize that runner.

Prints the number of commands kept. Exit 0 always; an empty COMMANDS_FILE just means nothing of that kind exists.
"""
import re
import sys
from pathlib import Path

MUTATION = re.compile(r'mutat|defect|inject', re.I)


def split(commands):
    """[(position, command)] for the non-empty lines, positions one-based over the non-empty lines (as the group rows count them)."""
    return [(i + 1, c) for i, c in enumerate(c for c in commands if c.strip())]


def filter_files(commands_path, groups_path, kind):
    lines = Path(commands_path).read_text(encoding='utf-8').splitlines()
    numbered = split(lines)
    want_mutation = kind == 'mutation'
    kept = [(pos, cmd) for pos, cmd in numbered if bool(MUTATION.search(cmd)) == want_mutation]
    renumber = {old: new for new, (old, _) in enumerate(kept, start=1)}
    Path(commands_path).write_text(''.join(cmd + '\n' for _, cmd in kept), encoding='utf-8')
    rows = []
    try:
        groups = Path(groups_path).read_text(encoding='utf-8').splitlines()
    except OSError:
        groups = []
    for row in groups:
        members = [renumber[int(p)] for p in row.split() if p.isdigit() and int(p) in renumber]
        if len(members) >= 2:
            rows.append(' '.join(str(m) for m in members))
    Path(groups_path).write_text(''.join(r + '\n' for r in rows), encoding='utf-8')
    return len(kept)


def main(argv):
    if len(argv) != 4 or argv[3] not in ('main', 'mutation'):
        print(__doc__, file=sys.stderr)
        return 2
    print(filter_files(argv[1], argv[2], argv[3]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
