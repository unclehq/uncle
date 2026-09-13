import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import runner_timing as timing
from build_timing import BuildTiming


class RunnerTimingTests(unittest.TestCase):
    def test_context_is_per_request_not_cumulative_usage(self):
        with patch.dict(os.environ, UNCLE_TIMING_DIR='/unused'), patch.object(timing, 'event') as emit:
            timer = timing.RunnerTiming('implementation')
            timer.observe({'method':'thread/tokenUsage/updated', 'params':{'tokenUsage':{
                'total':{'inputTokens':900000}, 'last':{'inputTokens':12000}}}})
            timer.observe({'type':'assistant', 'message':{'usage':{
                'input_tokens':100, 'cache_read_input_tokens':5000, 'cache_creation_input_tokens':200}}})
            timer.observe({'type':'result', 'usage':{'input_tokens':900000, 'output_tokens':1000}})
            rows = [c.kwargs['context_tokens'] for c in emit.call_args_list if c.args[0] == 'model_context']
            self.assertEqual(rows, [12000, 5300])

    def test_concurrent_tool_ids_gaps_and_first_response(self):
        clock = [10.]
        with patch.dict(os.environ, UNCLE_TIMING_DIR='/unused'), patch.object(timing, 'event') as emit, \
                patch.object(timing.time, 'monotonic', side_effect=lambda: clock[0]):
            timer = timing.RunnerTiming('execute-checklist')
            for identity in ('a','b'):
                timer.observe(dict(method='item/started', params={'item':{'id':identity,'type':'commandExecution'}}))
            clock[0] = 13.
            timer.observe(dict(method='item/completed', params={'item':{'id':'b','type':'commandExecution'}}))
            clock[0] = 15.
            timer.observe(dict(method='item/agentMessage/delta',params={'delta':'private text'}))
            timer.observe(dict(method='item/completed', params={'item':{'id':'a','type':'commandExecution'}}))
            timer.finish()
            calls = [call for call in emit.call_args_list if call.args[0] == 'tool_call']
            self.assertEqual([call.args[3] for call in calls], [3.,5.])
            responses = [call for call in emit.call_args_list if call.args[0]=='runner_first_response']
            self.assertEqual(len(responses), 1)
            self.assertEqual(responses[0].args[3], 5.)
            self.assertNotIn('private text', str(emit.call_args_list))
            self.assertTrue(any(call.args[0]=='runner_event_gap' for call in emit.call_args_list))

    def test_claude_cline_kimi_and_unpaired_events(self):
        with patch.dict(os.environ, UNCLE_TIMING_DIR='/unused'), patch.object(timing, 'event') as emit:
            timer = timing.RunnerTiming('execute-checklist')
            timer.observe({'type':'assistant','message':{'content':[{'type':'tool_use','id':'c','name':'Read','input':'secret'}]}})
            timer.observe({'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'c','content':'secret'}]}})
            for kind in ('content_start', 'content_end'):
                timer.observe({'method':'agent_event','params':{'type':kind,'contentType':'tool','toolCallId':'d','toolName':'Bash'}})
            timer.observe({'method':'event','params':{'type':'ToolCall','payload':{'id':'k','function':{'name':'Shell'}}}})
            timer.observe({'method':'event','params':{'type':'ToolResult','payload':{'tool_call_id':'k'}}})
            timer.tool('missing','Read','end')
            timer.tool('pending','Write','start')
            timer.finish()
            kinds=[c.args[0] for c in emit.call_args_list]
            self.assertEqual(kinds.count('tool_call'), 3)
            self.assertEqual(kinds.count('tool_unpaired'), 1)
            self.assertEqual(kinds.count('tool_unfinished'), 1)
            self.assertNotIn('secret', str(emit.call_args_list))

    def test_opencode_poll_deduplication(self):
        with patch.dict(os.environ, UNCLE_TIMING_DIR='/unused'), patch.object(timing, 'event') as emit:
            timer = timing.RunnerTiming('execute-checklist')
            for status in ('running','running','completed','completed'):
                timer.observe({'method':'http/message','params':{'parts':[{'type':'tool','callID':'t','tool':'read','state':{'status':status}}]}})
            timer.finish()
            self.assertEqual(sum(c.args[0]=='tool_call' for c in emit.call_args_list), 1)

    def test_stream_is_byte_preserving_even_for_non_json(self):
        with tempfile.TemporaryDirectory() as directory:
            data=b'notice\xff\n{"type":"system"}\nlast line'
            result=subprocess.run([sys.executable,timing.__file__,'stream','execute-checklist'],input=data,
                                  capture_output=True,env=dict(os.environ,UNCLE_TIMING_DIR=directory))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,data)

    def test_explicit_checklist_timers_retry_and_unfinished(self):
        with tempfile.TemporaryDirectory() as directory, patch('build_timing.snapshot', return_value=[]):
            with BuildTiming(Path(directory)) as build:
                tokens=[]
                for _ in range(2):
                    out=io.StringIO()
                    with contextlib.redirect_stdout(out): timing.checklist('check-start','MC-001')
                    tokens.append(out.getvalue().strip())
                timing.checklist('check-end',tokens[0],'failed')
                timing.checklist('check-end',tokens[0],'finished')  # first outcome is retained
                self.assertNotEqual(*tokens)
            records=[json.loads(p.read_text()) for p in (build.directory/'checklist').glob('*.json')]
            self.assertEqual(sum('ended_at' in row for row in records),1)
            self.assertEqual(next(r for r in records if 'ended_at' in r)['observation_status'],'failed')
            report=(build.directory/'report.md').read_text()
            self.assertIn('Checklist Item',report)
            self.assertIn('Checklist Unfinished',report)

    def test_native_normalized_stream_is_not_double_counted(self):
        with patch.dict(os.environ, UNCLE_TIMING_DIR='/unused'), patch.object(timing, 'event') as emit:
            timer=timing.RunnerTiming('execute-checklist')
            timer.observe({'type':'assistant','uncle_timing_native':True})
            timer.finish()
            emit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
