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


def file_hash(path):
    """Git blob id of a working-tree file, or None when it cannot be read."""
    result = subprocess.run(['git', 'hash-object', '--', path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return result.stdout.decode().strip() or None if not result.returncode else None


def write_hashes(baseline):
    """Record a content hash beside the baseline for every path it lists.

    The baseline names paths that predate the change so they are not charged
    to it. A path alone cannot tell "left alone" from "left alone, then
    edited by the implementation": a project whose files are all untracked
    (never committed) would show an empty change and be reported as
    undelivered. The sidecar lets paths() keep a baseline file only while its
    content is unchanged.
    """
    names = Path(baseline).read_text(errors='surrogateescape').splitlines()
    lines = []
    for name in names:
        digest = file_hash(name)
        if digest and '\t' not in name:
            lines.append('%s\t%s' % (name, digest))
    Path(str(baseline) + '.hashes').write_text('\n'.join(lines) + ('\n' if lines else ''), errors='surrogateescape')


def unchanged_baseline(baseline):
    """Baseline paths whose content still matches the recorded hash.

    A baseline with no sidecar (older run) keeps the original behaviour: every
    listed path is treated as unchanged.
    """
    names = set(Path(baseline).read_text(errors='surrogateescape').splitlines())
    sidecar = Path(str(baseline) + '.hashes')
    if not sidecar.is_file():
        return names
    recorded = {}
    for line in sidecar.read_text(errors='surrogateescape').splitlines():
        name, _, digest = line.partition('\t')
        recorded[name] = digest
    return {name for name in names if name not in recorded or file_hash(name) == recorded[name]}


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
        old = unchanged_baseline(baseline)
    patterns = artifact_patterns()
    candidates = {os.fsdecode(p) for p in (diff.stdout + untracked.stdout).split(b'\0') if p}
    # `git diff` reports tracked files whatever the ignore rules say, and
    # `--exclude-standard` above only filters untracked ones. Without this a
    # file committed before its ignore rule existed lands in the review
    # document -- and the reviewer reads thousands of lines of it.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from project_paths import ignored
        candidates -= ignored('.', candidates)
    except ImportError:
        pass
    return sorted(p for p in candidates if p not in old and not any(fnmatch.fnmatchcase(p, pattern) for pattern in patterns))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--record-hashes':
        write_hashes(sys.argv[2])
        raise SystemExit(0)
    for path in paths(os.environ.get('WORKFLOW_UNTRACKED_BASELINE')):
        if '\n' in path or '\r' in path:
            raise SystemExit('Review cannot represent a filename containing a newline')
        print(path)
