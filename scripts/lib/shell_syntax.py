"""Execute known verification loops with reliable aggregate results."""
from concurrent.futures import ThreadPoolExecutor
import glob
import os
from pathlib import Path
import re
import subprocess
import sys

from process_tree import bash_executable


def syntax_command(command, jobs):
    # This standard suite loop uses the bounded parallel suite runner.
    test_loop = (r'\s*for t in scripts/tests/\*-test\.sh;\s*'
                 r'do bash "\$t"(?:\s*\|\|\s*exit 1)?;\s*done\s*')
    if re.fullmatch(test_loop, command):
        return [bash_executable(), str(Path(__file__).resolve().parents[1] / 'run-shell-tests.sh'),
                '--project-root', '.', '--jobs', str(jobs)]
    # Only this known pure syntax loop is eligible; arbitrary shell commands
    # retain their original execution and ordering semantics.
    pattern = (r'\s*for f in scripts/\*\.sh scripts/lib/\*\.sh scripts/tests/\*\.sh;\s*'
               r'do bash -n "\$f"(?:\s*\|\|\s*exit 1)?;\s*done\s*')
    if not re.fullmatch(pattern, command):
        return None
    return [sys.executable, str(Path(__file__).resolve()), str(jobs)]


def check_files(files, jobs, bash):
    def check(path):
        result = subprocess.run([bash, '-n', path], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        return path, result.returncode, result.stdout
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(check, files))


def main():
    if sys.argv[1] in ("--command", "--command-file"):
        if sys.argv[1] == "--command-file":
            # Load original bytes in Python, avoiding MSYS argument conversion
            # of control characters between Bash and native Windows Python.
            raw = Path(sys.argv[2]).read_bytes().split(b'\n')[int(sys.argv[3]) - 1]
            command, jobs = raw.removesuffix(b'\r').decode('utf-8'), int(sys.argv[4])
        else:
            command, jobs = sys.argv[2], int(sys.argv[3])
        argv = syntax_command(command, jobs) or [bash_executable(), '-c', command]
        if os.name == 'nt':
            # Windows execv uses CRT argument joining, which loses quoting for
            # paths such as C:\Program Files\Git and shell command strings.
            # Popen quotes the argument list for CreateProcess and wait returns
            # the real child exit code rather than an apparent launch success.
            return subprocess.run(argv).returncode
        os.execv(argv[0], argv)
    jobs = int(sys.argv[1])
    if not 1 <= jobs <= 8:
        raise ValueError('Syntax check workers must be from 1 to 8')
    files = []
    for pattern in ('scripts/*.sh', 'scripts/lib/*.sh', 'scripts/tests/*.sh'):
        # Preserve Bash's failure on an unmatched glob.
        files.extend(Path(path).as_posix() for path in (sorted(glob.glob(pattern)) or [pattern]))
    results = check_files(files, jobs, bash_executable())
    for path, status, output in results:
        print(('FAIL' if status else 'PASS') + ' bash -n ' + path, flush=True)
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    return int(any(status for _, status, _ in results))


if __name__ == '__main__':
    raise SystemExit(main())
