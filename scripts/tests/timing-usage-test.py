import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from timing_usage import priced, combine, attribute
from runner_timing import RunnerTiming
from build_timing import BuildTiming


class UsageTests(unittest.TestCase):
    def test_cache_is_counted_once_and_custom_rates_are_used(self):
        with tempfile.TemporaryDirectory() as directory:
            prices=Path(directory)/'rates.json'
            prices.write_text(json.dumps({'model':dict(input=2,output=8,cache_read=1,cache_write=2)}))
            with patch.dict(os.environ, WORKFLOW_PRICING_FILE=str(prices.resolve())):
                row=priced(dict(model='model',input_tokens=100,output_tokens=20,cache_read_tokens=40,
                                cache_write_tokens=0,input_includes_cache=True,reported_cost_usd=.001))
                self.assertEqual(row['total_tokens'],120)
                self.assertAlmostEqual(row['estimated_cost_usd'],.00032)
                self.assertEqual(row['reported_cost_usd'],.001)
                self.assertEqual(row['pricing_source'],str(prices.resolve()))
                other=priced(dict(row,total_tokens=None,input_includes_cache=False,estimated_cost_usd=None))
                self.assertEqual(other['total_tokens'],160)
                self.assertEqual(combine([row,other])['total_tokens'],280)

    def test_partial_usage_and_unknown_model_are_not_zero(self):
        row=priced(dict(model='unknown',input_tokens=100,output_tokens=20,input_includes_cache=True))
        self.assertEqual(row['total_tokens'],120)
        self.assertIsNone(row['cache_read_tokens'])
        self.assertIsNone(row['estimated_cost_usd'])
        total=combine([row,{}])
        self.assertEqual(total['total_tokens'],120)
        self.assertEqual(total['total_tokens_coverage'],'1/2')
        self.assertIsNone(total['reported_cost_usd'])

    def test_cumulative_updates_are_deduplicated_and_differenced(self):
        with patch.dict(os.environ,UNCLE_TIMING_DIR='/unused'), patch('runner_timing.event') as emit:
            observer=RunnerTiming('execute-checklist')
            observer.usage(dict(input_tokens=100,output_tokens=20,cache_read_input_tokens=40,cache_creation_input_tokens=0),.01,True,'model')
            observer.usage(dict(input_tokens=100,output_tokens=20,cache_read_input_tokens=40,cache_creation_input_tokens=0),.01,True,'model')
            observer.usage(dict(input_tokens=150,output_tokens=30,cache_read_input_tokens=60,cache_creation_input_tokens=0),.02,True,'model')
            self.assertEqual(emit.call_count,2)
            row=emit.call_args.kwargs
            self.assertEqual(row['input_tokens'],50)
            self.assertEqual(row['cache_read_tokens'],20)
            self.assertEqual(row['total_tokens'],60)
            self.assertAlmostEqual(row['reported_cost_usd'],.01)

    def test_shared_intervals_are_labeled_and_processes_not_charged(self):
        common=dict(started_at=10,elapsed_seconds=10,workflow_state='execute-checklist')
        sample=dict(common,kind='model_usage',name='model',observed_at=15,input_tokens=10,output_tokens=2,
                    cache_read_tokens=0,cache_write_tokens=0,input_includes_cache=True,attempt_id='a')
        spans=attribute([sample,dict(common,kind='checklist_item',name='MC-1'),
                         dict(common,kind='tool_call',name='Bash',attempt_id='a'),
                         dict(common,kind='process',name='bash'),
                         dict(common,kind='runner_observation',name='another',attempt_id='b')])
        self.assertEqual(spans[1]['total_tokens'],12)
        self.assertIn('shared',spans[1]['usage_scope'])
        self.assertEqual(spans[2]['total_tokens'],12)
        self.assertIsNone(spans[3]['total_tokens'])
        self.assertIsNone(spans[4]['total_tokens'])

    def test_parts_and_report_persist_usage(self):
        with tempfile.TemporaryDirectory() as directory, patch('build_timing.snapshot',return_value=[]):
            with BuildTiming(Path(directory)) as build:
                observer=RunnerTiming('execute-checklist')
                observer.usage(dict(input_tokens=100,output_tokens=20,cache_read_input_tokens=30,cache_creation_input_tokens=0),.01,True,'unknown')
                observer.finish()
            rows=json.loads((build.directory/'parts.json').read_text())
            usage=next(r for r in rows if r['kind']=='model_usage')
            self.assertEqual(usage['total_tokens'],120)
            self.assertEqual(usage['reported_cost_usd'],.01)
            report=(build.directory/'report.md').read_text()
            self.assertIn('Estimated USD',report)
            self.assertIn('Token coverage',report)
            self.assertIn('0.010000',report)
            self.assertIn('## Model API Continuation',report)
            self.assertIn('not independent user turns',report)

if __name__=='__main__': unittest.main()
