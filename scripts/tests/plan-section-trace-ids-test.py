"""A plan-section worker that finds no behavior for a requirement used to send an empty `ids`, which the schema rejects whole
(issue seen on a groovy-calculator build: one empty trace row among 20 discarded a 25 KB packet and forced the single-pass plan)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import project_plan_sections as sections
import runner_schema
import worker_schemas


class TraceIds(unittest.TestCase):
    def test_empty_ids_row_is_still_rejected_and_the_error_names_the_row(self):
        schema = worker_schemas.section_model_packet(['6. Observable behaviors'], 'B')
        packet = {'schema': 'uncle.artifact/v1', 'kind': worker_schemas.SECTION_MODEL_KIND,
                  'sections': [{'heading': '6. Observable behaviors', 'blocks': [{'kind': 'paragraph', 'text': 'x'}]}],
                  'trace': [{'kind': 'B', 'requirement': 'R-1', 'ids': ['B-1']}, {'kind': 'B', 'requirement': 'R-2', 'ids': []}]}
        with self.assertRaises(ValueError) as caught:
            runner_schema.validate(packet, schema)
        self.assertIn('$.trace[1].ids', str(caught.exception))
        self.assertIn('minItems 1, got 0', str(caught.exception))

    def test_worker_prompts_tell_the_worker_to_leave_an_uncovered_requirement_out(self):
        with tempfile.TemporaryDirectory() as directory:
            base = ROOT / 'prompts' / 'project-plan-investigate.md'
            for blocks in (False, True):
                text = ' '.join(sections.build_prompt('behaviors', directory, str(base), json_mode=True, blocks=blocks).split())
                self.assertIn('leave it out', text, 'blocks=%s' % blocks)
                self.assertIn('empty `ids`', text, 'blocks=%s' % blocks)


if __name__ == '__main__':
    unittest.main()
