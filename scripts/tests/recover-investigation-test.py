#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('recover_investigation', ROOT/'scripts/lib/recover_investigation.py')
RECOVER = importlib.util.module_from_spec(spec); spec.loader.exec_module(RECOVER)


class Recovery(unittest.TestCase):
    def test_recovers_final_fenced_document_not_status_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); log = root/'events.jsonl'; target = root/'investigation.md'
            events = [
                {'type':'assistant', 'message':{'content':[{'text':'I will write the document.'}]}},
                {'type':'result', 'result':'```markdown\n# Requirements investigation\n\n## Required functionality\n\nCalculator.\n```'}]
            log.write_text('\n'.join(json.dumps(event) for event in events) + '\n')
            RECOVER.recover(log, target, '## Required functionality')
            self.assertEqual(target.read_text(), '# Requirements investigation\n\n## Required functionality\n\nCalculator.\n')

    def test_refuses_unfenced_or_incomplete_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); log = root/'events.jsonl'; target = root/'investigation.md'
            log.write_text(json.dumps({'type':'result', 'result':'I wrote the document.'}) + '\n')
            with self.assertRaisesRegex(ValueError, 'no complete fenced Markdown'):
                RECOVER.recover(log, target, '## Required functionality')
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
