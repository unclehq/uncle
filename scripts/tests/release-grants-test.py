#!/usr/bin/env python3
"""The release-grant checker accepts only the exact signed-link grant."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'scripts/lib/check_release_grants.py'
DOC = ROOT / 'docs/preview-link-release.md'
GRANT_PATH = '/sandbox/{sandboxId}/ports/{port}/signed-preview-url'
GRANT = {'publisher': 'daytona', 'method': 'GET', 'path': GRANT_PATH, 'require_approval': False}


def run(path):
    p = subprocess.run([sys.executable, '-B', str(CHECKER), str(path)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


class GrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, content):
        p = os.path.join(self.tmp.name, 'release.json')
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))
        return p

    def assertFails(self, code, path):
        rc, out, err = run(path)
        self.assertEqual(rc, code, err)
        self.assertEqual(out, '')
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertTrue(err.strip())
        return err

    def mutated(self, **changes):
        g = copy.deepcopy(GRANT)
        g.update(changes)
        return {'grants': [g]}

    def test_ok_top_level(self):
        rc, out, err = run(self.write(GRANT))
        self.assertEqual((rc, out.strip(), err), (0, 'OK', ''))

    def test_ok_nested_in_list(self):
        doc = {'name': 'x', 'grants': [{'publisher': 'other'}, GRANT]}
        rc, out, err = run(self.write(doc))
        self.assertEqual((rc, out.strip(), err), (0, 'OK', ''))

    def test_missing_grant(self):
        self.assertFails(1, self.write({'grants': []}))

    def test_require_approval_true(self):
        self.assertFails(1, self.write(self.mutated(require_approval=True)))

    def test_require_approval_absent(self):
        doc = self.mutated()
        del doc['grants'][0]['require_approval']
        self.assertFails(1, self.write(doc))

    def test_require_approval_wrong_types(self):
        for bad in (0, None, 'false', [], [False], {}, {'a': False}):
            with self.subTest(value=bad):
                self.assertFails(1, self.write(self.mutated(require_approval=bad)))

    def test_wrong_publisher(self):
        self.assertFails(1, self.write(self.mutated(publisher='other')))

    def test_wrong_method(self):
        self.assertFails(1, self.write(self.mutated(method='POST')))

    def test_wrong_path(self):
        self.assertFails(1, self.write(self.mutated(path='/sandbox/{sandboxId}/ports/{port}/preview-url')))

    def test_duplicate_key_conflicting_approval(self):
        text = ('{"publisher":"daytona","method":"GET","path":"%s",'
                '"require_approval":true,"require_approval":false}' % GRANT_PATH)
        err = self.assertFails(2, self.write(text))
        self.assertIn('duplicate key', err)
        self.assertNotIn('require_approval', err)
        self.assertNotIn('daytona', err)

    def test_duplicate_key_nested(self):
        text = '{"grants":[{"secret-name":1,"secret-name":2}]}'
        err = self.assertFails(2, self.write(text))
        self.assertIn('duplicate key', err)
        self.assertNotIn('secret-name', err)

    def test_invalid_json(self):
        err = self.assertFails(2, self.write('{not json SECRETVALUE'))
        self.assertNotIn('SECRETVALUE', err)

    def test_missing_file(self):
        self.assertFails(2, os.path.join(self.tmp.name, 'absent.json'))

    def test_usage(self):
        for args in ([], ['a', 'b']):
            p = subprocess.run([sys.executable, '-B', str(CHECKER)] + args,
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(p.stdout, '')
            self.assertEqual(len(p.stderr.strip().splitlines()), 1)

    def test_doc_names_grant_path(self):
        self.assertTrue(DOC.is_file())
        self.assertIn(GRANT_PATH, DOC.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
