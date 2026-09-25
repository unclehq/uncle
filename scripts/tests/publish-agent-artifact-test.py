#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('publisher', ROOT/'scripts/lib/publish_agent_artifact.py')
publisher = importlib.util.module_from_spec(spec); spec.loader.exec_module(publisher)


class Publisher(unittest.TestCase):
    def test_every_parent_stage_publishes_json_before_markdown(self):
        cases = {
            'requirements': {'schema':'uncle.artifact/v1','kind':'requirements-interpretation','sections': {
                key:'x' for key in ('required_functionality','optional_functionality','constraints','user_visible_behaviors','system_behaviors','failure_behaviors','ambiguities','assumptions','explicit_non_goals','definition_of_done')}},
            'project-plan': {'schema':'uncle.artifact/v1','kind':'plan','narrative':'# Plan','verification_commands':'true'},
            # The initial change plan has no adversarial findings to dispose
            # of yet; requiring dispositions here would reject valid output.
            'change-plan': {'schema':'uncle.artifact/v1','kind':'change-plan','narrative':'# Change'},
            'updated-plan': {'schema':'uncle.artifact/v1','kind':'plan','narrative':'# Plan','verification_commands':'true','protected_verification_paths':'tests/'},
            'updated-change-plan': {'schema':'uncle.artifact/v1','kind':'change-plan','narrative':'# Change','dispositions':[{'finding':'AR-001','disposition':'Accepted','reason':'x','plan_change':'x'}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for stage, payload in cases.items():
                log = root/(stage + '.jsonl')
                log.write_text(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':json.dumps(payload)}]}})+'\n')
                self.assertTrue(publisher.publish(stage, log, root))
                name = publisher.ARTIFACT[stage][0]
                self.assertEqual(json.loads((root/'.uncle/workflow/documents'/name.replace('.md','.json')).read_text())['kind'], payload['kind'])
                self.assertTrue((root/'.uncle/docs'/name).is_file())

    def test_recovers_only_schema_valid_json_mistakenly_written_to_human_view(self):
        payload = {'schema':'uncle.artifact/v1','kind':'plan','narrative':'# Plan','verification_commands':'true'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            view = root/'.uncle/docs/PROJECT_PLAN.md'; view.parent.mkdir(parents=True)
            view.write_text(json.dumps(payload), encoding='utf-8')
            log = root/'project-plan.jsonl'; log.write_text('{"type":"assistant","message":{"content":[{"text":"I wrote the plan."}]}}\n')
            self.assertTrue(publisher.publish('project-plan', log, root))
            self.assertEqual(json.loads((root/'.uncle/workflow/documents/PROJECT_PLAN.json').read_text())['kind'], 'plan')
            self.assertTrue(view.read_text().startswith('# Plan'))

    def test_never_treats_rendered_markdown_as_a_canonical_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            view = root/'.uncle/docs/PROJECT_PLAN.md'; view.parent.mkdir(parents=True)
            view.write_text('# Plan\n', encoding='utf-8')
            log = root/'project-plan.jsonl'; log.write_text('{"type":"assistant","message":{"content":[{"text":"I wrote the plan."}]}}\n')
            with self.assertRaisesRegex(ValueError, 'rendered Markdown view'):
                publisher.publish('project-plan', log, root)


if __name__ == '__main__':
    unittest.main()
