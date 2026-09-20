import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SDK = '''
let sends=0, starts=0;
export const getClineDefaultSystemPrompt=()=>'';
export const ClineCore={async create(){return {
 subscribe(){}, async dispose(){},
 async start(){starts++;return {sessionId:'original-session'}},
 async send(request){
  sends++;
  if(request.sessionId!=='original-session')throw new Error('Wrong session');
  if(sends>1 && !request.prompt.includes('do not repeat completed'))throw new Error('Replayed task');
  const mode=process.env.TEST_MODE;
  if(mode==='aborted')return {finishReason:'aborted',text:'ERR_HTTP2_STREAM_ERROR'};
  if(mode==='fatal')return {finishReason:'error',text:'Authentication rejected'};
  if(mode==='tool')return {finishReason:'error',text:'Tests failed'};
  if(mode==='iteration' && sends===1)return {finishReason:'error',text:'Agent runtime exceeded maxIterations (21)'};
  if(mode==='exhaust'||(mode==='recover' && sends<3))return {finishReason:'error',text:'terminated: NGHTTP2_INTERNAL_ERROR (ERR_HTTP2_STREAM_ERROR)'};
  if(mode==='throw' && sends===1)throw new Error('socket ECONNRESET');
  return {finishReason:'completed',text:JSON.stringify({starts,sends,session:request.sessionId})};
 },
 async getAccumulatedUsage(){return {aggregateUsage:{inputTokens:100*sends,outputTokens:10*sends,totalCost:.01*sends}}}
}}};
'''

@unittest.skipUnless(shutil.which('node'), 'Node is required for Cline')
class ClineTransportTests(unittest.TestCase):
    def run_bridge(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            sdk=Path(directory)/'sdk.mjs'
            sdk.write_text(SDK)
            payload=dict(id='start',method='start',params=dict(prompt='Original stage task',model='test-model',
                         effort='medium',cwd=directory,mode='act',turns=80))
            result=subprocess.run(['node',str(ROOT/'scripts/lib/cline-native.mjs'),str(sdk)],
                                  input=json.dumps(payload)+'\n',capture_output=True,text=True,
                                  env=dict(os.environ,TEST_MODE=mode),timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            events=[json.loads(line) for line in result.stdout.splitlines()]
            final=next(event['result'] for event in events if event.get('id')=='start')
            retries=[event for event in events if ('retry ' in event.get('params',{}).get('text','')
                                                   or 'fresh session' in event.get('params',{}).get('text',''))]
            self.assertEqual(sum(event.get('method')=='ready' for event in events),1)
            return final,retries

    def test_transport_recovery_keeps_session_and_usage(self):
        result,retries=self.run_bridge('recover')
        self.assertEqual(result['finishReason'],'completed')
        self.assertEqual(json.loads(result['text']),dict(starts=1,sends=3,session='original-session'))
        self.assertEqual(len(retries),2)
        self.assertEqual(result['usage']['inputTokens'],300)
        self.assertAlmostEqual(result['usage']['totalCost'],.03)

    def test_transport_exception_can_continue(self):
        result,retries=self.run_bridge('throw')
        self.assertEqual(result['finishReason'],'completed')
        self.assertEqual(json.loads(result['text'])['sends'],2)
        self.assertEqual(len(retries),1)

    def test_maximum_two_retries_then_preserve_failure(self):
        result,retries=self.run_bridge('exhaust')
        self.assertEqual(result['finishReason'],'error')
        self.assertEqual(len(retries),2)
        self.assertEqual(result['usage']['inputTokens'],300)

    def test_iteration_limit_gets_one_fresh_session_continuation(self):
        result,retries=self.run_bridge('iteration')
        self.assertEqual(result['finishReason'],'completed')
        self.assertEqual(json.loads(result['text'])['starts'],2)
        self.assertEqual(json.loads(result['text'])['sends'],2)
        self.assertTrue(any('fresh session' in event.get('params',{}).get('text','')
                            for event in retries))

    def test_nontransport_errors_do_not_retry(self):
        for mode in ('fatal','tool'):
            result,retries=self.run_bridge(mode)
            self.assertEqual(result['finishReason'],'error')
            self.assertEqual(retries,[])
            self.assertEqual(result['usage']['inputTokens'],100)

    def test_aborted_session_does_not_retry(self):
        result,retries=self.run_bridge('aborted')
        self.assertEqual(result['finishReason'],'aborted')
        self.assertEqual(retries,[])
        self.assertEqual(result['usage']['inputTokens'],100)

    def test_success_does_not_retry(self):
        result,retries=self.run_bridge('success')
        self.assertEqual(json.loads(result['text'])['sends'],1)
        self.assertEqual(retries,[])

if __name__=='__main__':unittest.main()
