#!/usr/bin/env python3
"""Enumerate a project's own files the way a person editing it would see them.

`git ls-files` is the source of truth for "does this project consider this
path its own" -- .gitignore, nested .gitignore files, and negation patterns
all resolve through one call instead of being re-implemented per caller.
`.uncle/`, `node_modules/`, `.git/`, and `__pycache__/` are excluded
unconditionally, whether or not a project's .gitignore happens to list them:
uncle's own scratch directory is never source, a dependency tree gains
nothing from a full-tree scan even on the rare project that commits one, and
interpreter cache noise is never meaningful -- the last one matters most when
git is unavailable below and there is no .gitignore to fall back on at all.
"""
import subprocess
from pathlib import Path

ALWAYS_EXCLUDED_DIRS = ('.uncle', 'node_modules', '.git', '__pycache__')


def is_excluded(rel):
    """Does a project-relative posix path fall under an always-excluded dir?"""
    return any(part in ALWAYS_EXCLUDED_DIRS for part in Path(rel).parts)


def ignored(root, rels):
    """The subset of `rels` the project's ignore rules cover, tracked or not.

    `--exclude-standard` only filters *untracked* files: a tracked path is
    never reported as ignored without `--no-index`. That gap is why a file
    committed before its ignore rule existed keeps being enumerated, hashed
    and fed to agents forever after -- one real checkout carried 2379 archived
    `.uncle/workflow-history` files that way.

    Asking git rather than matching patterns here is deliberate: ignore rules
    differ per project and compose from several places at once -- nested
    .gitignore files, negations, .git/info/exclude and the user's global
    excludesfile. One `check-ignore` call resolves all of them for the project
    actually in front of us. Returns an empty set when git cannot answer, so
    a caller never loses files on account of this filter.
    """
    rels = [rel for rel in rels if rel]
    if not rels:
        return set()
    try:
        result = subprocess.run(
            ['git', 'check-ignore', '--no-index', '-z', '--stdin'],
            cwd=str(root), input='\0'.join(rels).encode('utf-8', 'surrogateescape'),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except OSError:
        return set()
    if result.returncode not in (0, 1):
        return set()
    return {rel for rel in result.stdout.decode('utf-8', 'surrogateescape').split('\0') if rel}


def project_files(root):
    """Relative posix paths git considers part of the project at `root`:
    tracked files plus untracked-but-not-ignored ones, minus .uncle/,
    node_modules/, and .git/ regardless of what .gitignore says. Falls back to
    every file under root, with the same three exclusions, when git is
    unavailable or root is not a repository -- gitignore-awareness is then
    simply absent, the same as every caller before this existed."""
    root = Path(root)
    try:
        output = subprocess.run(
            ['git', 'ls-files', '-co', '--exclude-standard', '-z'],
            cwd=root, capture_output=True, check=True,
        ).stdout
        listed = [rel for rel in output.decode('utf-8', 'replace').split('\0')
                  if rel and not is_excluded(rel)]
        # `-co --exclude-standard` drops ignored *untracked* files but keeps
        # tracked ones, so the ignore rules are applied again here for the
        # paths that came back tracked.
        skip = ignored(root, listed)
        for rel in listed:
            if rel not in skip:
                yield rel
        return
    except (OSError, subprocess.CalledProcessError):
        pass
    for path in root.rglob('*'):
        # A symlink is yielded as a leaf regardless of what it targets,
        # matching how `git ls-files` treats it (a blob, never traversed):
        # callers that care about symlink safety, such as review-cache.py's
        # cache-key builder, need to see it in order to reject it.
        if not path.is_symlink():
            if path.is_dir() or not path.is_file():
                continue
        rel = path.relative_to(root).as_posix()
        if not is_excluded(rel):
            yield rel
