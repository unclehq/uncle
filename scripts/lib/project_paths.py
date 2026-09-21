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
        for rel in output.decode('utf-8', 'replace').split('\0'):
            if rel and not is_excluded(rel):
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
