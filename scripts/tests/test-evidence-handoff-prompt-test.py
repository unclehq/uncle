#!/usr/bin/env python3
"""Regression coverage for prompts/test-evidence-handoff.md's schema wording.

calculator-local (self-hosted, local/deepseek-v4-flash) produced three
distinct, non-conforming shapes for these two files across three attempts:
`evidence.log_line` instead of a flat `output` string, `output: null` for a
command with genuinely no stdout (right field name, no non-empty value), and
an invented `notes` shape for IMPLEMENTATION_NOTES.json, which the prompt
never gave an example for at all. These checks pin the wording that closes
each gap so a future edit cannot silently drop it.
"""
import unittest
from pathlib import Path

PROMPT = (Path(__file__).resolve().parents[2] / 'prompts/test-evidence-handoff.md').read_text(encoding='utf-8')


class TestEvidenceHandoffPrompt(unittest.TestCase):
    def test_output_is_required_even_for_a_silent_command(self):
        self.assertIn('non-empty string on every command', PROMPT)
        self.assertIn('Never leave it `null` or omit it', PROMPT)
        # A concrete example a model can copy, not just a rule in prose.
        self.assertIn('(no stdout; command redirects its own output to /dev/null; exit 0)', PROMPT)

    def test_implementation_notes_gets_an_explicit_schema_example(self):
        self.assertIn('{"schema":"uncle.artifact/v1","kind":"implementation-notes",'
                      '"notes":[{"topic":"...","detail":"..."}]}', PROMPT)

    def test_the_notes_shape_is_one_the_renderer_actually_understands(self):
        # Keep the prompt's example and implementation_notes.py's renderer in
        # sync: an example the renderer cannot display would repeat exactly
        # this bug (real content that silently rendered as nothing).
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'implementation_notes', Path(__file__).resolve().parents[1] / 'lib/implementation_notes.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        body = module.render_fragment_body({'notes': [{'topic': 'T', 'detail': 'D'}]})
        self.assertIn('### Notes', body)
        self.assertIn('- **T**: D', body)


if __name__ == '__main__':
    unittest.main()
