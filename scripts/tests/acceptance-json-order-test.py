#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class AcceptanceJsonOrder(unittest.TestCase):
    def test_json_with_heading_like_narrative_renders_one_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'TEST_REVIEW.md'
            path.write_text(json.dumps({'schema':'uncle.artifact/v1','kind':'acceptance-report',
                'narrative':'Summary only; never a gate.',
                'rows':[{'id':'RESULTS','required':True,'status':'PASS','evidence':'driver'}]}))
            subprocess.run(['python3', str(ROOT/'scripts/lib/acceptance_context.py'), str(path), temp], check=True)
            self.assertEqual(path.read_text().count('## Acceptance gate'), 1)

    def test_embedded_gate_in_json_narrative_is_not_rendered_twice(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'TEST_REVIEW.md'
            path.write_text(json.dumps({'schema':'uncle.artifact/v1','kind':'acceptance-report',
                'narrative':'## Summary\ntext\n\n## Acceptance gate\n\n| stale | table |',
                'rows':[{'id':'RESULTS','required':True,'status':'PASS','evidence':'driver'}]}))
            subprocess.run(['python3', str(ROOT/'scripts/lib/acceptance_context.py'), str(path), temp], check=True)
            rendered = path.read_text()
            self.assertEqual(rendered.count('## Acceptance gate'), 1)
            self.assertNotIn('stale | table', rendered)

    def test_transition_ingests_json_before_markdown_repair(self):
        source = (ROOT/'scripts/stagegate.sh').read_text()
        block = source[source.index('acceptance_transition() {'):source.index('\n}', source.index('acceptance_transition() {'))]
        self.assertLess(block.index('acceptance_context.py'), block.index('repair_document_format.py'))

if __name__ == '__main__': unittest.main()
