#!/usr/bin/env python3
"""A digest of everything a verification run could depend on, so an identical re-run can be skipped.

The driver verifies the build after implementation and again before the checklist runs; between the two
nothing changes in the usual case, and the second run repeats install, build, unit, browser and mutation
checks (about two minutes on a small app) to learn what it already knew.  The fingerprint is a hash of the
project's files -- the same set the preview server and scope checks use: tracked and untracked, minus
`.uncle/`, `node_modules/` and `.git/`, with ignored files left out -- plus any extra text given
(the verification commands).  Equal fingerprints mean the same code, tests and commands.

usage: tree_fingerprint.py PROJECT_ROOT [EXTRA_FILE ...]
"""
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_paths import project_files


def fingerprint(root, extras=()):
    digest = hashlib.sha256()
    root = Path(root)
    for rel in sorted(set(project_files(root))):
        path = root / rel
        digest.update(rel.encode('utf-8', 'replace') + b'\0')
        try:
            if path.is_symlink():
                digest.update(b'link:' + str(path.readlink()).encode('utf-8', 'replace'))
            else:
                digest.update(hashlib.sha256(path.read_bytes()).digest())
        except OSError:
            digest.update(b'unreadable')
        digest.update(b'\n')
    for extra in extras:
        digest.update(b'extra:' + str(extra).encode() + b'\0')
        try:
            digest.update(Path(extra).read_bytes())
        except OSError:
            digest.update(b'missing')
    return digest.hexdigest()


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    print(fingerprint(argv[0], argv[1:]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
