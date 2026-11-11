#!/usr/bin/env python3
"""Check record: sidecars, environment allow-list, snapshot, and rerun (AC-1..7)."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import check_record as cr  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.tree = self.tmp / 'tree'
        (self.tree / 'sub').mkdir(parents=True)
        (self.tree / 'a.txt').write_text('alpha\n')
        (self.tree / 'sub' / 'untracked.txt').write_text('untracked\n')  # no git at all: no commit needed
        (self.tree / 'run.sh').write_text('#!/bin/sh\ncat a.txt; echo done\n')
        os.chmod(self.tree / 'run.sh', 0o755)
        self.lines = []

    def tearDown(self):
        self._tmp.cleanup()

    def say(self, line):
        self.lines.append(line)

    def make(self, commands, snapshot=True, rewrites=None):
        """commands: list of dicts for write_sidecar; returns the record path."""
        rd = self.tmp / 'records'
        for i, c in enumerate(commands, 1):
            kw = dict(argv=['sh', 'run.sh'], cwd=str(self.tree), root=str(self.tree), status=0,
                      output=b'alpha\ndone\n')
            kw.update(c)
            cr.write_sidecar(str(rd), i, **kw)
        snap = cr.snapshot_capture(str(self.tree), str(self.tmp / 'store'), rewrites=rewrites) \
            if snapshot else None
        path = self.tmp / 'green-check.json'
        cr.assemble(str(rd), str(path), snap)
        return path

    def run_rerun(self, path, timeout=None):
        return cr.rerun(str(path), timeout, out=self.say)


class RecordTests(Fixture):
    def test_sidecar_fields_and_relative_cwd(self):
        e = cr.write_sidecar(str(self.tmp / 'r'), 1, ['x'], str(self.tree / 'sub'), str(self.tree), 0,
                             pipefail=True, timeout=5, output=b'o')
        self.assertEqual(e['cwd'], 'sub')
        for key in ('argv', 'status', 'pipefail', 'start', 'duration', 'timeout', 'output_sha256'):
            self.assertIn(key, e)
        self.assertTrue(e['pipefail'])

    def test_assemble_orders_and_flags_untrustworthy(self):
        rd = self.tmp / 'r'
        cr.write_sidecar(str(rd), 2, ['b'], str(self.tree), str(self.tree), 0)
        cr.write_sidecar(str(rd), 1, ['a'], str(self.tree), str(self.tree), 0)
        (rd / '4.json').write_text('{not json')
        rec = cr.assemble(str(rd), str(self.tmp / 'o.json'))
        self.assertEqual([c['index'] for c in rec['commands']], [1, 2, 4])
        self.assertTrue(rec['commands'][0]['trusted'])
        self.assertFalse(rec['commands'][2]['trusted'])  # unreadable and an index gap
        self.assertIn('unavailable', rec['commands'][2])

    def test_untrusted_entry_makes_rerun_unavailable(self):
        rd = self.tmp / 'r'
        (rd).mkdir()
        (rd / '1.json').write_text('{"index": 1}')
        snap = cr.snapshot_capture(str(self.tree), str(self.tmp / 'store'))
        cr.assemble(str(rd), str(self.tmp / 'o.json'), snap)
        code, status, _ = self.run_rerun(self.tmp / 'o.json')
        self.assertEqual((code != 0, status), (True, 'unavailable'))


class EnvironmentTests(Fixture):
    def test_keys_subset_and_canaries_absent(self):
        env = {'LANG': 'C', 'GITHUB_TOKEN': 'canary1', 'UNCLE_API_KEY': 'canary2', 'AWS_SECRET': 'c3',
               'UNCLE_ANYTHING': 'c4', 'PATH': '/x'}
        block = cr.capture_environment(env)
        self.assertTrue(set(block['variables']) <= set(cr.ALLOWED_ENV_NAMES))
        self.assertEqual(block['variables'], {'LANG': 'C'})
        self.assertNotIn('PATH', block['variables'])
        text = json.dumps(block)
        for canary in ('canary1', 'canary2', 'c3', 'c4'):
            self.assertNotIn(canary, text)

    def test_allow_list_has_no_credential_names(self):
        for name in cr.ALLOWED_ENV_NAMES:
            self.assertFalse(cr.CREDENTIAL_RE.search(name), name)

    def test_canaries_absent_from_record_file(self):
        os.environ['UNCLE_CANARY_TOKEN'] = 'canary-secret-value'
        try:
            path = self.make([{}])
        finally:
            del os.environ['UNCLE_CANARY_TOKEN']
        self.assertNotIn('canary-secret-value', path.read_text())

    def test_each_field_altered_blocks_rerun_with_no_command_run(self):
        sentinel = self.tree / 'sentinel'
        cmd = {'argv': ['sh', '-c', 'touch %s' % sentinel], 'output': b''}
        for mutate in (lambda e: e.__setitem__('platform', 'other'),
                       lambda e: e.__setitem__('machine', 'other'),
                       lambda e: e['tools'].__setitem__('git', 'git version 0.0'),
                       lambda e: e['tools'].__setitem__('python3', None),
                       lambda e: e['variables'].__setitem__('TZ', 'Mars/Base')):
            path = self.make([cmd])
            rec = json.loads(path.read_text())
            mutate(rec['environment'])
            path.write_text(json.dumps(rec))
            code, status, _ = self.run_rerun(path)
            self.assertNotEqual(code, 0)
            self.assertEqual(status, 'environment-mismatch')
            self.assertFalse(sentinel.exists())
            import shutil
            shutil.rmtree(self.tmp / 'records'); shutil.rmtree(self.tmp / 'store')

    def test_child_does_not_inherit_parent_credentials(self):
        cmd = {'argv': ['sh', '-c', 'env | sort | cut -d= -f1'], 'output': b''}
        path = self.make([cmd])
        rec = json.loads(path.read_text())
        os.environ['UNCLE_CANARY_TOKEN'] = 'leak'
        os.environ['GITHUB_TOKEN'] = 'leak'
        try:
            env = cr.execution_environment(rec['environment']['variables'], str(self.tmp))
        finally:
            del os.environ['UNCLE_CANARY_TOKEN']; del os.environ['GITHUB_TOKEN']
        self.assertTrue(set(env) <= set(cr.EXEC_ENV_NAMES))
        self.assertNotIn('GITHUB_TOKEN', env)
        import subprocess
        out = subprocess.run(['/usr/bin/env'], env=env, capture_output=True, text=True).stdout
        self.assertNotIn('leak', out)


class SnapshotTests(Fixture):
    def test_roundtrip_includes_untracked_and_mode(self):
        snap = cr.snapshot_capture(str(self.tree), str(self.tmp / 's'), rewrites={'a.txt': 'rewritten copy'})
        dest = self.tmp / 'd'
        dest.mkdir()
        cr.snapshot_restore(snap['store'], snap['digest'], str(dest))
        self.assertEqual((dest / 'sub' / 'untracked.txt').read_text(), 'untracked\n')
        self.assertTrue(os.access(dest / 'run.sh', os.X_OK))
        self.assertTrue(any(e.get('rewrite') for e in snap['entries']))

    def test_tampered_missing_and_wrong_digest(self):
        snap = cr.snapshot_capture(str(self.tree), str(self.tmp / 's'))
        blob = Path(snap['store']) / 'files' / snap['entries'][0]['sha256']
        blob.write_text('tampered')
        with self.assertRaises(cr.SnapshotMismatch):
            cr.snapshot_restore(snap['store'], snap['digest'], str(self.tmp / 'd1'))
        blob.unlink()
        with self.assertRaises(cr.SnapshotMismatch):
            cr.snapshot_restore(snap['store'], snap['digest'], str(self.tmp / 'd2'))
        with self.assertRaises(cr.SnapshotMismatch):
            cr.snapshot_restore(snap['store'], '0' * 64, str(self.tmp / 'd3'))


class RerunTests(Fixture):
    def test_match_in_tree_without_commit_or_git(self):
        code, status, _ = self.run_rerun(self.make([{}]))
        self.assertEqual((code, status), (0, 'match'))
        self.assertTrue(any(line.startswith('rerun: ') for line in self.lines))

    def test_mismatch_on_changed_output_and_status(self):
        self.assertEqual(self.run_rerun(self.make([{'output': b'different'}]))[:2], (1, 'mismatch'))

    def test_snapshot_tamper_before_any_command(self):
        sentinel = self.tree / 'sentinel'
        path = self.make([{'argv': ['sh', '-c', 'touch %s' % sentinel], 'output': b''}])
        rec = json.loads(path.read_text())
        rec['snapshot']['digest'] = '1' * 64
        path.write_text(json.dumps(rec))
        code, status, _ = self.run_rerun(path)
        self.assertEqual((code != 0, status), (True, 'snapshot-mismatch'))
        self.assertFalse(sentinel.exists())

    def test_replays_from_snapshot_not_live_tree(self):
        path = self.make([{}])
        (self.tree / 'a.txt').write_text('changed after check\n')
        self.assertEqual(self.run_rerun(path)[:2], (0, 'match'))

    def test_cwd_containment(self):
        for bad in ('/tmp', '../x', 'sub/../..'):
            path = self.make([{}])
            rec = json.loads(path.read_text())
            rec['commands'][0]['cwd'] = bad
            path.write_text(json.dumps(rec))
            code, status, _ = self.run_rerun(path)
            self.assertEqual((code != 0, status), (True, 'unavailable'), bad)
            import shutil
            shutil.rmtree(self.tmp / 'records'); shutil.rmtree(self.tmp / 'store')

    def test_symlink_escape_rejected_and_in_root_ok(self):
        outside = self.tmp / 'outside'
        outside.mkdir()
        with self.assertRaises(ValueError):
            link_root = self.tmp / 'lr'
            link_root.mkdir()
            os.symlink(outside, link_root / 'esc')
            cr.contained_cwd(str(link_root), 'esc')
        self.assertTrue(cr.contained_cwd(str(self.tree), 'sub').endswith('sub'))

    def test_browser_record_unavailable_and_nothing_runs(self):
        sentinel = self.tree / 'sentinel'
        path = self.make([{'argv': ['sh', '-c', 'touch %s' % sentinel], 'output': b''},
                          {'argv': ['npx', 'playwright', 'test']}])
        code, status, detail = self.run_rerun(path)
        self.assertEqual((code != 0, status, detail), (True, 'unavailable', 'browser required'))
        self.assertFalse(sentinel.exists())

    def test_legacy_record_unavailable_nonzero(self):
        legacy = self.tmp / 'legacy.json'
        legacy.write_text(json.dumps({'verdict': 'pass'}))
        code, status, _ = self.run_rerun(legacy)
        self.assertEqual((code != 0, status), (True, 'unavailable'))
        self.assertEqual(self.run_rerun(self.tmp / 'missing.json')[1], 'unavailable')

    def test_timeout_rule(self):
        self.assertEqual(cr.effective_timeout(10, None), 10)
        self.assertEqual(cr.effective_timeout(10, 3.0), 3.0)
        self.assertEqual(cr.effective_timeout(10, 99.0), 10)
        self.assertEqual(cr.effective_timeout(None, 4.0), 4.0)

    def test_invalid_timeout_rejected_before_execution(self):
        sentinel = self.tree / 'sentinel'
        path = self.make([{'argv': ['sh', '-c', 'touch %s' % sentinel], 'output': b''}])
        for bad in ('0', '-1', 'abc', 'nan', 'inf', ''):
            code, status, _ = self.run_rerun(path, bad)
            self.assertEqual((code != 0, status), (True, 'usage'), bad)
            self.assertFalse(sentinel.exists())

    def test_shorter_timeout_reports_mismatch_not_pass(self):
        path = self.make([{'argv': ['sh', '-c', 'sleep 5'], 'output': b'', 'timeout': 60}])
        code, status, _ = self.run_rerun(path, '0.2')
        self.assertEqual((code, status), (1, 'mismatch'))
        self.assertTrue(any('timed out' in line for line in self.lines))

    def test_pipefail_replayed(self):
        path = self.make([{'argv': ['bash', '-c', 'false | cat'], 'status': 1, 'pipefail': True,
                           'output': b''}])
        self.assertEqual(self.run_rerun(path)[:2], (0, 'match'))


if __name__ == '__main__':
    unittest.main()
