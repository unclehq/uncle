#!/usr/bin/env python3
"""Does the project build as it stands? Answered in a throwaway copy, so the project itself is never touched.

Run after a wave of implementation steps has merged. A seam between two workers (a scaffold `package.json` that omits a package the entry
file imports) breaks the build, which nothing observed until the driver's own verification, a stage later; live run 10 then spent 183s in
repair and another two minutes with a browser worker waiting on a web server that could never start. A one-second build here lets the
worker that owns the files fix it while it still holds the context.

usage: wave_build_check.py PROJECT OUT_JSON [TIMEOUT_SECONDS]
       wave_build_check.py --probe PROJECT        exit 0 when there is a build to run, 3 when there is not
exit:  0 the build passed; 1 it failed or timed out; 3 there is nothing to build (no package.json, or no `build` script).
OUT_JSON gets {"ok", "command", "seconds", "excerpt"}; the excerpt is the lines of the output that say what broke.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

SKIP = ('node_modules', '.git', '.uncle', 'dist', 'build', 'test-results', 'playwright-report', '.vite', 'coverage')
SIGNAL = re.compile(r'error|failed|cannot|could not|unexpected|not exported|resolve|not found|no such', re.I)
ANSI = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')


def excerpt(output, limit=1500, lines=10):
    text = ANSI.sub('', output)
    found = [line.strip() for line in text.splitlines() if line.strip() and SIGNAL.search(line)]
    chosen = found[:lines] or [line.strip() for line in text.splitlines() if line.strip()][-lines:]
    return '\n'.join(chosen)[:limit]


def build_command(project):
    """`npm run build` when package.json declares a build script, else None."""
    try:
        scripts = json.loads((Path(project) / 'package.json').read_text()).get('scripts') or {}
    except (OSError, ValueError):
        return None
    return ['npm', 'run', 'build'] if scripts.get('build') else None


def check(project, timeout=90):
    """(ok, seconds, excerpt) for the project's build, run in a copy; None when there is nothing to build."""
    command = build_command(project)
    if command is None:
        return None
    project = Path(project)
    work = Path(tempfile.mkdtemp(prefix='uncle-wave-build-'))
    started = time.monotonic()
    try:
        copy = work / 'project'
        shutil.copytree(project, copy, symlinks=True, ignore=shutil.ignore_patterns(*SKIP))
        if (project / 'node_modules').is_dir():
            (copy / 'node_modules').symlink_to((project / 'node_modules').resolve(), target_is_directory=True)
        try:
            done = subprocess.run(command, cwd=copy, env=dict(os.environ, CI='1'), capture_output=True, text=True, timeout=timeout)
            output, ok = (done.stdout or '') + '\n' + (done.stderr or ''), done.returncode == 0
        except subprocess.TimeoutExpired as late:
            output = ((late.stdout or b'').decode('utf-8', 'replace') if isinstance(late.stdout, bytes) else (late.stdout or ''))
            output += '\nthe build did not finish within %d seconds (timed out)' % timeout
            ok = False
        except OSError as error:
            output, ok = 'could not run the build: %s' % error, False
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return ok, round(time.monotonic() - started, 2), '' if ok else excerpt(output)


def main(argv):
    if argv[:1] == ['--probe'] and len(argv) == 2:
        return 0 if build_command(argv[1]) else 3              # is there anything to build at all? cheap, installs nothing
    if len(argv) < 2:
        raise SystemExit(__doc__)
    timeout = int(argv[2]) if len(argv) > 2 else 90
    result = check(argv[0], timeout)
    if result is None:
        return 3
    ok, seconds, found = result
    Path(argv[1]).write_text(json.dumps({'ok': ok, 'command': 'npm run build', 'seconds': seconds, 'excerpt': found}) + '\n')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
