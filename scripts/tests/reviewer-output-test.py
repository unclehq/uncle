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

    def test_check_raises_with_a_preview_for_a_non_document(self):
        with self.assertRaises(ValueError) as ctx:
            module.check('Sure, I will write the review next.', 'kimi')
        self.assertIn('kimi', str(ctx.exception))
        self.assertIn('I will write', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
