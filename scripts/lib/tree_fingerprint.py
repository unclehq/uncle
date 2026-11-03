#!/usr/bin/env python3
"""A digest of everything a verification run could depend on, so an identical re-run can be skipped.

The driver verifies the build after implementation and again before the checklist runs; between the two
nothing changes in the usual case, and the second run repeats install, build, unit, browser and mutation
checks (about two minutes on a small app) to learn what it already knew.  The fingerprint is a hash of the
project's files -- the same set the preview server and scope checks use: tracked and untracked, minus
`.uncle/`, `node_modules/` and `.git/`, with ignored files left out -- plus any extra text given
(the verification commands).  Equal fingerprints mean the same code, tests and commands.

usage: tree_fingerprint.py [--app] PROJECT_ROOT [EXTRA_FILE ...]
--app leaves out tests, specs, mutation files and documents: the files the running application can depend on.
"""
import hashlib
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_paths import project_files
from uncle_gitignore import strip_managed
from step_groups import TEST_PATH
from scaffold_reconcile import test_block_span

# These directories are verification outputs, also excluded from isolated inputs.
VERIFICATION_OUTPUTS = {".test-out", "test-results", "playwright-report"}


def is_application_file(rel):
    """A file the running application can depend on: not a test, spec or mutation file, and not a document."""
    return not TEST_PATH.search(rel) and not rel.lower().endswith('.md')


CONFIG_NAME = re.compile(r'^vite(st)?\.config\.[cm]?[jt]s$')


def without_test_block(text):
    """A Vite or Vitest config with the body of its `test: { ... }` object removed: where the unit tests look is not part of the
    application. Run 18: the driver's scaffold reconciliation widened that glob after the early checklist, which changed the
    application fingerprint and made all 15 passing early rows run again (96 s)."""
    span = test_block_span(text)
    return text if span is None else text[:span[0]] + text[span[1]:]


def fingerprint(root, extras=(), app_only=False):
    digest = hashlib.sha256()
    root = Path(root)
    for rel in sorted(set(project_files(root))):
        if any(part in VERIFICATION_OUTPUTS for part in Path(rel).parts[:-1]):
            continue
        if app_only and not is_application_file(rel):
            continue
        path = root / rel
        digest.update(rel.encode('utf-8', 'replace') + b'\0')
        try:
            if path.is_symlink():
                digest.update(b'link:' + str(path.readlink()).encode('utf-8', 'replace'))
            elif path.name == '.gitignore':
                # Uncle's own ignore lines (a bare `.uncle`) are appended between stages, sometimes just after verification started.
                # They say nothing about the code, so they must not make an identical tree look changed: in live run 9 the background
                # verification was started three times in a row, each start cancelling the last, as the tree "changed" under it.
                text = path.read_bytes().decode('utf-8', 'replace')
                digest.update(hashlib.sha256(strip_managed(text).encode('utf-8')).digest())
            elif app_only and CONFIG_NAME.match(path.name):
                text = path.read_bytes().decode('utf-8', 'replace')
                digest.update(hashlib.sha256(without_test_block(text).encode('utf-8')).digest())
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
    app_only = argv[0] == '--app'
    rest = argv[1:] if app_only else argv
    if not rest:
        raise SystemExit(__doc__)
    print(fingerprint(rest[0], rest[1:], app_only=app_only))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
