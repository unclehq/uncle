#!/usr/bin/env python3
"""The schema the server enforces on a sealed synthesis stage is the one its prompt asks for."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))


def load(name):
    spec = importlib.util.spec_from_file_location(name[:-3], LIB / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SH = load('self_hosted.py')
PROMPT = load('updated_plan_synthesis_prompt.py')


class SynthesisSchema(unittest.TestCase):
    def test_updated_plan_asks_for_patch_and_dispositions_not_narrative(self):
        schema = SH.artifact_schema('plan', True, False, synthesis=True)
        self.assertEqual(set(schema['required']), {'schema', 'kind', 'dispositions', 'patch'})
        self.assertNotIn('narrative', schema['properties'])
        self.assertNotIn('verification_commands', schema['properties'])
        self.assertNotIn('protected_verification_paths', schema['properties'])
        self.assertIs(schema['additionalProperties'], False)

    def test_updated_change_plan_asks_for_patch_and_dispositions(self):
        schema = SH.artifact_schema('change-plan', False, True, synthesis=True)
        self.assertEqual(set(schema['required']), {'schema', 'kind', 'dispositions', 'patch'})
        self.assertNotIn('narrative', schema['properties'])

    def test_a_patch_can_edit_or_insert_and_either_may_be_empty(self):
        patch = SH.artifact_schema('plan', True, False, synthesis=True)['properties']['patch']
        self.assertEqual(patch['required'], [])
        self.assertEqual(set(patch['properties']), {'edit_sections', 'replace_item', 'replace_text', 'insert_sections'})
        self.assertIn('content', patch['properties']['insert_sections']['items']['required'])

    def test_the_other_plan_stages_keep_the_full_plan_schema(self):
        self.assertIn('narrative', SH.artifact_schema('plan', True, False)['required'])
        self.assertIn('narrative', SH.artifact_schema('plan', False, False)['required'])
        self.assertIn('narrative', SH.artifact_schema('change-plan', False, True)['required'])

    def test_the_real_synthesis_prompt_carries_the_marker_the_driver_keys_on(self):
        plan = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': '## A\nx'}
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': []}
        workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
        self.assertIn(SH.SYNTHESIS_MARKER, PROMPT.prompt(plan, review, workers))
        self.assertIn(SH.SYNTHESIS_MARKER, PROMPT.prompt(dict(plan, kind='change-plan'), review, workers, change=True))

    def test_the_prompt_forbids_override_sections(self):
        plan = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': '## A\nx'}
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': []}
        workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
        for change in (False, True):
            text = PROMPT.prompt(dict(plan, kind='change-plan' if change else 'plan'), review, workers, change=change)
            self.assertIn('Never add a section that "overrides"', text)

    def test_the_prompt_and_schema_offer_snippet_replacement_first(self):
        plan = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': '## A\nx'}
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': []}
        workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
        text = PROMPT.prompt(plan, review, workers)
        self.assertIn('`replace_item` (use this first', text)
        self.assertLess(text.index('`replace_item` (use this first'), text.index('`replace_text` (use this for any other change)'))
        self.assertLess(text.index('`replace_text` (use this for any other change)'), text.index('`edit_sections` (only when most'))
        replace = SH.patch_schema('plan')['properties']['patch']['properties']['replace_text']['items']
        self.assertEqual(set(replace['required']), {'heading', 'old', 'new'})
        self.assertIn('replace_text', SH.patch_schema('plan')['properties']['patch']['properties'])

    def test_http_setup_enforces_the_patch_schema_only_for_a_synthesis_prompt(self):
        import tempfile
        root = tempfile.mkdtemp()
        synth = SH.SYNTHESIS_MARKER + ' Resolve findings.'
        for prompt, expect_narrative in ((synth, False), ('Write the plan.', True)):
            _, _, schema, _, _, _ = SH._http_setup('agent', {}, prompt, root, False, 'plan', protected=True)
            self.assertEqual('narrative' in schema['properties'], expect_narrative, prompt)


    def test_the_appended_contract_asks_for_a_patch_not_a_narrative(self):
        source = (LIB / 'self_hosted.py').read_text()
        start = source.index('synthesis = SYNTHESIS_MARKER in prompt and expected_kind')
        block = source[start:source.index('delivery_notice)', start)]
        self.assertIn('"patch":', block)
        self.assertIn('Do not write a `narrative`', block)


class CompactRequest(unittest.TestCase):
    def test_compact_json_never_asks_to_flatten_string_values(self):
        sys.path.insert(0, str(LIB))
        agent = load('http_agent.py')
        text = agent.COMPACT_JSON_REQUEST
        self.assertNotIn('single line', text)
        self.assertIn('between JSON tokens', text)
        self.assertIn('\\n escape', text)
        self.assertIn('one command per line', text)


class FieldLimits(unittest.TestCase):
    def schema(self, kind, **kw):
        return SH.artifact_schema(kind, **kw)

    def test_named_fields_get_their_own_limits_and_the_default_is_tighter(self):
        self.assertEqual(SH.DEFAULT_MAX_LENGTH, 1500)
        finding = self.schema('adversarial-review')['properties']['findings']['items']['properties']
        self.assertEqual(finding['title']['maxLength'], 400)
        self.assertEqual(finding['references']['maxLength'], 2000)
        self.assertEqual(finding['fix']['maxLength'], 1200)
        self.assertEqual(finding['id']['maxLength'], 80)

    def test_limits_clear_the_largest_values_seen_in_real_runs(self):
        # Largest real values: acceptance evidence 1798, adversarial references 1679,
        # definition_of_done 2677, 54 checklist checks, 44 acceptance rows.
        rows = self.schema('acceptance-report')['properties']['rows']
        self.assertGreaterEqual(rows['items']['properties']['evidence']['maxLength'], 1798)
        self.assertGreaterEqual(rows['maxItems'], 44)
        self.assertGreaterEqual(self.schema('manual-checklist')['properties']['checks']['maxItems'], 54)
        sections = self.schema('requirements-interpretation')['properties']['sections']['properties']
        self.assertGreaterEqual(sections['definition_of_done']['maxLength'], 2677)

    def test_every_string_and_list_is_bounded(self):
        def walk(node, path):
            if isinstance(node, dict):
                if node.get('type') == 'string':
                    self.assertIn('maxLength', node, path)
                if node.get('type') == 'array':
                    self.assertIn('maxItems', node, path)
                for key, value in node.items():
                    walk(value, path + '.' + key)
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, '%s[%d]' % (path, index))
        for kind in ('adversarial-review', 'final-audit', 'acceptance-report', 'manual-checklist', 'implementation-notes'):
            walk(self.schema(kind), kind)
        walk(self.schema('plan', protected=True, synthesis=True), 'plan')


if __name__ == '__main__':
    unittest.main()
