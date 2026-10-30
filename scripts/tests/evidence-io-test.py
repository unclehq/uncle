#!/usr/bin/env python3
"""Evidence fallback and caller-policy contracts captured before extraction."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

LIB = Path(__file__).resolve().parents[1] / 'lib'
GOLDEN = Path(__file__).with_name('fixtures') / 'evidence-io.json'


def load(lib, name):
    spec = importlib.util.spec_from_file_location('isolated_' + name, lib / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def primitives(lib):
    observed = {}
    with tempfile.TemporaryDirectory(prefix='evidence io ') as temp:
        root = Path(temp)
        paths = {'missing': root / 'missing', 'directory': root}
        for name, raw in [('empty', b''), ('text', 'caf\u00e9\r\nline\tend\n'.encode()), ('invalid-utf8', b'\xff\x00\r\n')]:
            paths[name] = root / name
            paths[name].write_bytes(raw)
        for name in ('attestation', 'envelope'):
            module = load(lib, name)
            digest = module._digest if name == 'attestation' else module.sha256_file
            observed[name] = {key: [module._read(path), digest(path)] for key, path in paths.items()}
            records = []
            state = root / name
            state.mkdir()
            saved = state / 'session-totals.json'
            records.append(module._records(state))
            for raw in (b'', b'{broken', b'\xff', b'null', b'[]', b'"scalar"', b'7', b'{}',
                        b'{"records":null}', b'{"records":{}}',
                        b'{"records":[null,7,"bad",[],{}, {"stage":"first"}, {"stage":"last"}]}'):
                saved.write_bytes(raw)
                records.append(module._records(state))
            saved.unlink()
            saved.mkdir()
            records.append(module._records(state))
            observed[name]['records'] = records
        attestation = load(lib, 'attestation')
        state = root / 'tsv'
        state.mkdir()
        observed['tsv'] = []
        for raw in ('', '\tignored\n', 'PASS\tx\nFIXED\ty\nPREEXISTING\tz\nREGRESSION\tw\n',
                    'garbage\nPASS\n\tignored\n', 'run\tREADY\thash\n',
                    'run\tREADY\thash\textra\n', 'run\tUNKNOWN\thash\n', 'run\tINVALID\thash\n'):
            path = state / 'green-check.tsv'
            path.write_text(raw)
            observed['tsv'].append([attestation._verification(state), attestation._verdict_row(path)])
    return observed


def envelope_observation(lib, direct=False):
    module = load(lib, 'envelope')
    with tempfile.TemporaryDirectory(prefix='envelope io ') as temp:
        root = Path(temp)
        state = root / 'state'
        state.mkdir()
        (state / 'envelopes.attempts').write_text('bad\tnope\nverification\t2\nverification\t3\n\n')
        (state / 'session-totals.json').write_text(json.dumps({'records': [None, {},
            {'kind': 'agent', 'stage': 'implementation', 'runner': '/bin/agent-first.sh', 'model': 'first',
             'ended_at': 1, 'process_exit': 0},
            {'kind': 'agent', 'stage': 'implementation', 'runner': '/bin/agent-last.sh', 'model': 'last',
             'ended_at': 2, 'process_exit': 1},
            {'kind': 'agent', 'stage': 'implementation', 'runner': 'ignored', 'speculative': True, 'ended_at': 3}]}))
        (root / 'evidence.txt').write_bytes(b'evidence\xff\n')
        (root / 'unreadable').mkdir()
        # The callers intentionally apply different selection rules to the same records.
        attestation = load(lib, 'attestation')
        sealed = attestation.seal({'commit_tree': 'a' * 40, 'origin': 'owner/repo\t59\tgh'},
                                  state=state, root=root, version='fixture')
        calls = []
        original_text, original_bytes = Path.read_text, Path.read_bytes
        original_write = Path.write_text

        def text(path, *args, **kw):
            calls.append(['read_text', path.relative_to(root).as_posix()])
            return original_text(path, *args, **kw)

        def binary(path, *args, **kw):
            calls.append(['read_bytes', path.relative_to(root).as_posix()])
            return original_bytes(path, *args, **kw)

        def write(path, *args, **kw):
            calls.append(['write_text', path.relative_to(root).as_posix()])
            return original_write(path, *args, **kw)

        def atomic(path, data):
            calls.append(['atomic_write', path.relative_to(root).as_posix()])
            return original_atomic(path, data)

        env = dict(os.environ, UNCLE_VERSION='fixture')
        if direct:
            result = subprocess.run([sys.executable, '-B', str(lib / 'envelope.py'), 'write',
                '--state', str(state), '--stage', 'verification', '--result', 'pass',
                '--producer-stage', 'implementation', '--producer-kind', 'agent',
                '--evidence', 'evidence.txt', 'missing', 'unreadable'], cwd=root, env=env, capture_output=True)
            status, stdout, stderr = result.returncode, result.stdout.decode(), result.stderr.decode()
        else:
            original_atomic = module._atomic_write
            with patch.dict(os.environ, UNCLE_VERSION='fixture'), patch.object(Path, 'read_text', text), \
                 patch.object(Path, 'read_bytes', binary), patch.object(Path, 'write_text', write), \
                 patch.object(module, '_atomic_write', atomic):
                module.write_envelope(state, 'verification', 'pass', root=root,
                                      evidence=['evidence.txt', 'missing', 'unreadable'],
                                      producer_stage='implementation', producer_kind='agent')
            status, stdout, stderr = 0, 'Envelope: verification pass\n', ''
        body = json.loads((state / 'envelopes/verification.json').read_bytes())
        body['produced_at'] = '<TIME>'
        observed = {'status': status, 'stdout': stdout, 'stderr': stderr,
                    'envelope': module.canonical(body).decode(),
                    'attempts': (state / 'envelopes.attempts').read_text(),
                    'sealed': sealed, 'rendered': attestation.render(sealed)}
        if not direct:
            observed['calls'] = calls
        return observed


class EvidenceIO(unittest.TestCase):
    def test_fallbacks_and_malformed_records_and_tsv(self):
        expected = json.loads(GOLDEN.read_text())
        self.assertEqual(primitives(LIB), expected['primitives'])

    def test_permission_errors_have_the_same_empty_fallbacks(self):
        for name in ('attestation', 'envelope'):
            module = load(LIB, name)
            with patch.object(Path, 'read_text', side_effect=PermissionError('denied')) as read:
                self.assertEqual(module._read('denied'), '')
                read.assert_called_once_with(encoding='utf-8', errors='replace')
            with patch.object(Path, 'read_text', side_effect=PermissionError('denied')) as read:
                self.assertEqual(module._records('denied'), [])
                read.assert_called_once_with(encoding='utf-8')
            with patch.object(Path, 'read_bytes', side_effect=PermissionError('denied')) as read:
                digest = module._digest if name == 'attestation' else module.sha256_file
                self.assertEqual(digest('denied'), '')
                read.assert_called_once_with()

    def test_non_io_errors_still_propagate(self):
        for name in ('attestation', 'envelope'):
            module = load(LIB, name)
            with patch.object(Path, 'read_text', side_effect=TypeError('bad path')):
                for function in (module._read, module._records):
                    with self.assertRaisesRegex(TypeError, '^bad path$'):
                        function('path')
            with patch.object(Path, 'read_bytes', side_effect=TypeError('bad path')):
                with self.assertRaisesRegex(TypeError, '^bad path$'):
                    (module._digest if name == 'attestation' else module.sha256_file)('path')

    def test_caller_outputs_and_io_order_match_golden(self):
        expected = json.loads(GOLDEN.read_text())['envelope']
        self.assertEqual(envelope_observation(LIB), expected)
        self.assertEqual(envelope_observation(LIB, direct=True),
                         {k: v for k, v in expected.items() if k != 'calls'})

    def test_importlib_and_direct_attestation_are_inert_outside_repository(self):
        code = '''import importlib.util, os, pathlib, sys
from unittest.mock import patch
before = list(sys.path)
with patch('subprocess.Popen', side_effect=AssertionError('process at import')), \\
     patch.object(pathlib.Path, 'read_text', side_effect=AssertionError('data read at import')), \\
     patch.object(pathlib.Path, 'mkdir', side_effect=AssertionError('mkdir at import')), \\
     patch('os.chdir', side_effect=AssertionError('chdir at import')):
    spec = importlib.util.spec_from_file_location('arbitrary_name', sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
assert sys.path == before
'''
        with tempfile.TemporaryDirectory() as temp:
            for name in ('attestation', 'envelope'):
                result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(LIB / (name + '.py'))],
                                        cwd=temp, capture_output=True)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'', b''), name)
            result = subprocess.run([sys.executable, '-B', str(LIB / 'attestation.py')], cwd=temp, capture_output=True)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'', b''))


if __name__ == '__main__':
    unittest.main()
