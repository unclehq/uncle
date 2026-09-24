import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('reviewer_output', Path(__file__).resolve().parents[1]/'lib/reviewer_output.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReviewerOutput(unittest.TestCase):
    def test_heading_or_table_row_is_a_document(self):
        self.assertTrue(module.looks_like_document('## Findings\n\nSomething.'))
        self.assertTrue(module.looks_like_document('| ID | Status |\n|---|---|\n| A | PASS |'))

    def test_prose_promise_is_not_a_document(self):
        self.assertFalse(module.looks_like_document('I will now produce the review with concrete findings.'))

    def test_bare_json_object_is_a_document(self):
        payload = json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'final-audit', 'findings': [], 'verdict': 'READY'})
        self.assertTrue(module.looks_like_document(payload))

    def test_every_parent_artifact_family_is_accepted_by_shared_runner_normalization(self):
        # Claude, Kimi, Cline, and native Codex all call check() before the
        # driver receives a reviewer response.  Parent artifacts must be
        # accepted as canonical JSON here; only a panel path gets --packet.
        for kind in ('adversarial-review', 'updated-project-plan',
                     'updated-change-plan', 'test-review', 'manual-checklist',
                     'verification-report', 'final-audit'):
            with self.subTest(kind=kind):
                payload = json.dumps({'schema': 'uncle.artifact/v1', 'kind': kind})
                self.assertEqual(json.loads(module.check(payload, 'shared-runner')), json.loads(payload))

    def test_fenced_json_object_is_a_document(self):
        payload = json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'final-audit', 'findings': [], 'verdict': 'READY'})
        self.assertTrue(module.looks_like_document('```json\n' + payload + '\n```'))
        self.assertTrue(module.looks_like_document('```\n' + payload + '\n```'))

    def test_json_without_the_schema_key_is_not_a_document(self):
        self.assertFalse(module.looks_like_document('{"reply": "done"}'))

    def test_fenced_json_with_trailing_narration_is_still_a_document(self):
        # Observed live: the model closes the fence cleanly and then keeps
        # talking ("All adversarial findings are addressed above."). The
        # anchored match this used to have rejected that outright, sending a
        # genuinely valid review to the same failure path as no document at
        # all.
        payload = json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
                               'findings': [], 'overall_assessment': 'Clean.'})
        text = '```json\n' + payload + '\n```\n\nAll adversarial findings are addressed above.'
        self.assertTrue(module.looks_like_document(text))

    def test_streamed_assistant_envelope_is_unwrapped_before_json_validation(self):
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'updated-project-plan',
                   'narrative': '## Architecture\n\nPlan.', 'verification_commands': 'pytest'}
        envelope = json.dumps({'type': 'assistant', 'message': {'content': [
            {'type': 'text', 'text': '```json\n' + json.dumps(payload) + '\n```'}]}})
        self.assertEqual(json.loads(module.check(envelope, 'stream-runner')), payload)

    def test_streamed_result_envelope_is_unwrapped_before_json_validation(self):
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'final-audit',
                   'findings': [], 'verdict': 'READY'}
        envelope = json.dumps({'type': 'result', 'result': json.dumps(payload)})
        self.assertEqual(json.loads(module.check(envelope, 'stream-runner')), payload)

    def test_unescaped_quotes_inside_worker_evidence_are_repaired_before_validation(self):
        text = ('{"schema":"uncle.artifact/v1","kind":"adversarial-review-worker-packet",'
                '"findings":[{"id":"AR-SEC-001","summary":"Quote test",'
                '"evidence":"A crafted input like "1+alert(1)" is rejected.",'
                '"risk":"XSS","required_correction":"Avoid eval"}]}')
        packet = module.worker_packet(text, 'local')
        self.assertIn('1+alert(1)', packet)

    def test_bare_object_keys_and_trailing_comma_are_repaired_before_validation(self):
        text = '{ schema: "uncle.artifact/v1", kind: "final-audit", findings: [], verdict: "READY", }'
        self.assertEqual(json.loads(module.check(text, 'local'))['verdict'], 'READY')

    def test_narrated_worker_packet_is_returned_as_canonical_json(self):
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review-worker-packet',
                  'findings': []}
        response = 'No regression findings were found. ' + json.dumps(packet)
        self.assertEqual(json.loads(module.check(response, 'codex')), packet)
        self.assertEqual(json.loads(module.worker_packet(response, 'codex')), packet)

    def test_check_raises_with_a_preview_for_a_non_document(self):
        with self.assertRaises(ValueError) as ctx:
            module.check('Sure, I will write the review next.', 'kimi')
        self.assertIn('kimi', str(ctx.exception))
        self.assertIn('I will write', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
