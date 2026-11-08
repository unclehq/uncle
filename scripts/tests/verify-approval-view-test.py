#!/usr/bin/env python3
"""`uncle verify` must check a committed Markdown view against the digest of
that Markdown, not against the canonical JSON the driver's gate approved, and
must report every failing check rather than stopping at the first.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import envelope  # noqa: E402

VERIFY = ROOT / 'scripts/uncle-verify.py'
spec = importlib.util.spec_from_file_location('uncle_verify', VERIFY)
uv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uv)

sha = lambda data: hashlib.sha256(data).hexdigest()


class ViewDigestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null',
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t', GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        self.git('init', '-q', '-b', 'main')
        self.state = self.repo / '.uncle/workflow'
        (self.state / 'approvals').mkdir(parents=True)
        (self.state / 'documents').mkdir()
        (self.repo / '.uncle/docs').mkdir()
        self.cwd = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(['git', *args], cwd=self.repo, env=self.env, check=True, stdout=subprocess.PIPE)

    def approve(self, name, markdown, canonical=None):
        """Approve NAME the way the driver does: the canonical JSON when there is one, else the view."""
        (self.repo / '.uncle/docs' / (name + '.md')).write_text(markdown)
        approved = markdown.encode()
        if canonical is not None:
            (self.state / 'documents' / (name + '.json')).write_text(canonical)
            approved = canonical.encode()
        (self.state / 'approvals' / (name + '.sha256')).write_text(sha(approved) + '\n')
        (self.state / 'approvals' / (name + '.gate-action')).write_text('ACKNOWLEDGE\n')
        (self.state / 'approvals' / (name + '.approved-by')).write_text('Brian\n')

    def statement(self, names):
        envelope.write_envelope(self.state, 'plan', 'pass', root=self.repo, approvals=names)
        return {'predicate': {'approvals': envelope.read_envelope(self.state, 'plan')['approvals']}}

    def commit(self):
        self.git('add', '-f', '.uncle/docs')
        self.git('commit', '-q', '-m', 'docs')

    def test_json_canonical_document_verifies_against_its_committed_view(self):
        self.approve('ADVERSARIAL_REVIEW', '# Review\n\nrendered view\n', canonical='{"kind": "adversarial-review"}\n')
        self.approve('CHANGE_PLAN', '# Plan\n')
        statement = self.statement(['CHANGE_PLAN', 'ADVERSARIAL_REVIEW'])
        self.commit()
        entry = [e for e in statement['predicate']['approvals'] if e['gate'] == 'ADVERSARIAL_REVIEW'][0]
        self.assertNotEqual(entry['digest'], entry['view_digest'])
        self.assertEqual(len(uv.check_3(statement, 'HEAD')), 2)

    def test_edited_view_is_still_refused(self):
        self.approve('ADVERSARIAL_REVIEW', '# Review\n', canonical='{"kind": "adversarial-review"}\n')
        statement = self.statement(['ADVERSARIAL_REVIEW'])
        (self.repo / '.uncle/docs/ADVERSARIAL_REVIEW.md').write_text('# Review\n\nedited after approval\n')
        self.commit()
        with self.assertRaises(uv.Refused) as caught:
            uv.check_3(statement, 'HEAD')
        self.assertIn('digest mismatch', caught.exception.args[0][0])

    def test_attestation_without_view_digest_falls_back_to_digest(self):
        self.approve('CHANGE_PLAN', '# Plan\n')
        statement = self.statement(['CHANGE_PLAN'])
        del statement['predicate']['approvals'][0]['view_digest']
        self.commit()
        self.assertEqual(len(uv.check_3(statement, 'HEAD')), 1)

    def test_every_failing_check_is_reported(self):
        self.approve('CHANGE_PLAN', '# Plan\n')
        statement = self.statement(['CHANGE_PLAN'])
        statement.update({'_type': uv.STATEMENT_TYPE, 'predicateType': uv.PREDICATE_TYPE, 'subject': [{'name': 'x', 'digest': {'gitTree': 'a' * 40}}]})
        statement['predicate'].update({'schema_version': uv.SCHEMA_VERSION, 'envelopes': {}, 'authentication': 'none'})
        self.commit()
        (self.repo / '.uncle/attestation.json').write_bytes(envelope.canonical(statement))
        (self.repo / '.uncle/docs/CHANGE_PLAN.md').write_text('# changed\n')
        self.git('add', '-f', '.uncle/docs')
        self.git('commit', '-q', '-m', 'edit')
        result = subprocess.run([sys.executable, str(VERIFY)], cwd=self.repo, env=self.env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('digest mismatch', result.stdout)
        self.assertIn('artifact mismatch', result.stdout)
        self.assertIn('review result is missing', result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith('NOT VERIFIED'))


if __name__ == '__main__':
    unittest.main()
