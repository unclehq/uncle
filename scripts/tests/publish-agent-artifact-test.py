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


if __name__ == '__main__':
    unittest.main()
