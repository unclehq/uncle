#!/usr/bin/env python3
"""scripts/lib/envelope.py: canonical bytes (AC-18, RFC 8785 §3 examples),
envelope shape and re-serialization (AC-1), key vocabulary (AC-2), the
invalidation map and directory creation (AC-16), the exclusion list (AC-19),
the blocking constant (AC-6) and the secret filter (AC-9)."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import envelope  # noqa: E402

VERIFY = ROOT / 'scripts/uncle-verify.py'


def verifier_canonical():
    """The verifier's copy of canonical(), loaded without importing envelope."""
    ns = {}
    text = VERIFY.read_text()
    block = text[text.index('def canonical(value):'):text.index('def pae(')]
    exec(compile(block, '<verify>', 'exec'), ns)
    return ns['canonical']


class CanonicalTests(unittest.TestCase):
    def test_rfc8785_sorting_and_escaping_example(self):
        # RFC 8785 §3.2.3: keys sorted by UTF-16 code units; control characters
        # escaped as \\uXXXX (lowercase), everything else literal.
        value = json.loads('{"\\u20ac": "Euro Sign", "\\r": "Carriage Return", "\\u000a": "Newline", "1": "One",'
                           ' "\\u0080": "Control\\u007f", "\\u00f6": "Latin Small Letter O With Diaeresis",'
                           ' "\\u00e9": "Latin Small Letter E With Acute", "\\ud834\\udd1e": "G clef", "\\u0000": "Nul"}')
        expected = ('{"\\u0000":"Nul","\\n":"Newline","\\r":"Carriage Return","1":"One","\u0080":"Control\u007f",'
                    '"\u00e9":"Latin Small Letter E With Acute","\u00f6":"Latin Small Letter O With Diaeresis",'
                    '"\u20ac":"Euro Sign","\U0001D11E":"G clef"}').encode('utf-8')
        self.assertEqual(envelope.canonical(value), expected)

    def test_literals_and_string_escapes(self):
        value = {'literals': [None, True, False], 'string': '\u20ac$\u000f\nA\'B"\\/', 'int': -12}
        self.assertEqual(envelope.canonical(value),
                         b'{"int":-12,"literals":[null,true,false],"string":"\xe2\x82\xac$\\u000f\\nA\'B\\"\\\\/"}')

    def test_floats_and_non_string_keys_are_refused(self):
        with self.assertRaises(ValueError):
            envelope.canonical({'x': 1.5})
        with self.assertRaises(ValueError):
            envelope.canonical({1: 'x'})

    def test_verifier_copy_is_byte_identical(self):
        other = verifier_canonical()
        samples = [
            {'z': {'b': [1, 2, {'c': None}], 'a': 'é'}, 'a': [True, False], '\u00e9': '\u0000\u001f\u007f\u2028'},
            {'n': 0, 'neg': -5, 'big': 2 ** 62, 'nested': {'k': {'k': {'k': []}}}},
            {'unicode': '日本語 𝄞', 'escape': '\\"\b\f\n\r\t', 'empty': {}, 'list': []},
        ]
        for sample in samples:
            self.assertEqual(envelope.canonical(sample), other(sample))
        # And the same function text in both files.
        block = lambda text, end: text[text.index('def _emit(value, out):'):text.index(end)]
        self.assertEqual(block(VERIFY.read_text(), 'def pae('), block((ROOT / 'scripts/lib/envelope.py').read_text(), 'def check_keys('))


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='envelope-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / '.uncle/workflow'
        (self.state / 'approvals').mkdir(parents=True)
        (self.root / 'CHANGE_SPEC.md').write_text('spec\n')
        (self.state / 'approvals/CHANGE_SPEC.sha256').write_text('a' * 64 + '\n')
        (self.state / 'approvals/CHANGE_SPEC.gate-action').write_text('APPROVE\n')
        (self.state / 'approvals/CHANGE_SPEC.approved-by').write_text('Brian\n')
        (self.state / 'approvals/CHANGE_SPEC.delegated-by').write_text('\n')

    def write(self, stage='requirements', **kw):
        return envelope.write_envelope(self.state, stage, kw.pop('result', 'pass'), root=self.root, **kw)

    def test_written_envelope_has_the_required_keys_and_round_trips(self):
        body = self.write(evidence=['CHANGE_SPEC.md'], approvals=['CHANGE_SPEC'])
        raw = (self.state / 'envelopes/requirements.json').read_bytes()
        self.assertEqual(envelope.canonical(json.loads(raw)), raw)
        self.assertEqual(envelope.read_envelope(self.state, 'requirements'), body)
        for key in ('schema_version', 'stage', 'attempt', 'producer', 'inputs', 'result', 'evidence', 'produced_at'):
            self.assertIn(key, body)
        self.assertEqual(body['schema_version'], '1')
        self.assertEqual(set(body['producer']), {'role', 'runner', 'model', 'uncle_version'})
        self.assertRegex(body['produced_at'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        self.assertEqual(body['evidence'], [{'path': 'CHANGE_SPEC.md', 'digest': {'sha256': envelope.sha256_file(self.root / 'CHANGE_SPEC.md')}}])
        self.assertEqual(body['approvals'][0]['approved_by'], 'Brian')
        self.assertEqual(body['approvals'][0]['required'], True)
        self.assertEqual(self.write()['attempt'], 2)

    def test_tampered_or_foreign_bytes_are_refused_on_read(self):
        self.write()
        path = self.state / 'envelopes/requirements.json'
        path.write_bytes(path.read_bytes().replace(b'"result":"pass"', b'"result": "pass"'))
        with self.assertRaises(envelope.EnvelopeError):
            envelope.read_envelope(self.state, 'requirements')
        path.write_bytes(envelope.canonical({'schema_version': '1', 'stage': 'review'}))
        with self.assertRaises(envelope.EnvelopeError):
            envelope.read_envelope(self.state, 'requirements')
        self.assertIsNone(envelope.read_envelope(self.state, 'plan'))

    def test_key_vocabulary_is_enforced(self):
        for bad in ({'tree': 'x'}, {'worker': 'x'}, {'reviewer': 'x'}, {'PR': 1}, {'unknown_word': 1}):
            with self.assertRaises(envelope.EnvelopeError, msg=repr(bad)):
                self.write(extra=bad)
        for stage in ('review', 'plan'):
            with self.assertRaises(envelope.EnvelopeError):
                self.write(stage, result='maybe')
        with self.assertRaises(envelope.EnvelopeError):
            self.write('nonsense')

    def test_findings_and_dispositions(self):
        review = ('## AR-001: one\n\n- **Severity**: High\n\n## AR-002 (x): two\n\nSeverity: Medium\n\n'
                  '## AR-003: three\n\nSeverity: **Blocking**\n\n## Overall assessment\nx\n')
        plan = '| Finding | Disposition | Reason | Exact plan change |\n|---|---|---|---|\n| AR-001 | Accepted | r | c |\n| AR-002 | Rejected | r | c |\n'
        self.assertEqual(envelope.findings(review), [
            {'id': 'AR-001', 'severity': 'blocking'}, {'id': 'AR-002', 'severity': 'advisory'}, {'id': 'AR-003', 'severity': 'blocking'}])
        self.assertEqual(envelope.dispositions(plan), [{'finding': 'AR-001', 'action': 'Accepted'}, {'finding': 'AR-002', 'action': 'Rejected'}])
        self.assertEqual(envelope.undispositioned(review, plan), ['AR-003'])
        self.assertEqual(envelope.undispositioned(review, plan + '| AR-003 | Deferred | r | c |\n'), [])
        self.assertEqual(envelope.undispositioned('No findings.\n', ''), [])

    def test_invalidate_map_and_directory_creation(self):
        for stage in envelope.STAGES:
            self.write(stage)
        expected = {
            'BASELINE_REPORT': set(envelope.STAGES), 'CHANGE_SPEC': set(envelope.STAGES),
            'ADVERSARIAL_REVIEW': {'plan', 'implementation', 'verification', 'audit', 'release'},
            'CHANGE_PLAN': {'plan', 'implementation', 'verification', 'audit', 'release'},
            'IMPLEMENT': {'implementation', 'verification', 'audit', 'release'},
            'FINAL_AUDIT': {'audit', 'release'},
        }
        for name, deleted in expected.items():
            for stage in envelope.STAGES:
                self.write(stage)
            envelope.invalidate(self.state, name)
            present = {p.stem for p in (self.state / 'envelopes').glob('*.json')}
            self.assertEqual(present, set(envelope.STAGES) - deleted, name)
        import shutil
        shutil.rmtree(self.state / 'envelopes')
        self.assertEqual(envelope.invalidate(self.state, 'unknown'), ())
        self.assertTrue((self.state / 'envelopes').is_dir())
        # The CLI form used by the driver.
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/lib/envelope.py'), 'invalidate', '--state', str(self.state), 'FINAL_AUDIT'],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('audit, release', result.stdout)

    def test_exclusion_list_matches_workflow_artifacts_and_verifier(self):
        text = (ROOT / 'scripts/lib/workflow-artifacts.sh').read_text()
        case = text[text.index('case "$1" in'):text.index('return 0')]
        names = set(re.findall(r'([A-Z_]+\.md)', case))
        self.assertEqual(names, {x for x in envelope.ARTIFACT_EXCLUDES if x.endswith('.md')})
        self.assertIn('.uncle/', envelope.ARTIFACT_EXCLUDES)
        block = lambda p: re.search(r'ARTIFACT_EXCLUDES = \((.*?)^\)', p.read_text(), re.S | re.M).group(1)
        self.assertEqual(block(VERIFY), block(ROOT / 'scripts/lib/envelope.py'))

    def test_blocking_constant_is_defined_once(self):
        self.assertEqual(envelope.BLOCKING, {'review': ('fail', 'unavailable'), 'verification': ('fail', 'unavailable'),
                                             'audit': ('fail', 'unavailable')})
        hits = subprocess.run(['grep', '-rl', '^BLOCKING = ', str(ROOT / 'scripts')], stdout=subprocess.PIPE, text=True).stdout.split()
        self.assertEqual(hits, [str(ROOT / 'scripts/lib/envelope.py')])
        self.assertNotIn('environ', envelope.blocking_reason.__code__.co_names)
        envelopes = {'review': {'result': 'pass'}, 'verification': {'result': 'pass'},
                     'audit': {'result': 'pass', 'inputs': {'artifact': {'digest': {'gitTree': 't'}}}},
                     'implementation': {'artifact': {'digest': {'gitTree': 't'}}}}
        envelopes['verification']['inputs'] = {'artifact': {'digest': {'gitTree': 't'}}}
        self.assertEqual(envelope.blocking_reason(envelopes, 't'), '')
        self.assertIn('review result unavailable', envelope.blocking_reason(dict(envelopes, review={'result': 'unavailable', 'reason': 'x'}), 't'))
        self.assertIn('audit result fail', envelope.blocking_reason(dict(envelopes, audit={'result': 'fail'}), 't'))
        self.assertIn('envelope missing', envelope.blocking_reason(dict(envelopes, verification=None), 't'))
        self.assertIn('artifact mismatch', envelope.blocking_reason(envelopes, 'u'))

    def test_secret_filter(self):
        value = {'a': 'token=ghp_' + 'x' * 36, 'b': ['ok', 'password: hunter22'], 'c': {'d': '/tmp/other/place', 'e': 'https://uncle.dev/attestation/v1',
                 'f': 'scripts/lib/envelope.py', 'g': 'known-value-123'}}
        out = envelope.filter_strings(value, root=self.root, known=['known-value-123'])
        self.assertEqual(out, {'a': '[redacted]', 'b': ['ok', '[redacted]'], 'c': {'d': '[redacted]', 'e': 'https://uncle.dev/attestation/v1',
                               'f': 'scripts/lib/envelope.py', 'g': '[redacted]'}})
        self.assertEqual(envelope.filter_strings({'p': str(self.root / 'inside')}, root=self.root), {'p': str(self.root / 'inside')})

    def test_approval_entry_splits_human_and_delegated(self):
        approvals = self.state / 'approvals'
        self.assertEqual(envelope.approval_entry(self.state, 'CHANGE_SPEC')['approved_by'], 'Brian')
        (approvals / 'CHANGE_SPEC.delegated-by').write_text('supervisor:standing:Brian\n')
        (approvals / 'CHANGE_SPEC.approved-by').write_text('\n')
        entry = envelope.approval_entry(self.state, 'CHANGE_SPEC')
        self.assertEqual((entry['approved_by'], entry['delegated_by']), ('', 'supervisor:standing:Brian'))
        # Legacy: the delegation lived in .approved-by itself.
        (approvals / 'CHANGE_SPEC.delegated-by').unlink()
        (approvals / 'CHANGE_SPEC.gate-action').unlink()
        (approvals / 'CHANGE_SPEC.approved-by').write_text('unattended\n')
        entry = envelope.approval_entry(self.state, 'CHANGE_SPEC')
        self.assertEqual((entry['approved_by'], entry['delegated_by'], entry['required']), ('', 'unattended', True))
        (approvals / 'FINAL_AUDIT_OVERRIDE.sha256').write_text('b' * 64 + '\n')
        self.assertFalse(envelope.approval_entry(self.state, 'FINAL_AUDIT_OVERRIDE')['required'])
        (approvals / 'X.gate-action').write_text('OVERRIDE\n')
        self.assertFalse(envelope.approval_entry(self.state, 'X')['required'])


if __name__ == '__main__':
    unittest.main(verbosity=0)
