import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('artifact_json', Path(__file__).resolve().parents[1]/'lib/artifact_json.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UnfenceJson(unittest.TestCase):
    def test_bare_object_is_returned_as_is(self):
        self.assertEqual(module.unfence_json('{"a": 1}'), '{"a": 1}')

    def test_wrapping_fence_is_stripped(self):
        self.assertEqual(module.unfence_json('```json\n{"a": 1}\n```'), '{"a": 1}')
        self.assertEqual(module.unfence_json('```\n{"a": 1}\n```'), '{"a": 1}')

    def test_trailing_narration_after_a_bare_object_is_dropped(self):
        # A model that wrote a valid object and then, despite being told not
        # to, described what it did as a trailing sentence -- observed live
        # on a real dogfood run. The object itself must still be recovered.
        text = '{"a": 1}\n\nThe file is written and contains the complete object.'
        self.assertEqual(module.unfence_json(text), '{"a": 1}')

    def test_trailing_narration_after_a_closing_fence_is_dropped(self):
        # Also observed live: the fence closes cleanly, but the model keeps
        # talking afterward. The old anchored regex rejected this outright.
        text = '```json\n{"a": 1}\n```\n\nAll adversarial findings are addressed above.'
        self.assertEqual(module.unfence_json(text), '{"a": 1}')

    def test_leading_narration_before_a_fence_is_dropped(self):
        text = "Here's the review:\n```json\n{\"a\": 1}\n```"
        self.assertEqual(module.unfence_json(text), '{"a": 1}')

    def test_nested_braces_and_string_values_are_handled(self):
        text = '```json\n{"a": {"b": 1}, "c": "a } b { c"}\n```\nDone.'
        self.assertEqual(module.unfence_json(text), '{"a": {"b": 1}, "c": "a } b { c"}')

    def test_non_json_markdown_is_returned_unchanged(self):
        text = '# A real Markdown document\n\nSome prose.\n'
        self.assertEqual(module.unfence_json(text), text.strip())

    def test_narration_only_with_no_json_at_all_is_unchanged(self):
        text = 'Now I have all the evidence needed. Let me construct the review.'
        self.assertEqual(module.unfence_json(text), text)

    def test_bare_filenames_with_no_json_are_unchanged(self):
        text = '.uncle/docs/REQUIREMENTS_INTERPRETATION.md\n.uncle/docs/PROJECT_PLAN.md'
        self.assertEqual(module.unfence_json(text), text)

    def test_stray_brace_inside_otherwise_normal_prose_is_not_mistaken_for_json(self):
        # A legacy Markdown document that happens to mention a JS object
        # literal somewhere in the middle of a code example must not be
        # treated as a JSON response just because it contains a brace.
        text = '# Plan\n\nUse `{foo: 1}` as the config shape.\n\n## Verification commands\n'
        self.assertEqual(module.unfence_json(text), text.strip())


if __name__ == '__main__':
    unittest.main()
