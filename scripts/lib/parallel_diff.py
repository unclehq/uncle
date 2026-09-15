"""Compute independent file diffs concurrently, emit in input order."""
from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import sys


def file_diff(path, tracked_paths=None):
    tracked = path in tracked_paths if tracked_paths is not None else subprocess.run(['git', 'ls-files', '--error-unmatch', '--', path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    command = ['git', 'diff', 'HEAD', '--', path] if tracked else [
        'git', 'diff', '--no-index', '--', os.devnull, path]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode not in ((0,) if tracked else (0, 1)):
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout


def main():
    jobs = int(os.environ.get('WORKFLOW_VERIFY_JOBS', '4'))
    if not 1 <= jobs <= 8:
        raise ValueError('WORKFLOW_VERIFY_JOBS must be from 1 to 8')
    paths = [line.rstrip('\n') for line in sys.stdin if line.rstrip('\n')]
    if not paths:
        return
    listing = subprocess.run(['git', 'ls-files', '-z'], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, check=True)
    tracked = {os.fsdecode(path) for path in listing.stdout.split(b'\0') if path}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for output in pool.map(lambda path: file_diff(path, tracked), paths):
            sys.stdout.buffer.write(output)


if __name__ == '__main__':
    main()
