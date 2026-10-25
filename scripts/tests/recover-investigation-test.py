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
            with self.assertRaisesRegex(ValueError, 'no complete Markdown'):
                RECOVER.recover(log, target, '## Required functionality')
            self.assertFalse(target.exists())

    def test_recovers_a_final_answer_that_is_the_document_unfenced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); log = root/'events.jsonl'; target = root/'investigation.md'
            document = '# Requirements Investigation\n\n## Required functionality\n\nCalculator with a 1970s theme.\n'
            events = [{'type':'assistant', 'message':{'content':[{'text':document}]}},
                      {'type':'result', 'result':document}]
            log.write_text('\n'.join(json.dumps(event) for event in events) + '\n')
            RECOVER.recover(log, target, '## Required functionality')
            self.assertEqual(target.read_text(), document)

    def test_unfenced_text_that_does_not_open_with_a_heading_is_still_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); log = root/'events.jsonl'; target = root/'investigation.md'
            chatty = 'Here is the investigation:\n\n## Required functionality\n\nCalculator.\n'
            log.write_text(json.dumps({'type':'result', 'result':chatty}) + '\n')
            with self.assertRaisesRegex(ValueError, 'no complete Markdown'):
                RECOVER.recover(log, target, '## Required functionality')
            self.assertFalse(target.exists())

    def test_an_unfenced_assistant_message_alone_is_not_the_final_answer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); log = root/'events.jsonl'; target = root/'investigation.md'
            log.write_text(json.dumps({'type':'assistant', 'message':{'content':[{'text':'# Draft\n\n## Required functionality\n'}]}}) + '\n')
            with self.assertRaisesRegex(ValueError, 'no complete Markdown'):
                RECOVER.recover(log, target, '## Required functionality')


if __name__ == '__main__':
    unittest.main()
