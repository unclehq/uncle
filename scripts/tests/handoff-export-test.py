"""Hand-off publish mode: applying the hand-off to the base commit gives exactly the audited tree (issue 205)."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[2] / 'scripts' / 'lib'
GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']


def run(cwd, *args, env=None, data=None):
    return subprocess.run(args, cwd=cwd, check=True, input=data, stdout=subprocess.PIPE,
                          env=dict(os.environ, **(env or {}))).stdout.decode().strip()


class Handoff(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.repo = d.name
        r = self.repo
        run(r, 'git', 'init', '-q', '-b', 'main')
        Path(r, 'keep.txt').write_text('keep\n')
        Path(r, 'edit.txt').write_text('old\n')
        Path(r, 'gone.txt').write_text('bye\n')
        run(r, *GIT, 'add', '-A')
        run(r, *GIT, 'commit', '-qm', 'base')
        self.base = run(r, 'git', 'rev-parse', 'HEAD')
        Path(r, 'edit.txt').write_text('new\n')
        Path(r, 'gone.txt').unlink()
        Path(r, 'sub').mkdir()
        Path(r, 'sub', 'tool.sh').write_bytes(b'#!/bin/sh\necho \xff\x00bin\n')
        os.chmod(Path(r, 'sub', 'tool.sh'), 0o755)
        # The audited tree, built the way the driver does: a temporary index, never the user's.
        env = {'GIT_INDEX_FILE': os.path.join(r, '.git', 'tmp-index')}
        run(r, 'git', 'add', '-A', env=env)
        self.tree = run(r, 'git', 'write-tree', env=env)
        run(r, 'git', 'reset', '-q', '--hard')
        run(r, 'git', 'clean', '-fdq')
        wf = Path(r, '.uncle', 'workflow', 'pr')
        wf.mkdir(parents=True)
        (wf / 'journal.json').write_text(json.dumps({
            'commit_tree': self.tree, 'original_head': self.base, 'head_branch': 'uncle/x', 'origin': 'o/r\t7\tgh',
            'base_repo': 'o/r', 'audit_hash': 'a' * 64,
            'attestation': {'issue': 'o/r#7', 'review_result': 'NOT_READY', 'tree': self.tree[:12], 'version': '1'}}))
        (wf.parent / 'audit-verdict.original').write_text('run\tNOT_READY\t' + 'a' * 64 + '\n')

    def export(self):
        run(self.repo, sys.executable, str(LIB / 'handoff_export.py'))
        return json.loads(Path(self.repo, '.uncle', 'handoff', 'handoff.json').read_text())

    def test_applying_handoff_gives_the_audited_tree(self):
        h = self.export()
        self.assertEqual((h['base_commit'], h['head_branch'], h['draft'], h['audit_verdict']),
                         (self.base, 'uncle/x', True, 'NOT_READY'))
        self.assertIn('UNCLE CHANGE ATTESTATION', h['pr_body'])
        self.assertEqual({c['path']: c['action'] for c in h['changes']},
                         {'edit.txt': 'modify', 'gone.txt': 'delete', 'sub/tool.sh': 'add'})
        # Apply to a fresh checkout of the base commit through a temporary index and compare trees.
        r = self.repo
        env = {'GIT_INDEX_FILE': os.path.join(r, '.git', 'apply-index')}
        base_oid = h['base_commit']
        run(r, 'git', 'read-tree', base_oid, env=env)
        for c in h['changes']:
            if c['action'] == 'delete':
                run(r, 'git', 'update-index', '--force-remove', c['path'], env=env)
                continue
            oid = run(r, 'git', 'hash-object', '-w', '--stdin', env=env, data=base64.b64decode(c['content']))
            self.assertEqual(oid, c['oid'])
            run(r, 'git', 'update-index', '--add', '--cacheinfo', '%s,%s,%s' % (c['mode'], oid, c['path']), env=env)
        self.assertEqual(run(r, 'git', 'write-tree', env=env), self.tree)
        self.assertEqual([c['mode'] for c in h['changes'] if c['path'] == 'sub/tool.sh'], ['100755'])

    def test_missing_journal_fails_nonzero(self):
        Path(self.repo, '.uncle/workflow/pr/journal.json').unlink()
        p = subprocess.run([sys.executable, str(LIB / 'handoff_export.py')], cwd=self.repo, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b'No audited change', p.stderr)


if __name__ == '__main__':
    unittest.main()
