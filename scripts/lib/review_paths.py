"""Enumerate reviewable changes with one baseline lookup and batched Git calls."""
import fnmatch
import os
from pathlib import Path
import subprocess
import sys


def artifact_patterns():
    # Read the canonical shell case list rather than maintaining a second list.
    text = Path(__file__).with_name('workflow-artifacts.sh').read_text()
    case = text.split('case "$1" in', 1)[1].split(')', 1)[0]
    return [part.strip().replace('\\\n', '').strip() for part in case.split('|')]


def paths(baseline=None):
    exclusions = ['--', '.', ':(exclude).uncle/workflow', ':(exclude).uncle/workflow-history']
    def git(args):
        return subprocess.run(['git', *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    diff = git(['diff', '--name-only', '-z', 'HEAD', *exclusions])
    if diff.returncode:
        diff = git(['diff', '--name-only', '-z', *exclusions])
    untracked = git(['ls-files', '--others', '--exclude-standard', '-z', *exclusions])
    old = set()
    if baseline and Path(baseline).is_file():
        old = set(Path(baseline).read_text(errors='surrogateescape').splitlines())
    patterns = artifact_patterns()
    candidates = {os.fsdecode(p) for p in (diff.stdout + untracked.stdout).split(b'\0') if p}
    return sorted(p for p in candidates if p not in old and not any(fnmatch.fnmatchcase(p, pattern) for pattern in patterns))


if __name__ == '__main__':
    for path in paths(os.environ.get('WORKFLOW_UNTRACKED_BASELINE')):
        if '\n' in path or '\r' in path:
            raise SystemExit('Review cannot represent a filename containing a newline')
        print(path)
