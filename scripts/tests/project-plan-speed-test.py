#!/usr/bin/env python3
"""Run-16 numbering and single-pass planner regressions; no model or Git calls."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import artifact_json
import http_agent
import plan_context
import plan_model as pm
import self_hosted_http as transport
import updated_plan_ops as ops
from native_stage import Stage
from plan_patch import apply_patch


NARRATIVE = '''# Project plan

Keep the exact threshold 12.75 and requirement MC-7.

## 12. Implementation order

1. **Scaffold** — Create the manifest.
   Owns: `package.json`

2. **Core** — Implement the arithmetic.
   Owns: `src/calc.js`

1. **Tests** — Assert MC-7 at 12.75.
   Owns: `tests/calc.js`
   Depends on: 2

## 18. Notes

Keep this text, including the literal number 1 and MC-7.
'''


class Fixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / '.uncle').mkdir()
        (self.root / '.uncle/config').write_text('runner self-hosted\n')
        env = patch.dict(os.environ, {
            'UNCLE_CONFIG': str(self.root / '.uncle/config'),
            'UNCLE_PROJECT_ROOT': str(self.root),
            'PROJECT_ROOT': str(self.root),
            'UNCLE_STATUS_STAGE': 'project-plan-investigate',
            'WORKFLOW_PLAN_RECORDS': '1',
            'WORKFLOW_SELF_HOSTED_RESULT_REUSE': 'off',
        }, clear=True)
        env.start()
        self.addCleanup(env.stop)
        network = patch.object(transport, 'compatible_post', side_effect=AssertionError('no network/model'))
        network.start()
        self.addCleanup(network.stop)

    def payload(self, text=NARRATIVE):
        return dict(schema='uncle.artifact/v1', kind='plan', narrative=text,
                    verification_commands='python3 -m unittest',
                    protected_verification_paths='tests/calc.js')


class Numbering(Fixture):
    def test_run16_duplicate_is_repaired_without_changing_any_other_model_field(self):
        original = pm.import_markdown(NARRATIVE)
        self.assertTrue(any('number 1 is used twice' in e for e in pm.validate(original)[0]))
        expected = copy.deepcopy(original)
        pm.steps_of(expected)[2]['number'] = 3
        payload = self.payload()
        saved = copy.deepcopy(payload)
        result = pm.publish_records(payload, self.root)
        self.assertEqual(pm.model_of(result), pm.with_protected(expected, payload))
        self.assertEqual(payload, saved)
        self.assertEqual(pm.validate(pm.model_of(result), self.root)[0], [])
        self.assertEqual(result['narrative'], NARRATIVE.replace('1. **Tests**', '3. **Tests**'))
        self.assertEqual(result['verification_commands'], payload['verification_commands'])
        self.assertEqual(result['protected_verification_paths'], payload['protected_verification_paths'])

    def test_out_of_sequence_references_follow_original_step_identity(self):
        model = pm.import_markdown(NARRATIVE)
        steps = pm.steps_of(model)
        for step, number, deps in zip(steps, (9, 4, 20), ([], [9], [9, 4])):
            step.update(number=number, depends_on=deps)
        expected = copy.deepcopy(model)
        for step, number, deps in zip(pm.steps_of(expected), (1, 2, 3), ([], [1], [1, 2])):
            step.update(number=number, depends_on=deps)
        result = pm.publish_records(self.payload(pm.render(model)), self.root, model=model)
        self.assertEqual(pm.model_of(result), pm.with_protected(expected, self.payload()))
        self.assertEqual(result['narrative'], pm.render(expected))

    def test_ambiguous_duplicate_reference_falls_back_without_partial_changes(self):
        model = pm.import_markdown(NARRATIVE)
        pm.steps_of(model)[1]['depends_on'] = [1]
        before = copy.deepcopy(model)
        with self.assertRaisesRegex(pm.PlanError, 'used twice'):
            pm.publish_records(self.payload(), self.root, model=model)
        self.assertEqual(model, before)

    def test_sections_only_plan_repairs_without_adding_a_narrative(self):
        payload = self.payload()
        del payload['narrative']
        payload.update(pm.import_markdown(NARRATIVE))
        result = pm.publish_records(payload, self.root)
        self.assertEqual([s['number'] for s in pm.steps_of(result)], [1, 2, 3])
        self.assertNotIn('narrative', result)

    def test_other_validation_errors_are_not_hidden_by_number_repair(self):
        for defect in ('missing dependency', 'bad owner', 'cycle'):
            with self.subTest(defect=defect):
                model = pm.import_markdown(NARRATIVE)
                steps = pm.steps_of(model)
                if defect == 'missing dependency':
                    steps[2]['depends_on'] = [99]
                elif defect == 'bad owner':
                    steps[2]['owns'] = ['../escape.js']
                else:
                    steps[0]['number'] = 3
                    steps[0]['depends_on'] = [2]
                    steps[1]['depends_on'] = [3]
                before = copy.deepcopy(model)
                with self.assertRaises(pm.PlanError):
                    pm.publish_records(self.payload(), self.root, model=model)
                self.assertEqual(model, before)

    def test_already_sequential_documents_are_byte_identical(self):
        text = NARRATIVE.replace('1. **Tests**', '3. **Tests**')
        payload = self.payload(text)
        rendered = artifact_json.render_plan(payload)
        result = pm.publish_records(payload, self.root)
        self.assertEqual(result['narrative'], text)
        self.assertEqual(artifact_json.render_plan(result), rendered)

    def test_claude_codex_large_and_opt_out_keep_existing_validation(self):
        config = self.root / '.uncle/config'
        for runner, environment in (
                ('claude', {}), ('codex', {}),
                ('self-hosted', {'WORKFLOW_SELF_HOSTED_GRANULARITY': 'large'}),
                ('self-hosted', {'WORKFLOW_SELF_HOSTED_PLAN_RENUMBER': 'off'})):
            with self.subTest(runner=runner, environment=environment), patch.dict(os.environ, environment):
                config.write_text('runner ' + runner + '\n')
                with self.assertRaisesRegex(pm.PlanError, 'used twice'):
                    pm.publish_records(self.payload(), self.root)
                valid = self.payload(NARRATIVE.replace('1. **Tests**', '5. **Tests**'))
                result = pm.publish_records(valid, self.root)
                self.assertEqual(result['narrative'], valid['narrative'])
                self.assertEqual([s['number'] for s in pm.steps_of(result)], [1, 2, 5])

    def test_number_repair_config_uses_stage_alias_and_env_precedence(self):
        config = self.root / '.uncle/config'
        config.write_text('runner self-hosted\nproject-plan.plan-renumber off\n')
        with self.assertRaisesRegex(pm.PlanError, 'used twice'):
            pm.publish_records(self.payload(), self.root)
        with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_PLAN_RENUMBER_PROJECT_PLAN='on'):
            result = pm.publish_records(self.payload(), self.root)
        self.assertEqual([s['number'] for s in pm.steps_of(result)], [1, 2, 3])

    def test_existing_duplicate_does_not_reject_unrelated_edit_ops(self):
        model = pm.import_markdown(NARRATIVE)
        note = model['sections'][-1]['blocks'][0]
        result = pm.apply_ops(model, [{'op': 'set_text', 'id': note['id'], 'text': 'Keep MC-7.'}], root=self.root)
        self.assertEqual(pm.locate(result, note['id'])[0]['text'], 'Keep MC-7.')
        self.assertEqual([s['number'] for s in pm.steps_of(result)], [1, 2, 1])
        good = pm.import_markdown(NARRATIVE.replace('1. **Tests**', '3. **Tests**'))
        with self.assertRaises(pm.PlanError):
            pm.apply_ops(good, [{'op': 'set_step', 'id': pm.steps_of(good)[2]['id'], 'depends_on': [99]}], root=self.root)

    def test_every_plan_export_publishes_matching_json_and_rendered_view(self):
        for name, exporter, protected, change in (
                ('PROJECT_PLAN', plan_context.export_project_plan, False, False),
                ('UPDATED_PROJECT_PLAN', plan_context.export_updated_project_plan, True, False),
                ('CHANGE_PLAN', plan_context.export_change_plan, False, True),
                ('UPDATED_CHANGE_PLAN', plan_context.export_change_plan, False, True)):
            with self.subTest(name=name):
                path = self.root / (name + '.md')
                text = NARRATIVE if change else artifact_json.render_plan(self.payload(), protected=protected)
                path.write_text(text)
                exporter(path, self.root)
                saved = artifact_json.read(self.root, path.name)
                self.assertEqual([s['number'] for s in pm.steps_of(pm.model_of(saved))], [1, 2, 3])
                self.assertEqual(pm.steps_of(pm.model_of(saved))[2]['depends_on'], [2])
                plan_context.render_canonical(path, self.root, protected=protected, change=change)
                self.assertIn('3. **Tests**', path.read_text())
                self.assertNotIn('1. **Tests**', path.read_text())
                self.assertIn('Keep this text, including the literal number 1 and MC-7.', path.read_text())

    def test_updated_ops_uses_updated_runner_and_keeps_original_ids_for_edits(self):
        (self.root / '.uncle/config').write_text('runner claude\nupdated-plan.runner self-hosted\n')
        plan = self.root / 'PROJECT_PLAN.json'
        plan.write_text(json.dumps(self.payload()))
        slices = self.root / 'slices.tsv'
        slices.write_text('1\tAR-1\n')
        packet = {'dispositions': [{'finding': 'AR-1', 'disposition': 'Accepted',
                                    'reason': 'Clarify title.', 'plan_change': 'Rename test step.'}],
                  'ops': [{'op': 'set_step', 'id': pm.steps_of(pm.import_markdown(NARRATIVE))[2]['id'],
                           'fields': {'title': 'Boundary tests'}}]}
        (self.root / '1.json').write_text(json.dumps(packet))
        output = self.root / 'merged.json'
        with patch.dict(os.environ), patch('os.getcwd', return_value=str(self.root)):
            os.environ.pop('UNCLE_STATUS_STAGE', None)
            ops.merge(plan, slices, self.root, output)
        result = json.loads(output.read_text())
        revised = pm.import_markdown(apply_patch(NARRATIVE, result['patch']))
        self.assertEqual([s['number'] for s in pm.steps_of(revised)], [1, 2, 3])
        self.assertEqual(pm.steps_of(revised)[2]['title'], 'Boundary tests')
        self.assertEqual(pm.steps_of(revised)[2]['depends_on'], [2])


class PlannerPrefetch(Fixture):
    def setUp(self):
        super().setUp()
        self.requirements = '.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json'
        path = self.root / self.requirements
        path.parent.mkdir(parents=True)
        path.write_text('{"requirement":"KEEP_EXACT_THRESHOLD_12_75"}')
        (self.root / '.gitignore').write_text('# KEEP_EXISTING_IGNORE\ncustom-output/\n')
        self.prompt = (ROOT / 'prompts/project-plan-investigate.md').read_text()
        self.policy = http_agent.Policy(self.root, write=True, shell=True)

    def test_single_pass_receives_requirements_and_existing_ignore_before_first_turn(self):
        content = http_agent.prefetch_context(self.prompt, self.policy)
        self.assertIn('KEEP_EXACT_THRESHOLD_12_75', content)
        self.assertIn('KEEP_EXISTING_IGNORE', content)
        self.assertEqual(content.count('KEEP_EXISTING_IGNORE'), 1)

    def test_prefetch_is_disabled_by_config_and_environment_has_precedence(self):
        config = self.root / '.uncle/config'
        config.write_text('self-hosted.prefetch off\n')
        self.assertEqual(http_agent.prefetch_context(self.prompt, self.policy), '')
        with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_PREFETCH='on'):
            self.assertIn('KEEP_EXISTING_IGNORE', http_agent.prefetch_context(self.prompt, self.policy))

    def test_large_granularity_and_other_stages_keep_existing_context(self):
        for environment in ({'WORKFLOW_SELF_HOSTED_GRANULARITY': 'large'},
                            {'UNCLE_STATUS_STAGE': 'project-plan-section-outline'},
                            {'UNCLE_STATUS_STAGE': 'implementation-step-1'}):
            with self.subTest(environment=environment), patch.dict(os.environ, environment):
                content = http_agent.prefetch_context(self.prompt, self.policy)
                self.assertNotIn('KEEP_EXISTING_IGNORE', content)

    def test_native_claude_and_codex_prompts_do_not_get_http_prefetch(self):
        for runner in ('claude', 'codex'):
            with self.subTest(runner=runner), patch('os.getcwd', return_value=str(self.root)):
                stage = Stage(runner, 'agent', 'project-plan-investigate', [], prompt=self.prompt)
                self.assertIn(self.prompt, stage.prompt)
                self.assertNotIn('KEEP_EXISTING_IGNORE', stage.prompt)
                self.assertNotIn('KEEP_EXACT_THRESHOLD_12_75', stage.prompt)

    def test_planner_prefetch_stage_option_obeys_parent_and_environment(self):
        config = self.root / '.uncle/config'
        config.write_text('runner self-hosted\nproject-plan.project-plan-prefetch off\n')
        self.assertNotIn('KEEP_EXISTING_IGNORE', http_agent.prefetch_context(self.prompt, self.policy))
        with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_PROJECT_PLAN_PREFETCH_PROJECT_PLAN='on'):
            self.assertIn('KEEP_EXISTING_IGNORE', http_agent.prefetch_context(self.prompt, self.policy))

    def test_prefetch_never_reads_prototype_secrets_or_symlinked_ignore(self):
        (self.root / 'index.html').write_text('PROTOTYPE_MUST_NOT_BECOME_REQUIREMENTS')
        (self.root / '.env').write_text('SECRET_MUST_NOT_BE_READ')
        content = http_agent.prefetch_context(self.prompt, self.policy)
        self.assertNotIn('PROTOTYPE_MUST_NOT_BECOME_REQUIREMENTS', content)
        self.assertNotIn('SECRET_MUST_NOT_BE_READ', content)
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / 'ignore'
            target.write_text('EXTERNAL_IGNORE_MUST_NOT_BE_READ')
            (self.root / '.gitignore').unlink()
            (self.root / '.gitignore').symlink_to(target)
            self.assertNotIn('EXTERNAL_IGNORE_MUST_NOT_BE_READ', http_agent.prefetch_context(self.prompt, self.policy))

    def test_stub_needs_at_most_three_turns_and_writes_identical_documents(self):
        def run(enabled):
            calls = []

            def reply(values, tools, messages, *args, **kwargs):
                calls.append(copy.deepcopy(messages))
                context = json.dumps(messages)
                for marker, path in (('KEEP_EXACT_THRESHOLD_12_75', self.requirements),
                                     ('KEEP_EXISTING_IGNORE', '.gitignore')):
                    if marker not in context:
                        call = {'id': 'read-' + str(len(calls)), 'type': 'function',
                                'function': {'name': 'read_file', 'arguments': json.dumps({'path': path})}}
                        return {'choices': [{'message': {'content': '', 'tool_calls': [call]}, 'finish_reason': 'tool_calls'}]}
                if not any(m.get('role') == 'tool' and 'write-plan' == m.get('tool_call_id') for m in messages):
                    call = {'id': 'write-plan', 'type': 'function', 'function': {'name': 'write_file',
                            'arguments': json.dumps({'path': '.uncle/workflow/project-plan-investigation.md', 'content': NARRATIVE})}}
                    return {'choices': [{'message': {'content': '', 'tool_calls': [call]}, 'finish_reason': 'tool_calls'}]}
                return {'choices': [{'message': {'content': 'Complete.'}, 'finish_reason': 'stop'}]}

            with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_PREFETCH=enabled), \
                    patch.object(http_agent, 'interruptible_chat', side_effect=reply), \
                    patch.object(http_agent, 'constrained_completion', side_effect=AssertionError('no final schema on Markdown delivery')), \
                    contextlib.redirect_stdout(io.StringIO()):
                answer, requests = http_agent.run_agent({}, self.prompt, self.policy, 32768, turns=8)
            self.assertEqual(answer, 'Complete.')
            self.assertEqual(requests, len(calls))
            return requests, (self.root / '.uncle/workflow/project-plan-investigation.md').read_bytes()

        slow, before = run('off')
        fast, after = run('on')
        self.assertEqual((slow, fast), (4, 2))
        self.assertEqual(before, after)
        self.assertEqual((self.root / '.gitignore').read_text(), '# KEEP_EXISTING_IGNORE\ncustom-output/\n')


if __name__ == '__main__':
    unittest.main()
