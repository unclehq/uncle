#!/usr/bin/env python3
"""Golden observations captured before sharing traversal; no model or Git fixtures."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

LIB = Path(__file__).resolve().parents[1] / 'lib'
CORPUS = Path(__file__).with_name('fixtures') / 'runner-events'
CALLERS = ('publish_agent_artifact', 'recover_investigation')
KIND = 'checklist-execution-worker-packet'
HEADING = '## Required functionality'


def load(lib, name):
    spec = importlib.util.spec_from_file_location('isolated_' + name, lib / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe(lib, case, name, direct=False):
    """Capture bytes, status, diagnostics and API write order on the same inputs."""
    module = load(lib, name)
    with tempfile.TemporaryDirectory(prefix='runner events ') as temp:
        root = Path(temp)
        log = root / 'events.jsonl'
        source = 'empty' if case.startswith('fallback-') else case
        log.write_bytes((CORPUS / (source + '.jsonl')).read_bytes())
        if case.startswith('fallback-'):
            view = root / '.uncle/docs/PROJECT_PLAN.md'
            view.parent.mkdir(parents=True)
            view.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'plan',
                                       'narrative': '# Fallback', 'verification_commands': 'true'})
                            if case == 'fallback-json' else '# Already rendered\n')
        target = root / 'output'
        args = ([str(log), str(target), '--heading', HEADING] if name == 'recover_investigation'
                else [str(log), str(target), '--kind', KIND])
        if name == 'publish_agent_artifact':
            args = ['project-plan', str(log), str(root)]
        writes = []
        original = Path.write_text

        def record(path, *a, **kw):
            writes.append(path.relative_to(root).as_posix())
            return original(path, *a, **kw)

        if direct:
            result = subprocess.run([sys.executable, '-B', str(lib / (name + '.py')), *args],
                                    cwd=root, capture_output=True)
            status, stdout, stderr = result.returncode, result.stdout, result.stderr
        else:
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), patch.object(Path, 'write_text', record):
                try:
                    if name == 'publish_agent_artifact':
                        try:
                            module.publish(*args)
                            status = 0
                        except (OSError, ValueError) as error:
                            print('canonical agent artifact: ' + str(error), file=sys.stderr)
                            status = 1
                    else:
                        status = module.main(args)
                except AttributeError as error:
                    # Existing uncaught non-object event error; retain it, not a repair.
                    status = 1
                    print('AttributeError: ' + str(error), file=sys.stderr)
            stdout, stderr = stdout.getvalue().encode(), stderr.getvalue().encode()
        if stderr.startswith(b'Traceback (most recent call last):'):
            # Source locations necessarily move; the exception type/message must not.
            stderr = stderr.splitlines()[-1] + b'\n'
        files = {p.relative_to(root).as_posix(): p.read_bytes().hex()
                 for p in sorted(root.rglob('*')) if p.is_file() and
                 (p == target or '.uncle' in p.parts)}
        observed = {'status': status, 'stdout': stdout.decode().replace(str(root), '<ROOT>'),
                    'stderr': stderr.decode().replace(str(root), '<ROOT>'), 'files': files}
        if not direct:
            observed['writes'] = writes
        return observed


class RunnerEvents(unittest.TestCase):
    def test_ordered_traversal(self):
        expected = json.loads((CORPUS / 'golden.json').read_text())['traversal']
        for name in CALLERS:
            module = load(LIB, name)
            for corpus, rows in expected.items():
                actual = []
                for line in (CORPUS / corpus).read_text(encoding='utf-8', errors='replace').splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    actual.append(list(module.texts(event)))
                self.assertEqual(actual, rows, (name, corpus))

    def test_golden_api_and_direct_scripts(self):
        golden = json.loads((CORPUS / 'golden.json').read_text())['callers']
        for case, callers in golden.items():
            for name, expected in callers.items():
                with self.subTest(case=case, caller=name):
                    self.assertEqual(observe(LIB, case, name), expected)
                    self.assertEqual(observe(LIB, case, name, direct=True),
                                     {k: v for k, v in expected.items() if k != 'writes'})

    def test_importlib_from_outside_repository_has_no_path_or_runtime_side_effects(self):
        code = '''import importlib.util, os, pathlib, sys
from unittest.mock import patch
before = list(sys.path)
cwd = os.getcwd()
with patch('subprocess.Popen', side_effect=AssertionError('process at import')), \\
     patch.object(pathlib.Path, 'read_text', side_effect=AssertionError('data read at import')), \\
     patch.object(pathlib.Path, 'mkdir', side_effect=AssertionError('mkdir at import')), \\
     patch('os.chdir', side_effect=AssertionError('chdir at import')):
    spec = importlib.util.spec_from_file_location('arbitrary_name', sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
assert sys.path == before
assert os.getcwd() == cwd
assert list(module.texts({'result': 'ok'})) == ['ok']
'''
        with tempfile.TemporaryDirectory() as temp:
            for name in CALLERS:
                result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(LIB / (name + '.py'))],
                                        cwd=temp, capture_output=True)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'', b''), name)


if __name__ == '__main__':
    unittest.main()
