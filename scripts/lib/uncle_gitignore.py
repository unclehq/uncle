#!/usr/bin/env python3
""".uncle holds run state, cost/token logs, and (via self_hosted.py) API keys
-- never something to commit. This normalizes a project's ignore rules to one
canonical block.

The block also keeps the change attestation, its signature and the trust root (`allowed_signers`) out of the ignore rules: they are
committed on the feature branch, and under `.uncle/*` a negation is the only way to commit them. A `.gitignore` that lacks the
negations ignored them, and the attestation then never reached the branch.

An existing .gitignore is edited. A git repository with none gets one created, holding only this block. A directory that is not a
git repository gets no file on its behalf.

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
    '!.uncle/attestation.json', '!.uncle/attestation.sig', '!.uncle/allowed_signers',
    # The intermediate spellings, from after the `.workflow` rename but before
    # the `.uncle/*` block. `.uncle/workflow` on its own is the one that
    # matters most: it does not cover `.uncle/workflow-history/`, so a project
    # carrying only that line ignored the live run directory and nothing else.
    '.uncle/workflow', '.uncle/workflow/', '.uncle/workflow/*',
    '.uncle/workflow-history', '.uncle/workflow-history/', '.uncle/workflow-history/*',
    '.workflow', '.workflow/', '.workflow/*',
    '.workflow/state', '.workflow/approvals/', '.workflow/logs/',
    '.workflow/change.diff', '.workflow/change-stat.txt',
}
CANONICAL = ['.uncle/*', '!.uncle/docs/', '!.uncle/attestation.json', '!.uncle/attestation.sig', '!.uncle/allowed_signers']


def only_adds_managed(before, after):
    """True when `after` is `before` plus lines that are Uncle's own ignore entries and nothing else.

    Something running next to a stage appends a bare `.uncle` to a project's .gitignore. That is not an edit anyone made to the
    project, so a guard that compares the file byte for byte (the triage sandbox diff, the implementation approval) tolerates
    exactly this and nothing more: any removal, reordering of other rules or added rule of the project's own still counts."""
    if before == after:
        return True
    old, new = before.splitlines(), after.splitlines()
    pool = list(old)
    extra = []
    for line in new:
        if line in pool:
            pool.remove(line)
        else:
            extra.append(line)
    return not pool and all(line.strip() in MANAGED for line in extra)


def strip_managed(text):
    """The file's content without Uncle's own ignore entries; what an approval should be bound to."""
    return '\n'.join(line for line in text.splitlines() if line.strip() not in MANAGED)


FREEZE_ENV = 'UNCLE_GITIGNORE_FROZEN'
_FROZEN_ROOTS = set()


def _marker_path(project_root):
    return os.path.join(project_root, '.uncle', 'workflow', 'gitignore-frozen')


def _root_key(project_root):
    return os.path.realpath(project_root)


def is_frozen(project_root):
    """True when .gitignore must no longer be written: env guard, in-process record, or marker file."""
    if os.environ.get(FREEZE_ENV) == '1':
        return True
    if _root_key(project_root) in _FROZEN_ROOTS:
        return True
    return os.path.lexists(_marker_path(project_root))


def freeze(project_root):
    """Freeze .gitignore handling for this project root (after publish, before the final commit).

    Always records the freeze in-process so ensure() stays read-only even when the marker cannot be persisted (fail closed).
    Returns True when the marker exists as a regular file afterwards; False when it could not be written (a symlink at
    .uncle, workflow or the marker, or any OSError). Never follows links, never truncates, never writes outside the root."""
    _FROZEN_ROOTS.add(_root_key(project_root))
    try:
        uncle_dir = os.path.join(project_root, '.uncle')
        wf_dir = os.path.join(uncle_dir, 'workflow')
        marker = _marker_path(project_root)
        for part in (uncle_dir, wf_dir):
            if os.path.islink(part):
                return False
        os.makedirs(wf_dir, exist_ok=True)
        for part in (uncle_dir, wf_dir):
            if os.path.islink(part):
                return False
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o644)
        except FileExistsError:
            import stat
            return stat.S_ISREG(os.lstat(marker).st_mode)
        os.close(fd)
        return True
    except (OSError, ValueError):
        return False


def ensure(project_root):
    """Normalize <project_root>/.gitignore. Returns True when it was changed."""
    if is_frozen(project_root):
        return False
    path = os.path.join(project_root, ".gitignore")
    try:
        with open(path, encoding="utf-8") as fh:
            existing = fh.read()
    except FileNotFoundError:
        if not os.path.exists(os.path.join(project_root, ".git")):
            return False
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(CANONICAL) + "\n")
        except OSError:
            return False
        return True
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


BLOCK_START = '# >>> uncle managed >>>'
BLOCK_END = '# <<< uncle managed <<<'


def _git_path(root, *args):
    import subprocess
    try:
        out = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    path = out.stdout.strip().splitlines()[0]
    return path if os.path.isabs(path) else os.path.join(root, path)


def _exclude_path(root):
    """The shared info/exclude path when it is safe to write, else None."""
    path = _git_path(root, 'rev-parse', '--git-path', 'info/exclude')
    common = _git_path(root, 'rev-parse', '--git-common-dir')
    if not path or not common:
        return None
    info = os.path.dirname(path)
    if os.path.islink(path) or os.path.islink(info):
        return None
    real_common = os.path.realpath(common)
    if os.path.commonpath([real_common, os.path.realpath(info)]) != real_common:
        return None
    return path


def _exclude_text(existing):
    """`existing` with exactly one canonical block: placed where a marked block was, else appended."""
    lines = existing.splitlines()
    out, placed, skipping = [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped == BLOCK_START:
            skipping = True
            if not placed:
                out.append(None)
                placed = True
            continue
        if skipping:
            if stripped == BLOCK_END:
                skipping = False
            elif stripped not in MANAGED:
                # An unterminated block: lines that are not ours end it.
                skipping = False
                out.append(line)
            continue
        if stripped == BLOCK_END or stripped in MANAGED:
            continue
        out.append(line)
    block = [BLOCK_START, *CANONICAL, BLOCK_END]
    if None in out:
        merged = []
        for line in out:
            merged.extend(block if line is None else [line])
        out = merged
    else:
        out.extend(block)
    return '\n'.join(out) + '\n'


def ensure_exclude(project_root):
    """Write the canonical block into the shared info/exclude, never a tracked file.

    True only when the file was written; False when already canonical, not a git repository, the path is a symlink or outside the
    git common dir, or on any OSError."""
    try:
        path = _exclude_path(project_root)
        if path is None:
            return False
        try:
            with open(path, encoding='utf-8') as fh:
                existing = fh.read()
        except FileNotFoundError:
            existing = ''
        new = _exclude_text(existing)
        if new == existing:
            return False
        import tempfile
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix='.exclude-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(new)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return True
    except (OSError, ValueError):
        return False


def _exclude_text_current(project_root):
    """True when info/exclude already holds the canonical block (so a False from ensure_exclude is benign)."""
    path = _exclude_path(project_root)
    if path is None:
        return False
    try:
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
    except OSError:
        return False
    return _exclude_text(text) == text


def tracked_needs_normalization(project_root):
    """True when the tracked .gitignore holds Uncle entries that differ from the canonical block."""
    try:
        with open(os.path.join(project_root, '.gitignore'), encoding='utf-8') as fh:
            managed = [l.strip() for l in fh.read().splitlines() if l.strip() in MANAGED]
    except OSError:
        return False
    return bool(managed) and managed != CANONICAL


if __name__ == '__main__':
    # Best effort: a project that cannot be normalized still runs.
    ensure(sys.argv[1] if len(sys.argv) > 1 else '.')
