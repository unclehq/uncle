#!/usr/bin/env python3
"""The preview page in one tool-free call: the prompt carries everything, the reply is the page."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import preview_oneshot as shot

PAGE = '<!doctype html>\n<html><head><title>T</title></head><body>' + '<p>x</p>' * 40 + '</body></html>'


def log(text, assistant=None):
    lines = []
    if assistant is not None:
        lines.append(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': assistant}]}}))
    lines.append(json.dumps({'type': 'result', 'result': text, 'usage': {}}))
    path = Path(tempfile.mkdtemp()) / 'stream.jsonl'
    path.write_text('\n'.join(lines) + '\n')
    return path


class Prompt(unittest.TestCase):
    def project(self, **files):
        root = Path(tempfile.mkdtemp())
        for name, text in files.items():
            path = root / name.replace('__', '/')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return root

    def test_the_inputs_are_embedded_so_the_model_reads_nothing(self):
        root = self.project(**{'REQUIREMENTS.md': 'a groovy calculator',
                               '.uncle__workflow__documents__REQUIREMENTS_INTERPRETATION.json': '{"palette":"#cc5500"}',
                               '.uncle__workflow__documents__PROJECT_PLAN.json': '{"narrative":"plan text"}'})
        prompt = shot.build_prompt(root)
        for expected in ('a groovy calculator', '#cc5500', 'plan text', 'Do not call any tool',
                         'starting with `<!doctype html>`', '.uncle/vendor/react.production.min.js'):
            self.assertIn(expected, prompt)

    def test_missing_inputs_are_skipped_not_invented(self):
        prompt = shot.build_prompt(self.project(**{'REQUIREMENTS.md': 'brief only'}))
        self.assertIn('brief only', prompt)
        self.assertNotIn('## Plan', prompt)
        self.assertNotIn('## Requirements interpretation', prompt)

    def test_a_long_input_is_clipped(self):
        prompt = shot.build_prompt(self.project(**{'REQUIREMENTS.md': 'x' * 50000}))
        self.assertLess(len(prompt), shot.LIMIT + 5000)
        self.assertIn('(truncated)', prompt)


class Extract(unittest.TestCase):
    def run_extract(self, stream):
        out = Path(tempfile.mkdtemp()) / 'staged' / 'index.html'
        code = shot.extract(stream, out)
        return code, out

    def test_a_bare_document_is_staged(self):
        code, out = self.run_extract(log(PAGE))
        self.assertEqual(code, 0)
        self.assertTrue(out.read_text().startswith('<!doctype html>'))

    def test_a_fence_or_a_sentence_around_it_is_stripped(self):
        for reply in ('```html\n%s\n```' % PAGE, 'Here is the page:\n\n%s\n\nHope it helps.' % PAGE):
            code, out = self.run_extract(log(reply))
            self.assertEqual(code, 0, reply[:30])
            text = out.read_text()
            self.assertTrue(text.startswith('<!doctype html>'))
            self.assertTrue(text.rstrip().endswith('</html>'))
            self.assertNotIn('```', text)
            self.assertNotIn('Hope it helps', text)

    def test_the_assistant_text_is_used_when_the_result_is_empty(self):
        code, out = self.run_extract(log('', assistant=PAGE))
        self.assertEqual(code, 0)

    def test_replies_without_a_usable_page_are_refused(self):
        for reply in ('', 'I cannot do that.', '<html><body>tiny</body></html>', '<!doctype html><html><body>' + 'x' * 400,
                      '<p>just a fragment ' + 'x' * 400 + '</p>'):
            code, out = self.run_extract(log(reply))
            self.assertEqual(code, 1, reply[:30])
            self.assertFalse(out.exists())

    def test_a_missing_or_garbled_log_is_refused(self):
        self.assertEqual(shot.extract('/nonexistent/log.jsonl', Path(tempfile.mkdtemp()) / 'o.html'), 1)
        garbled = Path(tempfile.mkdtemp()) / 'g.jsonl'
        garbled.write_text('not json\n{"type":\n')
        self.assertEqual(shot.extract(garbled, Path(tempfile.mkdtemp()) / 'o.html'), 1)

    def test_the_nothing_staged_on_failure_leaves_an_earlier_page_alone(self):
        out = Path(tempfile.mkdtemp()) / 'index.html'
        out.write_text('earlier')
        self.assertEqual(shot.extract(log('no page'), out), 1)
        self.assertEqual(out.read_text(), 'earlier')


if __name__ == '__main__':
    unittest.main()
