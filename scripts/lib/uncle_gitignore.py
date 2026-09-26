#!/usr/bin/env python3
""".uncle holds run state, cost/token logs, and (via self_hosted.py) API keys
-- never something to commit. This normalizes a project's ignore rules to one
canonical block.

Only a .gitignore that already exists is edited: a project with no git
repository, or one that manages ignores elsewhere (e.g. a global
excludesfile), gets no file created on its behalf.

Generated documents (generated_input.py: REQUIREMENTS.md/CHANGE_REQUEST.md,
and any workflow output that lands under .uncle/docs) live there instead of
the project root specifically so a human-authored file and a generated one are
never confused for each other. But git's own worktree-removal dirty check only
ever sees tracked content, so a blanket `.uncle/` ignore makes a freshly
generated, not-yet-committed document invisible to it -- worktree_remove()
(scripts/lib/worktrees.sh) would then happily discard a worktree holding one no
operator has used yet. `!.uncle/docs/` re-includes the whole directory;
nothing re-excludes its contents, so everything under it stays tracked and
visible. change-pr.sh's snapshot() also skips whatever the ignore rules cover,
so that negation is what keeps the approved artifacts in the PR.

This runs for the project root and for every worktree a run is created in.
A worktree checks out a commit, so its .gitignore is whatever was committed --
which on a project that added the block later is the version without it. That
is how a worktree ended up tracking 2379 archived `.uncle/workflow-history`
files and carrying them into a PR.
"""
import os
import sys

# Uncle's own entries, canonical and legacy, normalized as one block. A
# project can have a stale bare `.uncle` after an earlier canonical pair;
# replacing just that bare line added another pair on every first-run refresh.
# The `.workflow` spellings predate the `.uncle/workflow` rename and name
# directories that no longer exist; they are uncle's to retire, and leaving
# them behind is what made a project's ignore file read as half-configured.
MANAGED = {
    '.uncle', '.uncle/', '.uncle/*', '!.uncle/docs/',
    '.workflow', '.workflow/', '.workflow/*',
    '.workflow/state', '.workflow/approvals/', '.workflow/logs/',
    '.workflow/change.diff', '.workflow/change-stat.txt',
}
CANONICAL = ['.uncle/*', '!.uncle/docs/']


def ensure(project_root):
    """Normalize <project_root>/.gitignore. Returns True when it was changed."""
    path = os.path.join(project_root, ".gitignore")
    try:
        with open(path, encoding="utf-8") as fh:
            existing = fh.read()
    except OSError:
        return False
    lines = existing.splitlines()
    positions = [index for index, line in enumerate(lines) if line.strip() in MANAGED]
    if positions:
        # Keep the first occurrence's position and drop every duplicate or
        # legacy spelling, leaving unrelated user rules untouched.
        first = positions[0]
        normalized = []
        for index, line in enumerate(lines):
            if index == first:
                normalized.extend(CANONICAL)
            if line.strip() not in MANAGED:
                normalized.append(line)
        if normalized == lines:
            return False
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(normalized) + "\n")
        except OSError:
            return False
        return True
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(("\n" if existing and not existing.endswith("\n") else "")
                     + "\n".join(CANONICAL) + "\n")
    except OSError:
        return False
    return True


if __name__ == '__main__':
    # Best effort: a project that cannot be normalized still runs.
    ensure(sys.argv[1] if len(sys.argv) > 1 else '.')
