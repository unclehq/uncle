#!/usr/bin/env python3
"""Carry a race winner's work from its isolated project copy back to the live project.

A candidate race runs every candidate in its own copy of the project so that
none can clobber another.  Only the winner counts, so its work (source edits,
the documents the stage writes) must reach the live tree, or a stage that
succeeded leaves nothing behind.  The copy is snapshotted when it is made; the
winner is then compared against that snapshot, so only what the winner itself
changed is promoted, and a file someone else changed in the live project in the
meantime is left alone and reported rather than overwritten.

    promote_candidate.py snapshot <candidate-project>      write <candidate>/../manifest.json
    promote_candidate.py promote  <candidate-dir> <live-root>
"""
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

# Never promoted: version control, dependencies, caches.  The copy excludes most
# of these already; a candidate that created them (npm install) must not export them.
EXCLUDED_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.vite'}
EXCLUDED_GLOBS = ('.opencode*',)
# Inside .uncle only documents cross; state, logs, credentials and the
# candidate's own delivery file never do.
UNCLE_DOCS = '.uncle/docs/'
UNCLE_PACKETS = '.uncle/workflow/documents/'
UNCLE_INVESTIGATION = ('.uncle/workflow/*-investigation.md',)
MANIFEST = 'manifest.json'


def promotable(relative):
    if relative.startswith('.uncle/'):
        return (relative.startswith(UNCLE_DOCS) or relative.startswith(UNCLE_PACKETS)
                or any(fnmatch.fnmatch(relative, pattern) and relative.count('/') == 2 for pattern in UNCLE_INVESTIGATION))
    return True


def _excluded(name):
    return name in EXCLUDED_DIRS or any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDED_GLOBS)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def files(root):
    """{relative posix path: sha256} of the regular, promotable files under `root`."""
    root = Path(root)
    found = {}
    for directory, names, filenames in os.walk(root):
        names[:] = [n for n in names if not _excluded(n) and not (Path(directory) / n).is_symlink()]
        for name in filenames:
            path = Path(directory) / name
            if path.is_symlink() or _excluded(name) or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if promotable(relative):
                found[relative] = digest(path)
    return found


def snapshot(project):
    project = Path(project)
    (project.parent / MANIFEST).write_text(json.dumps(files(project), sort_keys=True), encoding='utf-8')


def _safe_target(live, relative):
    """The live path for `relative`, or None when it would leave the project or cross a symlink."""
    target = live / relative
    cursor = live
    for part in Path(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return None
    try:
        target.resolve().relative_to(live.resolve())
    except ValueError:
        return None
    return target


def promote(candidate_dir, live_root):
    """Apply the winner's changes to `live_root`; returns {'copied', 'removed', 'conflicts'} lists."""
    candidate_dir, live = Path(candidate_dir), Path(live_root)
    project = candidate_dir / 'project'
    try:
        base = json.loads((candidate_dir / MANIFEST).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ValueError('candidate has no snapshot manifest; refusing to promote blindly') from None
    now = files(project)
    result = {'copied': [], 'removed': [], 'conflicts': []}
    for relative, sha in sorted(now.items()):
        if base.get(relative) == sha:
            continue                                   # the winner did not touch it
        target = _safe_target(live, relative)
        if target is None:
            result['conflicts'].append(relative + ' (unsafe path)')
            continue
        if target.exists() and not target.is_symlink() and digest(target) not in (base.get(relative), sha):
            result['conflicts'].append(relative + ' (changed in the live project meanwhile)')
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project / relative, target)
        result['copied'].append(relative)
    for relative, sha in sorted(base.items()):
        if relative in now:
            continue
        target = _safe_target(live, relative)
        if target is not None and target.is_file() and not target.is_symlink() and digest(target) == sha:
            target.unlink()
            result['removed'].append(relative)
    return result


def main(argv):
    if len(argv) == 3 and argv[1] == 'snapshot':
        snapshot(argv[2])
        return 0
    if len(argv) == 4 and argv[1] == 'promote':
        try:
            result = promote(argv[2], argv[3])
        except ValueError as error:
            print('Candidate promotion: ' + str(error), file=sys.stderr)
            return 1
        print('Candidate promotion: %d file(s) copied, %d removed, %d conflict(s).' %
              (len(result['copied']), len(result['removed']), len(result['conflicts'])), file=sys.stderr)
        for line in result['conflicts']:
            print('  not promoted: ' + line, file=sys.stderr)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
