import importlib.util
import json
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

    def test_leading_narration_before_an_unfenced_final_object_is_dropped(self):
        # Live updated-plan worker output: the model explained that the lens
        # was clean, then appended the exact requested packet unwrapped.
        text = ('The review is complete; no corrections are needed. '
                '{"schema":"uncle.artifact/v1",'
                '"kind":"updated-plan-worker-packet","findings":[]}')
        self.assertEqual(
            module.unfence_json(text),
            '{"schema":"uncle.artifact/v1","kind":"updated-plan-worker-packet","findings":[]}',
        )

    def test_single_backtick_inline_code_wrapping_is_stripped(self):
        # Observed live: the model wrapped its JSON in a single inline-code
        # backtick ("`{...}`") rather than a triple-backtick block fence.
        # The response was otherwise perfectly valid JSON and got rejected
        # anyway because unfence_json only recognized the triple-backtick
        # case.
        text = '`{"schema":"uncle.artifact/v1","kind":"adversarial-review","findings":[]}`'
        self.assertEqual(module.unfence_json(text),
                          '{"schema":"uncle.artifact/v1","kind":"adversarial-review","findings":[]}')

    def test_single_backtick_with_trailing_narration_is_stripped(self):
        text = '`{"a": 1}` is the complete review.'
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

    def test_final_answer_after_an_earlier_decoy_schema_example_wins(self):
        # Observed live, final-audit stage: the model narrated its reasoning
        # at length, quoting the schema contract itself as a reminder --
        # with placeholder/example values, self-contradictory on its own
        # ("blocks":"YES" alongside verdict "READY") -- before giving its
        # real, complete, self-consistent answer as the very last line,
        # wrapped in a single backtick. The real answer must win, not the
        # earlier in-narration example.
        decoy = ('Let me think this through.\n\n'
                 'The schema requires:\n'
                 '```json\n'
                 '{\n'
                 '  "schema": "uncle.artifact/v1",\n'
                 '  "kind": "final-audit",\n'
                 '  "findings": [{"id": "FA-1", "blocks": "YES"}],\n'
                 '  "verdict": "READY"\n'
                 '}\n'
                 '```\n\n'
                 'Now let me verify the evidence carefully...\n\n'
                 'Confirmed. Here is the final audit:\n\n')
        real_answer = ('`{"schema":"uncle.artifact/v1","kind":"final-audit","findings":'
                        '[{"id":"FA-1","severity":"Medium","evidence":"...",'
                        '"affected_requirement":"AC-4","required_correction":"...","blocks":"NO"}],'
                        '"verdict":"READY WITH NON-BLOCKING ISSUES"}`')
        text = decoy + real_answer
        result = module.unfence_json(text)
        payload = json.loads(result)
        self.assertEqual(payload['verdict'], 'READY WITH NON-BLOCKING ISSUES')
        self.assertEqual(payload['findings'][0]['blocks'], 'NO')

    def test_stray_brace_inside_otherwise_normal_prose_is_not_mistaken_for_json(self):
        # A legacy Markdown document that happens to mention a JS object
        # literal somewhere in the middle of a code example must not be
        # treated as a JSON response just because it contains a brace.
        text = '# Plan\n\nUse `{foo: 1}` as the config shape.\n\n## Verification commands\n'
        self.assertEqual(module.unfence_json(text), text.strip())


class RenderChangePlan(unittest.TestCase):
    def test_explicit_empty_dispositions_is_valid_when_review_had_no_findings(self):
        # A model that correctly reasoned "zero adversarial findings, so
        # zero dispositions" writes dispositions: [] deliberately -- that is
        # the right answer, not a missing field. `not []` is True in Python,
        # so a plain truthiness check rejected this exact correct response
        # live: a real adversarial review with no findings produced
        # `{"dispositions": []}`, and the validator called it "missing
        # dispositions for the adversarial review."
        payload = {'narrative': '# Plan\n', 'dispositions': []}
        rendered = module.render_change_plan(payload, require_dispositions=True)
        self.assertIn('# Plan', rendered)
        self.assertNotIn('Adversarial review dispositions', rendered)

    def test_omitted_dispositions_key_still_rejected(self):
        # The actual contract violation this guards against: the model
        # dropped the field entirely rather than reasoning about it.
        payload = {'narrative': '# Plan\n'}
        with self.assertRaises(ValueError):
            module.render_change_plan(payload, require_dispositions=True)

    def test_populated_dispositions_still_render_the_table(self):
        payload = {'narrative': '# Plan\n', 'dispositions': [
            {'finding': 'AR-001', 'disposition': 'Accepted', 'reason': 'fixed', 'plan_change': 'none'},
        ]}
        rendered = module.render_change_plan(payload, require_dispositions=True)
        self.assertIn('Adversarial review dispositions', rendered)
        self.assertIn('AR-001', rendered)

    def test_disposition_with_wrong_field_names_is_a_clean_validation_error(self):
        # Seen live: a model wrote disposition objects keyed "id"/"status"/
        # "rationale" instead of "finding"/"disposition"/"reason"/
        # "plan_change". The bare `row['finding']` lookup raised an
        # unhandled KeyError that crashed the whole driver process instead
        # of failing this document's validation the way every other
        # malformed-field case here does.
        payload = {'narrative': '# Plan\n', 'dispositions': [
            {'id': 'AR-001', 'status': 'Accepted', 'rationale': 'fixed'},
        ]}
        with self.assertRaises(ValueError):
            module.render_change_plan(payload, require_dispositions=True)

    def test_same_wrong_field_names_also_rejected_in_render_plan(self):
        # render_plan() (UPDATED_PROJECT_PLAN.md) shares the same
        # dispositions table logic as render_change_plan() (CHANGE_PLAN.md);
        # confirm the fix covers both instead of just the one hit live.
        payload = {
            'verification_commands': 'true',
            'dispositions': [{'id': 'AR-001', 'status': 'Accepted', 'rationale': 'fixed'}],
        }
        with self.assertRaises(ValueError):
            module.render_plan(payload, protected=False)


if __name__ == '__main__':
    unittest.main()
