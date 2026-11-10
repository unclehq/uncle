"""Review-worker packets are rejected whole for one overlong field, so the prompt must state the caps and the error must name them."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import runner_schema
import self_hosted


def caps(kind):
    item = self_hosted.REVIEWER_SCHEMAS[kind]['properties']['findings']['items']['properties']
    return item['summary']['maxLength'], item['evidence']['maxLength']


class LengthCaps(unittest.TestCase):
    def test_overlong_string_error_names_the_bound_and_the_size(self):
        with self.assertRaises(ValueError) as caught:
            runner_schema.validate('x' * 417, {'type': 'string', 'minLength': 1, 'maxLength': 400})
        self.assertIn('maxLength 400', str(caught.exception))
        self.assertIn('got 417', str(caught.exception))

    def test_too_many_items_error_names_the_bound(self):
        with self.assertRaises(ValueError) as caught:
            runner_schema.validate([1] * 9, {'type': 'array', 'maxItems': 8, 'items': {'type': 'integer'}})
        self.assertIn('maxItems 8', str(caught.exception))

    def test_in_bounds_values_still_pass(self):
        runner_schema.validate('x' * 400, {'type': 'string', 'minLength': 1, 'maxLength': 400})

    def test_worker_prompts_state_the_schema_caps(self):
        for prompt, kind in (('adversarial-review-worker.md', 'adversarial-review-worker-packet'),
                             ('final-audit-review-worker.md', 'final-audit-worker-packet')):
            text = ' '.join((ROOT / 'prompts/change' / prompt).read_text().split())
            summary, evidence = caps(kind)
            self.assertIn('at most %d characters' % summary, text, prompt)
            self.assertIn('at most %d characters' % evidence, text, prompt)


if __name__ == '__main__':
    unittest.main()
