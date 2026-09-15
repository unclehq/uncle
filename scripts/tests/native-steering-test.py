import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/lib'))
from native_stage import Stage

FAKE='''#!/usr/bin/env python3
import sys,json,os
if '--help' in sys.argv:
 print('--wire');sys.exit()
def out(v):print(json.dumps(v),flush=True)
for line in sys.stdin:
 e=json.loads(line);m=e.get('method');i=e.get('id');p=e.get('params',{})
 if m=='initialize':out({'id':i,'result':{}})
 elif m=='thread/start':out({'id':i,'result':{'thread':{'id':'same-session'},'model':'fake-model'}})
 elif m=='turn/start':
  out({'id':i,'result':{'turn':{'id':'same-turn'}}})
  out({'method':'thread/tokenUsage/updated','params':{'tokenUsage':{'total':{'inputTokens':100,'outputTokens':20,'cachedInputTokens':10}}}})
 elif m=='turn/steer':
  assert p['threadId']=='same-session' and p['expectedTurnId']=='same-turn'
  assert p['input'][0]['text']=='Use the requested direction'
  out({'id':i,'result':{'turnId':'same-turn'}})
  for _ in range(2):out({'method':'thread/tokenUsage/updated','params':{'tokenUsage':{'total':{'inputTokens':150,'outputTokens':30,'cachedInputTokens':15}}}})
  out({'method':'item/agentMessage/delta','params':{'delta':'Steered reply'}})
  out({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'Steered reply'}}})
  out({'method':'turn/completed','params':{'turn':{'id':'same-turn','status':'completed'}}})
 elif m=='prompt':
  turn=i
  out({'method':'event','params':{'type':'StepBegin','payload':{'n':1}}})
  out({'method':'event','params':{'type':'StatusUpdate','payload':{'message_id':'m1','token_usage':{'input_other':100,'output':20,'input_cache_read':10,'input_cache_creation':0}}}})
 elif m=='steer':
  assert p['user_input']=='Use the requested direction'
  out({'id':i,'result':{'status':'steered'}})
  for _ in range(2):out({'method':'event','params':{'type':'StatusUpdate','payload':{'message_id':'m1','token_usage':{'input_other':150,'output':30,'input_cache_read':15,'input_cache_creation':0}}}})
  out({'method':'event','params':{'type':'ContentPart','payload':{'type':'text','text':'Steered reply'}}})
  out({'id':turn,'result':{'status':'finished'}})
 elif e.get('type')=='user':
  if e['message']['content']=='Use the requested direction':
   out({'type':'result','is_error':False,'usage':{'input_tokens':100,'output_tokens':20},'total_cost_usd':0.005})
   out({'type':'user','uuid':e['uuid']})
   out({'type':'assistant','message':{'content':[{'type':'text','text':'Steered reply'}]}})
   out({'type':'result','is_error':False,'usage':{'input_tokens':150,'output_tokens':30,'cache_read_input_tokens':15},'total_cost_usd':0.01})
'''

HTTP_FAKE='''#!/usr/bin/env python3
import sys,json
from http.server import HTTPServer,BaseHTTPRequestHandler
port=int(sys.argv[sys.argv.index('--port')+1]);kimi='web' in sys.argv
if kimi:print('Token: fake-test-token',flush=True)
count=0
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def answer(self,value):
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
  if kimi:value={'code':0,'data':value}
  self.wfile.write(json.dumps(value).encode())
 def do_POST(self):
  global count
  data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or '{}')
  if self.path in ('/session','/api/v1/sessions'):return self.answer({'id':'same-session'})
  if self.path.endswith('/prompt_async') or self.path.endswith('/prompts'):
   count+=1
   return self.answer({'prompt_id':str(count),'status':'queued' if count>1 else 'running'})
  if self.path.endswith('/prompts:steer'):return self.answer({'steered':True})
  return self.answer({})
 def do_GET(self):
  if self.path in ('/global/health','/api/v1/healthz'):return self.answer({'ok':True})
  if self.path=='/session/status':return self.answer({'same-session':{'type':'idle' if count>1 else 'busy'}})
  if self.path.endswith('/message'):
   u=[{'info':{'id':'u'+str(i),'role':'user'}} for i in range(1,count+1)]
   return self.answer(u+[{'info':{'id':'a1','role':'assistant','parentID':'u'+str(count),
    'tokens':{'input':150 if count>1 else 100,'output':30,'cache':{'read':15,'write':0}},'cost':.02,'time':{'completed':123 if count>1 else None}},
    'parts':[{'id':'text','type':'text','text':'Steered reply' if count>1 else ''}]}])
  if self.path.endswith('/snapshot'):
   return self.answer({'session':{'main_turn_active':count<2,'last_turn_reason':'completed',
    'agent_config':{'model':'fake-model'},'usage':{'input_tokens':150 if count>1 else 100,'output_tokens':30,'cache_read_tokens':15,'cache_creation_tokens':0,'total_cost_usd':.02}},
    'messages':{'items':[{'id':'a1','role':'assistant','content':[{'type':'text','text':'Steered reply' if count>1 else ''}]}]}})
  if self.path.endswith('/prompts'):return self.answer({'active':{} if count<2 else None,'queued':[]})
  return self.answer({})
HTTPServer(('127.0.0.1',port),Handler).serve_forever()
'''
CLINE_FAKE='''
let callback,resolve;
const host={subscribe(f){callback=f},async start(){return {sessionId:'same-session'}},
 async send(p){
  if(p.delivery==='steer'){
   if(p.sessionId!=='same-session')throw Error('wrong session');
   callback({type:'agent_event',payload:{sessionId:'same-session',event:{type:'usage',totalInputTokens:150,totalOutputTokens:30,totalCacheReadTokens:15,totalCost:.02}}});
   callback({type:'agent_event',payload:{sessionId:'same-session',event:{type:'content_end',contentType:'text',text:'Steered reply'}}});
   setTimeout(()=>resolve({finishReason:'completed',usage:{inputTokens:150,outputTokens:30,cacheReadTokens:15,totalCost:.02}}),20);
   return;
  }
  return new Promise(r=>{resolve=r});
 },async dispose(){}};
export const ClineCore={async create(){return host}};
export const getClineDefaultSystemPrompt=()=>'';
'''

class NativeTests(unittest.TestCase):
 def test_readonly_reviewer_final_json_is_saved_by_adapter(self):
  fake_code = """#!/usr/bin/env python3
import json, sys
def send(value): print(json.dumps(value), flush=True)
for line in sys.stdin:
 event = json.loads(line)
 method = event.get('method')
 if method == 'initialize': send({'id':event['id'], 'result':{}})
 elif method == 'thread/start':
  assert event['params']['sandbox'] == 'read-only'
  assert event['params']['approvalPolicy'] == 'never'
  send({'id':event['id'], 'result':{'thread':{'id':'review'}}})
 elif method == 'turn/start':
  send({'id':event['id'], 'result':{'turn':{'id':'assessment'}}})
  send({'method':'item/agentMessage/delta', 'params':{'delta':'Reading inputs.'}})
  send({'method':'item/completed', 'params':{'item':{'type':'agentMessage', 'text':'{"version":1,"input_digest":"fixture","verdict":"REVISE"}'}}})
  send({'method':'item/completed', 'params':{'item':{'type':'agentMessage', 'text':'Yes—three coding blockers remain.'}}})
  send({'method':'turn/completed', 'params':{'turn':{'id':'assessment', 'status':'completed'}}})
"""
  with tempfile.TemporaryDirectory() as d:
   root = Path(d)
   fake = root/'runner'
   fake.write_text(fake_code)
   fake.chmod(0o755)
   output = root/'assessment.json'
   result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/lib/native_stage.py'),
                            '--runner', 'codex', '--side', 'reviewer', '--stage', 'plan-executability',
                            '--', 'exec', '--output-last-message', str(output), 'Return assessment JSON.'],
                           cwd=root, env=dict(os.environ, WORKFLOW_CODEX_CMD=str(fake)),
                           capture_output=True, text=True, timeout=15)
   self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
   self.assertEqual(json.loads(output.read_text()), {'version':1, 'input_digest':'fixture', 'verdict':'REVISE'})

 def test_review_final_answer_is_not_replaced_by_compaction_commentary(self):
  stage = Stage('codex', 'reviewer', 'test-review', [], prompt='Review')
  stage.answer = 'Streamed compaction commentary'
  stage.completed_answer('Compacting the report', phase='commentary')
  self.assertEqual(stage.output_answer(), '')
  stage.completed_answer('## Acceptance gate\nComplete report', phase='final_answer')
  stage.completed_answer('Compacting (pass 1)', phase='commentary')
  self.assertEqual(stage.output_answer(), '## Acceptance gate\nComplete report')

 def test_assessment_capture_is_scoped_and_uses_latest_complete_object(self):
  stage = Stage('codex', 'reviewer', 'plan-executability', [], prompt='Review')
  first = json.dumps({'version':1, 'input_digest':'first', 'verdict':'READY'})
  latest = json.dumps({'version':1, 'input_digest':'second', 'verdict':'REVISE'})
  stage.completed_answer(first)
  stage.completed_answer(latest)
  stage.completed_answer('Three blockers remain.')
  self.assertEqual(stage.output_answer(), latest)
  stage.stage = 'adversarial-review'
  self.assertEqual(stage.output_answer(), 'Three blockers remain.')
  stage.stage = 'plan-executability'
  stage.assessment_answer = ''
  stage.completed_answer('Summary: ' + first)
  self.assertEqual(stage.output_answer(), 'Summary: ' + first)

 def test_all_stage_prompts_preserve_work_after_chat(self):
  sys.path.insert(0, str(ROOT))
  import uncle_tui
  for name, side in uncle_tui.STAGES:
   for runner in ('claude', 'codex', 'kimi', 'cline', 'self-hosted'):
    with self.subTest(stage=name, side=side, runner=runner):
     stage = Stage(runner, side, name, [], prompt='Required stage task')
     self.assertIn('continue unfinished stage', stage.prompt)
     self.assertIn('required stage output in its required format', stage.prompt)
     self.assertIn('All automated tests and test fixtures MUST disable', stage.prompt)
     self.assertIn('--no-gpg-sign', stage.prompt)
     self.assertIn('present the exact', stage.prompt)
     self.assertIn('must work without creating a project commit', stage.prompt)
     self.assertIn('resuming an older plan', stage.prompt)
     self.assertTrue(stage.prompt.endswith('Required stage task'))

 def test_claude_batched_steering_completes_all_stages(self):
  sys.path.insert(0, str(ROOT))
  import uncle_tui
  for name, side in uncle_tui.STAGES:
   with self.subTest(stage=name, side=side):
    stage = Stage('claude', side, name, [], prompt='Required stage task')
    stage.spawn = lambda command: None
    stage.send = lambda message: None
    stage.ready = lambda directory: None
    stage.status = lambda *args, **kwargs: None
    stage.text = lambda text: None
    stage.tokens = lambda *args, **kwargs: None
    def loop(handle, steer):
     steer('Use the reference image', 'one')
     steer('What is happening?', 'two')
     handle({'type': 'user', 'uuid': 'one'})
     handle({'type': 'user', 'uuid': 'two'})
     self.assertTrue(handle({'type': 'result', 'is_error': False, 'usage': {}}))
    stage.loop = loop
    stage.claude('unused')

 def test_native_same_session_and_metrics(self):
  sys.path.insert(0, str(ROOT))
  import uncle_tui
  for runner, name, side in ((r, n, s) for r in ('codex','kimi','claude') for n, s in uncle_tui.STAGES):
   with self.subTest(runner=runner, stage=name, side=side),tempfile.TemporaryDirectory() as d:
    root=Path(d);fake=root/'runner';fake.write_text(FAKE);fake.chmod(0o755)
    status=root/'status';status.touch()
    env=dict(os.environ,UNCLE_STATUS_FILE=str(status),PYTHONDONTWRITEBYTECODE='1')
    env['WORKFLOW_'+runner.upper()+'_CMD']=str(fake)
    args=[sys.executable,'-B',str(ROOT/'scripts/lib/native_stage.py'),'--runner',runner,'--side',side,'--stage',name,'--','-p','--model','fake-model','--effort','high']
    if side == 'reviewer': args.append('Initial task')
    child=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,cwd=d)
    try:
     child.stdin.write('Initial task');child.stdin.close();child.stdin=None
     deadline=time.monotonic()+10
     while time.monotonic()<deadline:
      events=[json.loads(x) for x in status.read_text().splitlines()]
      ready=next((e for e in events if e['event']=='steering_ready'),None)
      if ready:break
      if child.poll() is not None:break
      time.sleep(.02)
     self.assertIsNotNone(ready)
     message=Path(ready['channel'])/'direction.json'
     message.write_text(json.dumps({'id':'direction','text':'Use the requested direction'}))
     stdout,stderr=child.communicate(timeout=10)
     self.assertEqual(child.returncode,0,stderr+stdout)
     result=json.loads(stdout.splitlines()[-1])
     self.assertEqual(result['usage']['input_tokens'],250 if runner=='claude' else 150)
     self.assertEqual(result['usage']['output_tokens'],50 if runner=='claude' else 30)
     events=[json.loads(x) for x in status.read_text().splitlines()]
     self.assertEqual(len([e for e in events if e['event']=='steering_ready']),1)
     accepted=[e for e in events if e['event']=='steering_accepted']
     self.assertEqual(len(accepted),1)
     answered=[e for e in events if e['event']=='steering_answered']
     if runner=='claude':
      # D-13: the original prompt's result arrives after acceptance and is not the
      # answer; only the result of the steered turn answers it.
      self.assertEqual(accepted[0]['correlation'],'turn')
      self.assertEqual([e['message_id'] for e in answered],['direction'])
      order=[e['event'] for e in events if e['event'] in ('steering_accepted','chat_output','steering_answered')]
      self.assertEqual(order,['steering_accepted','chat_output','steering_answered'])
      self.assertEqual([e for e in events if e['event']=='steering_unconfirmed'],[])
     else:
      self.assertEqual(accepted[0]['correlation'],'none')
      self.assertEqual(answered,[],'no native correlation: never guessed answered')
      self.assertEqual([e['message_id'] for e in events if e['event']=='steering_unconfirmed'],['direction'])
     self.assertFalse(Path(ready['channel']).exists())
    finally:
     if child.poll() is None:child.kill();child.wait()

 def test_cline_and_http_sessions_steer_without_restart(self):
  for runner in ('cline','self-hosted','kimi'):
   with self.subTest(runner=runner),tempfile.TemporaryDirectory() as d:
    root=Path(d);fake=root/'runner';fake.write_text(HTTP_FAKE);fake.chmod(0o755)
    if runner=='cline':
     sdk=root/'node_modules/@cline/sdk/dist';sdk.mkdir(parents=True)
     (sdk/'index.js').write_text(CLINE_FAKE)
     (sdk.parent/'package.json').write_text('{"type":"module"}')
    status=root/'events';status.touch()
    env=dict(os.environ,UNCLE_STATUS_FILE=str(status),PYTHONDONTWRITEBYTECODE='1',
             UNCLE_SELF_HOSTED_BASE_URL='http://localhost:9999/v1',UNCLE_SELF_HOSTED_MODEL='fake-model',UNCLE_SELF_HOSTED_API_KEY='fake')
    if runner=='kimi':
     # The current Kimi transport detects the absence of --wire from --help.
     fake.write_text(HTTP_FAKE.replace("port=int(sys.argv", "if '--help' in sys.argv:print('web');sys.exit()\nport=int(sys.argv"))
    env['WORKFLOW_'+('OPENCODE' if runner=='self-hosted' else runner.upper())+'_CMD']=str(fake)
    args=[sys.executable,'-B',str(ROOT/'scripts/lib/native_stage.py'),'--runner',runner,'--side','reviewer','--stage','test-review','--','exec','--model','fake-model','--output-last-message',str(root/'reply'),'Initial task']
    child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,cwd=d)
    try:
     ready=None;deadline=time.monotonic()+12
     while time.monotonic()<deadline:
      events=[json.loads(x) for x in status.read_text().splitlines()]
      ready=next((e for e in events if e['event']=='steering_ready'),None)
      if ready or child.poll() is not None:break
      time.sleep(.03)
     if not ready:
      stdout,stderr=child.communicate(timeout=1)
      self.fail(stdout+stderr)
     (Path(ready['channel'])/'direction.json').write_text(json.dumps({'id':'direction','text':'Use the requested direction'}))
     stdout,stderr=child.communicate(timeout=10)
     self.assertEqual(child.returncode,0,stdout+stderr)
     result=json.loads(stdout.splitlines()[-1])
     self.assertEqual(result['usage']['input_tokens'],250 if runner=='claude' else 150)
     self.assertEqual(result['total_cost_usd'],.02)
     self.assertEqual((root/'reply').read_text(),'Steered reply')
     events=[json.loads(x) for x in status.read_text().splitlines()]
     accepted=[e for e in events if e['event']=='steering_accepted']
     self.assertEqual(len(accepted),1)
     answered=[e for e in events if e['event']=='steering_answered']
     if runner=='self-hosted':
      self.assertEqual(accepted[0]['correlation'],'message')
      self.assertEqual([(e['message_id'],e['response_id']) for e in answered],[('direction','a1')])
     else:
      self.assertEqual(accepted[0]['correlation'],'none')
      self.assertEqual(answered,[])
      self.assertEqual([e['message_id'] for e in events if e['event']=='steering_unconfirmed'],['direction'])
    finally:
     if child.poll() is None:child.kill();child.wait()

 @unittest.skipUnless(os.name == 'posix', 'POSIX parent death; Windows uses Job Objects')
 def test_sigkill_of_workflow_parent_cancels_native_runner(self):
  import signal
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);fake=root/'runner'
   fake.write_text(FAKE.replace('import sys,json,os', 'import sys,json,os\nopen(os.environ["FAKE_PID"],"w").write(str(os.getpid()))'))
   fake.chmod(0o755)
   status=root/'events';status.touch()
   env=dict(os.environ,UNCLE_STATUS_FILE=str(status),WORKFLOW_CODEX_CMD=str(fake),FAKE_PID=str(root/'runner.pid'),PYTHONDONTWRITEBYTECODE='1')
   args=[sys.executable,'-B',str(ROOT/'scripts/lib/native_stage.py'),'--runner','codex','--side','reviewer','--stage','baseline','--','exec','Initial task']
   wrapper='import subprocess,sys,time; from pathlib import Path; child=subprocess.Popen(sys.argv[1:]); Path("stage.pid").write_text(str(child.pid)); child.wait()'
   with (root/'output').open('w') as log:
    parent=subprocess.Popen([sys.executable,'-c',wrapper,*args],cwd=d,env=env,stdout=log,stderr=log)
    try:
     deadline=time.monotonic()+10
     while 'steering_ready' not in status.read_text() and time.monotonic()<deadline:
      time.sleep(.03)
     self.assertIn('steering_ready',status.read_text())
     parent.kill();parent.wait()
     deadline=time.monotonic()+10
     while 'Workflow parent exited' not in (root/'output').read_text() and time.monotonic()<deadline:
      time.sleep(.03)
     self.assertIn('Workflow parent exited; native stage cancelled',(root/'output').read_text())
     self.assertIn('steering_closed',status.read_text())
     runner_pid=int((root/'runner.pid').read_text())
     state=subprocess.run(['ps','-p',str(runner_pid),'-o','stat='],capture_output=True,text=True).stdout.strip()
     self.assertTrue(not state or state.startswith('Z'),state)
    finally:
     if parent.poll() is None:parent.kill();parent.wait()
     for name in ('stage.pid','runner.pid'):
      if (root/name).exists():
       try:os.kill(int((root/name).read_text()),signal.SIGTERM)
       except ProcessLookupError:pass

 def test_cumulative_usage_replaces_previous_snapshot(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'UNCLE_STATUS_FILE':str(Path(d)/'events')}):
   stage=Stage('cline','agent','implementation',[],prompt='task')
   stage.tokens({'input_tokens':100,'output_tokens':20},.01)
   stage.tokens({'input_tokens':150,'output_tokens':30},.02)
   stage.tokens({'input_tokens':150,'output_tokens':30},.02)
   self.assertEqual(stage.usage['input_tokens'],150)
   self.assertEqual(stage.cost,.02)

 def test_retry_usage_includes_previous_attempt_without_mutating_current(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'UNCLE_STATUS_FILE':str(Path(d)/'events')}):
   stage=Stage('self-hosted','agent','implementation',[],prompt='task')
   stage.usage_baseline={'input_tokens':120,'output_tokens':20,'_total_cost_usd':.01}
   stage.tokens({'input_tokens':100,'output_tokens':30,'cache_read_input_tokens':10},.02,inclusive=False)
   event=json.loads((Path(d)/'events').read_text())
   self.assertEqual(event['total_tokens'],280)
   self.assertAlmostEqual(event['total_cost_usd'],.03)
   self.assertEqual(stage.usage['input_tokens'],100)

 def test_disconnected_session_fails_instead_of_restarting(self):
  stage=Stage('codex','agent','implementation',[],prompt='task')
  stage.events.put({'_eof':True})
  with self.assertRaisesRegex(ValueError,'disconnected'):
   stage.loop(lambda event:False,lambda text,id:None)

BUDGET_FAKE = '''#!/usr/bin/env python3
import sys,json,os
if '--help' in sys.argv:
 print('--wire');sys.exit()
def out(v):print(json.dumps(v),flush=True)
steps=[int(x) for x in os.environ.get('STEPS','100000,350000,400000').split(',')]
def usage(n):out({'method':'thread/tokenUsage/updated','params':{'tokenUsage':{'total':{'inputTokens':n,'outputTokens':10,'cachedInputTokens':0}}}})
def done():
 out({'method':'item/agentMessage/delta','params':{'delta':'done'}})
 out({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'done'}}})
 out({'method':'turn/completed','params':{'turn':{'id':'u','status':'completed'}}})
for line in sys.stdin:
 e=json.loads(line);m=e.get('method');i=e.get('id');p=e.get('params',{})
 if m=='initialize':out({'id':i,'result':{}})
 elif m=='thread/start':out({'id':i,'result':{'thread':{'id':'t'},'model':'fake-model'}})
 elif m=='turn/start':
  out({'id':i,'result':{'turn':{'id':'u'}}})
  for n in steps:usage(n)
  if os.environ.get('COMPLETE_ON_START'):done()
 elif m=='turn/steer':
  with open(os.environ['RECORD'],'a') as f:f.write(p['input'][0]['text']+'\\n')
  out({'id':i,'result':{'turnId':'u'}})
  done()
'''

class ContextBudgetTests(unittest.TestCase):
 def run_stage(self,root,env_extra):
  root=Path(root);fake=root/'runner';fake.write_text(BUDGET_FAKE);fake.chmod(0o755)
  status=root/'status';status.touch()
  env=dict(os.environ,UNCLE_STATUS_FILE=str(status),PYTHONDONTWRITEBYTECODE='1',
           RECORD=str(root/'record'),**env_extra)
  env['WORKFLOW_CODEX_CMD']=str(fake)
  args=[sys.executable,'-B',str(ROOT/'scripts/lib/native_stage.py'),'--runner','codex','--side','agent','--stage','implementation','--','-p','--model','fake-model']
  child=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,cwd=root)
  child.stdin.write('Initial task');child.stdin.close();child.stdin=None
  stdout,stderr=child.communicate(timeout=10)
  return child,stdout,stderr,status

 def test_auto_steer_fires_once_above_budget(self):
  with tempfile.TemporaryDirectory() as d:
   child,stdout,stderr,status=self.run_stage(d,{'STEPS':'100000,350000,400000'})
   self.assertEqual(child.returncode,0,stderr+stdout)
   text=(Path(d)/'record').read_text()
   self.assertEqual(text.count('Context budget'),1)
   self.assertIn('250000',text)
   events=[json.loads(x) for x in status.read_text().splitlines()]
   accepted=[e for e in events if e['event']=='steering_accepted' and e.get('message_id')=='context-budget']
   self.assertEqual(len(accepted),1)

 def test_no_steer_below_budget(self):
  with tempfile.TemporaryDirectory() as d:
   child,stdout,stderr,_=self.run_stage(d,{'STEPS':'100000,150000,180000','COMPLETE_ON_START':'1'})
   self.assertEqual(child.returncode,0,stderr+stdout)
   self.assertFalse((Path(d)/'record').exists())

 def test_ceiling_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   child,stdout,stderr,_=self.run_stage(d,{'STEPS':'100000,400000','WORKFLOW_CONTEXT_CEILING_TOKENS':'250000'})
   self.assertNotEqual(child.returncode,0)
   self.assertIn('context budget exceeded',stderr+stdout)

if __name__=='__main__':unittest.main()
