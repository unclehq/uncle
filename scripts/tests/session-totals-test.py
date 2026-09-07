#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('session_totals', Path(__file__).resolve().parents[1] / 'lib/session-totals.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Sessions(unittest.TestCase):
    def test_resume_reset_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / '.uncle/workspace'
            metrics = workspace / 'metrics'
            metrics.mkdir(parents=True)
            source = root / 'REQUIREMENTS.md'
            source.write_text('First project')
            first = module.update(workspace, source, '#')
            row = dict(kind='agent', stage='implementation', elapsed_seconds=10,
                       input_tokens=100, output_tokens=50, reported_cost_usd=.1)
            (metrics / 'one.json').write_text(json.dumps(row))
            module.update(workspace)
            resumed = module.update(workspace, source, '#')
            self.assertEqual(first['id'], resumed['id'])
            self.assertEqual(resumed['records'], [row])
            self.assertEqual(module.update(workspace)['records'], [row])
            source.write_text('New project')
            fresh = module.update(workspace, source, '#')
            self.assertNotEqual(first['id'], fresh['id'])
            self.assertEqual(fresh['records'], [])
            self.assertTrue((metrics / 'one.json').exists())
            change = root / 'CHANGE_REQUEST.md'
            change.write_text('Change project')
            changed = module.update(workspace, change, '#')
            self.assertNotEqual(changed['id'], fresh['id'])
            issue = module.update(workspace, change, 'owner/repo#1')
            self.assertNotEqual(issue['id'], changed['id'])
            self.assertEqual(module.update(workspace, change, 'owner/repo#1')['id'], issue['id'])
            self.assertNotEqual(module.update(workspace, change, 'owner/repo#2')['id'], issue['id'])

    def test_existing_history_and_partial_files(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            metrics = workspace / 'metrics'
            metrics.mkdir()
            (metrics / 'bad.json').write_text('{')
            (metrics / 'good.json').write_text('{"kind":"reviewer","stage":"review"}')
            saved = module.update(workspace)
            self.assertEqual(len(saved['records']), 1)
            (metrics / 'bad.json').write_text('{"kind":"agent","stage":"build"}')
            self.assertEqual(len(module.update(workspace)['records']), 2)

if __name__ == '__main__':
    unittest.main()
