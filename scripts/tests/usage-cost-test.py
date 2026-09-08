import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'lib' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

kimi, cost = load('kimi-usage'), load('usage-cost')

class UsageTests(unittest.TestCase):
    def test_rates_cache_and_reported_precedence(self):
        row = dict(model='moonshot-ai/kimi-k2.7-code-highspeed', reported_cost_usd=None,
                   input_tokens=1000000, output_tokens=1000000, cache_read_tokens=1000000, cache_write_tokens=0)
        self.assertAlmostEqual(cost.enrich(row)['estimated_cost_usd'], 10.28)
        row['input_includes_cache'] = True
        self.assertAlmostEqual(cost.enrich(row)['estimated_cost_usd'], 8.38)
        self.assertEqual(cost.enrich({'reported_cost_usd': 0})['cost_status'], 'reported')
        self.assertEqual(cost.enrich({'reported_cost_usd': 1})['reported_cost_usd'], 1)
        self.assertEqual(cost.enrich({'model': 'unknown'})['cost_status'], 'unknown')

    def test_custom_model_rates_and_missing_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'rates.json'
            p.write_text(json.dumps({'custom':dict(input=1,output=2,cache_read=.1,cache_write=1)}))
            with patch.dict(os.environ, WORKFLOW_PRICING_FILE=str(p)):
                row=dict(model='custom', input_tokens=100, output_tokens=20, cache_read_tokens=10, cache_write_tokens=0)
                self.assertAlmostEqual(cost.enrich(row)['estimated_cost_usd'], .000141)
                row.pop('input_tokens')
                row.pop('estimated_cost_usd')
                self.assertNotIn('estimated_cost_usd',cost.enrich(row))

    def test_unique_session_matching_and_summing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); cwd=root/'project';cwd.mkdir()
            session=root/'workflow/session';wire=session/'agents/main/wire.jsonl';wire.parent.mkdir(parents=True)
            (session/'state.json').write_text(json.dumps({'cwd':str(cwd)}))
            prompt=dict(type='turn.prompt', input=[dict(type='text',text='my prompt')])
            usage=dict(type='usage.record', usageScope='turn', model='moonshot-ai/kimi-k2.7-code-highspeed',
                       usage=dict(inputOther=10, output=5,inputCacheRead=100,inputCacheCreation=0))
            wire.write_text('\n'.join(map(json.dumps,[prompt,usage,usage]))+'\n{partial')
            snap={'existing':[], 'prompt_sha256':kimi.prompt_hash(prompt)}
            result=kimi.collect(root,cwd,snap)
            self.assertEqual(result['usage']['input_tokens'],20)
            self.assertEqual(result['usage']['cache_read_input_tokens'],200)
            self.assertIsNone(result['total_cost_usd'])
            snap['existing']=[str(session)]
            self.assertEqual(kimi.collect(root,cwd,snap),{})
            snap['existing']=[];snap['prompt_sha256']='wrong'
            self.assertEqual(kimi.collect(root,cwd,snap),{})
            snap['prompt_sha256']=kimi.prompt_hash(prompt)
            import shutil
            shutil.copytree(session,root/'workflow/another')
            self.assertEqual(kimi.collect(root,cwd,snap),{})

    def test_backfill_is_dry_by_default_and_idempotent(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); project=root/'project'
            metrics=project/'.uncle/workflow/metrics';metrics.mkdir(parents=True)
            row=dict(kind='agent',stage='implementation',runner='/scripts/agent-kimi.sh',started_at=1000,ended_at=1010,reported_cost_usd=0)
            metric=metrics/'attempt.json';metric.write_text(json.dumps(row))
            session=root/'sessions/workflow/session'
            wire=session/'agents/main/wire.jsonl';wire.parent.mkdir(parents=True)
            (session/'state.json').write_text(json.dumps({'cwd':str(project)}))
            records=[dict(type='turn.prompt',time=1002000,input=[]),
                     dict(type='usage.record',time=1004000,usageScope='turn',model='moonshot-ai/kimi-k2.7-code-highspeed',
                          usage=dict(inputOther=100,output=50,inputCacheRead=1000,inputCacheCreation=0))]
            wire.write_text('\n'.join(map(json.dumps,records)))
            env=dict(os.environ,WORKFLOW_KIMI_SESSIONS_DIR=str(root/'sessions'))
            command=['python3',str(ROOT/'backfill-kimi-costs.py'),str(project)]
            subprocess.run(command,env=env,check=True,capture_output=True)
            self.assertEqual(json.loads(metric.read_text()),row)
            subprocess.run(command+['--apply'],env=env,check=True,capture_output=True)
            saved=metric.read_text()
            self.assertIsNone(json.loads(saved)['reported_cost_usd'])
            self.assertGreater(json.loads(saved)['estimated_cost_usd'],0)
            self.assertTrue((metrics.parent/'cost-backfill-originals/attempt.json').exists())
            subprocess.run(command+['--apply'],env=env,check=True,capture_output=True)
            self.assertEqual(metric.read_text(),saved)

if __name__=='__main__': unittest.main()
