"""A read-only review worker whose inputs are embedded gets one schema-constrained answer; nothing else changes."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import http_agent as h
import worker_prompt as w


class SchemaFirst(unittest.TestCase):
    def test_the_marker_is_the_contract_text_the_embedder_writes(self):
        self.assertIn(h.INLINE_INPUTS_MARK, w.CONTRACT)

    def test_review_packets_with_embedded_inputs_go_schema_first(self):
        for name in sorted(h.INLINE_REVIEW_PACKETS):
            self.assertTrue(h.inline_worker_schema_first(name, 'prompt\n' + h.INLINE_INPUTS_MARK), name)

    def test_without_the_marker_the_ordinary_tool_loop_runs(self):
        for name in sorted(h.INLINE_REVIEW_PACKETS):
            self.assertFalse(h.inline_worker_schema_first(name, 'Read only `.uncle/workflow/documents/PLAN.json`.'), name)

    def test_workers_that_need_their_tools_never_qualify(self):
        for name in ('checklist_execution_worker_packet', 'preflight_worker_packet', 'project_plan_section_worker_packet',
                     'updated_plan_edit_worker_packet', 'artifact', ''):
            self.assertFalse(h.inline_worker_schema_first(name, h.INLINE_INPUTS_MARK), name)

    def test_the_option_turns_it_off(self):
        with patch.object(h.transport, 'option', side_effect=lambda key, default=None: 'off' if key == 'worker-schema-first' else default):
            self.assertFalse(h.inline_worker_schema_first('test_review_worker_packet', h.INLINE_INPUTS_MARK))

    def test_a_prompt_the_embedder_wrote_carries_the_marker_and_one_it_left_alone_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / 'PLAN.json'
            plan.write_text(json.dumps({'k': 'v'}))
            source, out = root / 'p.md', root / 'o.md'
            source.write_text('Review.\n\n## Canonical inputs (binding)\n\nRead only `%s`. Nothing else.\n\n## Assigned review lens\n\nGo.\n' % plan)
            self.assertEqual(w.main([str(source), str(out)]), 0)
            self.assertTrue(h.inline_worker_schema_first('adversarial_review_worker_packet', out.read_text()))
            source.write_text('Review.\n\n## Canonical inputs (binding)\n\nRead only `%s/missing.json`.\n\n## Assigned review lens\n\nGo.\n' % root)
            self.assertEqual(w.main([str(source), str(root / 'o2.md')]), 3)            # inputs not embedded: prompt untouched
            self.assertFalse(h.inline_worker_schema_first('adversarial_review_worker_packet', source.read_text()))


if __name__ == '__main__':
    unittest.main()
