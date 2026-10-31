"""Private preflight snapshots and OS-confined probe commands."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


class Violation(ValueError):
    pass


def copy_project(source, target):
    source, target = Path(source).resolve(), Path(target)
    def ignore(directory, names):
        skipped = {name for name in names if name in ('.git', '.uncle', '__pycache__')}
        for name in names:
            path = Path(directory) / name
            if path.is_symlink():
                resolved = path.resolve()
                if not resolved.is_relative_to(source) or any(p in ('.git', '.uncle') for p in resolved.relative_to(source).parts):
                    skipped.add(name)
        return skipped
    shutil.copytree(source, target, ignore=ignore, symlinks=True)
    for directory, names, files in os.walk(target):
        for name in names + files:
            path = Path(directory) / name
            if path.is_symlink():
                original = source / path.relative_to(target)
                destination = target / original.resolve().relative_to(source)
                path.unlink()
                path.symlink_to(os.path.relpath(destination, path.parent))
    from self_hosted import copy_generated_documents
    copy_generated_documents(source, target)


def snapshot(root):
    result = {}
    for directory, names, files in os.walk(root):
        relative = Path(directory).relative_to(root).parts
        if relative == ('.uncle',):
            names[:] = [n for n in names if n in ('docs', 'workflow')]
            files = []
        elif relative == ('.uncle', 'workflow'):
            names[:] = [n for n in names if n == 'documents']
            files = []
        names.sort()
        for name in sorted(files + [n for n in names if (Path(directory) / n).is_symlink()]):
            path = Path(directory) / name
            result[path.relative_to(root).as_posix()] = (os.readlink(path) if path.is_symlink() else
                                                       hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def prepare(source):
    directory = Path(tempfile.mkdtemp(prefix='uncle-preflight-')).resolve()
    try:
        copy_project(source, directory / 'project')
        (directory / 'snapshot.json').write_text(json.dumps(snapshot(directory / 'project')))
    except BaseException:
        shutil.rmtree(directory)
        raise
    return directory / 'project'


def check(root, worker):
    root = Path(root)
    before = json.loads((root.parent / 'snapshot.json').read_text())
    after = snapshot(root)
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    if changed:
        raise Violation('%s: read-only preflight project changed: %s' % (worker, ', '.join(changed[:10])))


def probe_command(command, directory):
    """Only the private probe tree is writable, including through absolute paths."""
    from process_tree import bash_executable
    directory = str(Path(directory).resolve())
    shell = [bash_executable(), '-c', command]
    if sys.platform == 'darwin' and shutil.which('sandbox-exec'):
        profile = ('(version 1)(allow default)(deny file-write*)'
                   '(allow file-write* (subpath %s) (literal "/dev/null"))'
                   '(deny process-exec (literal "/usr/bin/sandbox-exec"))') % json.dumps(directory)
        return ['sandbox-exec', '-p', profile] + shell
    if sys.platform.startswith('linux') and shutil.which('bwrap'):
        return ['bwrap', '--die-with-parent', '--ro-bind', '/', '/', '--bind', directory, directory,
                '--dev', '/dev', '--proc', '/proc', '--chdir', directory + '/project', '--'] + shell
    raise ValueError('Preflight shell probes require sandbox-exec or bubblewrap; no command was run')


def main(argv):
    if argv[0] == 'prepare':
        print(prepare(argv[1]))
    elif argv[0] == 'check':
        check(argv[1], argv[2])
    elif argv[0] == 'remove':
        root = Path(argv[1]).resolve()
        if root.name != 'project' or not root.parent.name.startswith('uncle-preflight-'):
            raise ValueError('invalid preflight scratch path')
        shutil.rmtree(root.parent)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, Violation) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
