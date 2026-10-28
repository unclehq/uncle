#!/usr/bin/env python3
"""A private copy of the project to run the verification commands in while the run goes on.

The driver's verification commands used to run with everything else stopped, because they start servers on the project's own port
and write into the tree.  Run in the background beside the test review and the checklist (whose workers start the same application
on the same port), they would fail each other.  So they run in a copy: the project's files, `node_modules` linked rather than
copied, and the port the project's configuration names moved to another one, in the copy only.  What the commands write
(`.test-out`, reports) is copied back when they finish.

    isolated_verify.py prepare PROJECT DEST     prints {"base": N, "port": M} (null when no port was found)
    isolated_verify.py finish PROJECT DEST      copies the run's output directories back into PROJECT
"""
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

SKIP = {'node_modules', '.git', 'dist', '.test-out', 'coverage', 'test-results', 'playwright-report', '.mutation-work',
        '.mutation-scratch', '.venv', '__pycache__', '.pw-browsers'}
OUTPUT = ('.test-out', 'test-results', 'playwright-report')
TEXT_LIMIT = 2_000_000
PORT = re.compile(r'(?:--port[ =]|port[\'"]?\s*[:=]\s*|(?:localhost|127\.0\.0\.1|0\.0\.0\.0):)(\d{4,5})\b')
OFFSET = 1500


def files(root):
    """Project files worth copying: not dependencies, build output or the driver's own state (only `.uncle/docs` is kept)."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        keep = []
        for name in dirnames:
            rel = rel_dir / name
            if name in SKIP:
                continue
            if rel.parts[:1] == ('.uncle',) and rel.parts[:2] != ('.uncle', 'docs') and len(rel.parts) == 2:
                continue
            keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            yield rel_dir / name


def base_port(dest):
    counts = Counter()
    for rel in files(dest):
        path = Path(dest) / rel
        if path.suffix.lower() not in ('.js', '.mjs', '.cjs', '.ts', '.json', '.md', '.sh', '.html', '.yml', '.yaml', '.toml'):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, ValueError):
            continue
        for match in PORT.finditer(text):
            port = int(match.group(1))
            if 1024 <= port <= 65535:
                counts[port] += 1
    return counts.most_common(1)[0][0] if counts else None


def prepare(project, dest):
    project, dest = Path(project), Path(dest)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for rel in files(project):
        source = project / rel
        if source.is_symlink() or not source.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    modules = project / 'node_modules'
    if modules.is_dir():
        (dest / 'node_modules').symlink_to(modules.resolve())
    base = base_port(dest)
    port = None
    if base:
        port = base + OFFSET if base + OFFSET <= 65000 else base - OFFSET
        pattern = re.compile(r'(?<!\d)%d(?!\d)' % base)
        for rel in files(dest):
            path = dest / rel
            try:
                if path.stat().st_size > TEXT_LIMIT:
                    continue
                text = path.read_text(encoding='utf-8')
            except (OSError, ValueError):
                continue
            changed = pattern.sub(str(port), text)
            if changed != text:
                path.write_text(changed, encoding='utf-8')
    return {'base': base, 'port': port}


KEEP = ('dist', 'build', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml')


def finish(project, dest):
    """Bring back what the commands produced: test output, and what an install and a build leave for the project to run
    (noinit: the install and build ran in the copy only, so the project had no dependencies and no build, and its page was blank)."""
    project, dest = Path(project), Path(dest)
    modules = dest / 'node_modules'
    if modules.is_dir() and not modules.is_symlink() and not (project / 'node_modules').exists():
        shutil.move(str(modules), str(project / 'node_modules'))          # installed here: it becomes the project's
    for name in KEEP:
        source, target = dest / name, project / name
        if source.is_symlink() or not source.exists():
            continue
        if source.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(source, target, symlinks=True)
        elif not target.exists():
            shutil.copy2(source, target)
    for name in OUTPUT:
        source = dest / name
        if not source.is_dir():
            continue
        for path in source.rglob('*'):
            if path.is_file() and not path.is_symlink():
                target = project / name / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)


def main(argv):
    if len(argv) != 3 or argv[0] not in ('prepare', 'finish'):
        raise SystemExit(__doc__)
    if argv[0] == 'prepare':
        print(json.dumps(prepare(argv[1], argv[2])))
    else:
        finish(argv[1], argv[2])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
