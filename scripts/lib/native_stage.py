"""Native, bidirectional stage sessions with stage-scoped steering and usage."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from runner_timing import RunnerTiming
from read_cache import ReadCache
from process_tree import timed_popen
from process_tree import launch_command, group_options, kill_tree, finish_check

KEYS = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')

STEERING_INSTRUCTIONS = """Live stage chat:
User messages may arrive while you work. Apply relevant steering to the current
stage. Answer status or general questions briefly, then continue unfinished stage
work without waiting for another message. A question does not cancel the task.
Honor explicit requests to stop or change direction. Keep the stage's permissions,
approval gates, and required deliverables; do not approve gates on the user's behalf.
Before completing, produce the required stage output in its required format, even
if you also answered chat questions. Finish normally when the stage is complete;
the workflow driver owns advancement to the next stage.

Stage task:
"""

CONTEXT_BUDGET_NOTE = ('Context budget: your requests now carry %d tokens. Before continuing, '
    'persist anything you still need to your stage handoff or output document, then work with '
    'the smallest set that finishes the stage: do not re-read files or logs already inspected, '
    'read by path and section when needed, and keep tool outputs short.')

class Stage:
    def __init__(self, runner, side, stage, args, prompt=None):
        self.parent_pid = os.getppid()
        self.parent_lost = False
        self.parent_watch_stop = threading.Event()
        self.runner, self.side, self.stage, self.args = runner, side, stage, args
        self.model = self.option('--model', '-m') or ''
        self.effort = self.option('--effort') or os.environ.get('UNCLE_CLINE_EFFORT', 'medium')
        for i, arg in enumerate(args[:-1]):
            if arg == '-c' and args[i+1].startswith('model_reasoning_effort='):
                self.effort = args[i+1].split('=', 1)[1]
        self.output = self.option('--output-last-message', '-o')
        self.prompt = prompt if prompt is not None else (sys.stdin.read() if side == 'agent' else args[-1])
        self.read_cache = ReadCache(os.getcwd())
        self.prompt += self.read_cache.context(self.prompt)
        self.prompt = STEERING_INSTRUCTIONS + self.prompt
        execution_rules = Path(__file__).resolve().parents[2] / 'lib/gates/EXECUTION_RULES.md'
        if execution_rules.is_file():
            policy = execution_rules.read_text(encoding='utf-8')
            if policy not in self.prompt:
                self.prompt = policy + '\n\n' + self.prompt
        self.events = queue.Queue()
        self.child = None
        self.pooled = False
        self.usage = dict.fromkeys(KEYS, 0)
        self.usage_baseline = {}
        self.cost = None
        self.inclusive = True
        self._prev_ctx = 0
        self._budget_steered = False
        self.context_budget_hit = 0
        self.answer = ''
        self.final_answer = ''
        self.assessment_answer = ''
        self.started = time.monotonic()
        self.timing = RunnerTiming(stage)
        self.channel = None
        self.pending = {}
        # Submitted inputs in order, the original prompt first. A runner that
        # answers inputs one response at a time (correlation 'turn') pops the
        # head on every completed response, so the original response can never
        # count as the answer to steering accepted while it was still running.
        self.turns = []
        self.accepted = set()
        self.correlation = 'none'  # 'turn' | 'message' | 'none': how answers are tied to steering
        self.note = os.environ.get('UNCLE_SUPERVISION_NOTE', '')
        self.turn = self.session = None
        self.env = os.environ.copy()
        for key in ('UNCLE_STATUS_FILE', 'UNCLE_PROJECT_ROOT', 'UNCLE_CONFIG', 'UNCLE_STEERING',
                    'STAGEGATE_RUN_ID', 'STAGEGATE_ORIGIN_REPO', 'STAGEGATE_ORIGIN_ISSUE', 'DOCUMENT_BUDGET_SOURCE',
                    'UNCLE_SUPERVISION_NOTE', 'UNCLE_SUPERVISION_HOST'):
            self.env.pop(key, None)

    def option(self, *names):
        for i, arg in enumerate(self.args[:-1]):
            if arg in names:
                return self.args[i+1]
        return None

    def status(self, event, **fields):
        path = os.environ.get('UNCLE_STATUS_FILE')
        if path:
            data = dict(event=event, stage=self.stage, runner=self.runner, model=self.model,
                        effort=self.effort, mode='act' if self.side == 'agent' else 'review', **fields)
            with open(path, 'a', encoding='utf-8') as stream:
                stream.write(json.dumps(data) + '\n')

    def tokens(self, usage, cost=None, inclusive=True):
        self.usage = {key: int(usage.get(key, 0) or 0) for key in KEYS}
        self.cost = cost if cost is not None else self.cost
        self.inclusive = inclusive
        reported = {key: self.usage[key] + self.usage_baseline.get(key, 0) for key in KEYS}
        reported_cost = None if self.cost is None else self.cost + self.usage_baseline.get('_total_cost_usd', 0)
        self.timing.usage(reported, reported_cost if cost is not None else None, inclusive, self.model)
        ctx = sum(reported.values()) - (sum(reported[k] for k in KEYS[2:]) if inclusive else 0)
        self.status('usage', usage=reported, total_cost_usd=reported_cost, input_includes_cache=inclusive,
                    total_tokens=ctx)
        per_request = ctx - self._prev_ctx
        self._prev_ctx = max(self._prev_ctx, ctx)
        if per_request > 0:
            ceiling = int(os.environ.get('WORKFLOW_CONTEXT_CEILING_TOKENS', '0'))
            if ceiling and per_request > ceiling:
                raise ValueError('Stage context budget exceeded (%d tokens in one request); '
                                 'split the change or use a larger-context model' % per_request)
            budget = int(os.environ.get('WORKFLOW_CONTEXT_BUDGET_TOKENS', '200000'))
            if per_request > budget and not self._budget_steered:
                self._budget_steered = True
                self.context_budget_hit = per_request

    def text(self, text):
        if not text:
            return
        self.timing.response()
        self.answer += text
        print(json.dumps({'type':'assistant', 'uncle_timing_native':True, 'uncle_chat_output':bool(os.environ.get('UNCLE_STATUS_FILE')), 'message':{'content':[{'type':'text','text':text}]}}), flush=True)
        self.status('chat_output', text=text)

    def completed_answer(self, text, response_id=None, phase=None):
        if phase in ('commentary', 'final_answer'):
            self.phased_answers = True
        if phase == 'commentary':
            return
        if phase == 'final_answer':
            self.explicit_final_answer = text
        self.final_answer = text
        self.responded(response_id)
        if self.side != 'reviewer' or self.stage != 'plan-executability':
            return
        # A later steering reply must not overwrite a completed assessment.
        # Only accept a whole message, never JSON fragments from streamed prose.
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            return
        if isinstance(value, dict) and all(key in value for key in
                                           ('version', 'input_digest', 'verdict')):
            self.assessment_answer = text

    def output_answer(self):
        if self.side == 'reviewer' and self.stage == 'plan-executability' and self.assessment_answer:
            # The workflow still validates the full schema, digest and evidence.
            return self.assessment_answer
        if self.side == 'reviewer' and getattr(self, 'phased_answers', False):
            return getattr(self, 'explicit_final_answer', '')
        return getattr(self, 'explicit_final_answer', '') or self.final_answer or self.answer

    def watch_parent(self):
        # Windows supervisors own descendants through a Job Object. On POSIX,
        # cancel the native session if its owning workflow shell disappears.
        if os.name == 'nt':
            return

        def watch():
            while not self.parent_watch_stop.wait(.1):
                if self.parent_pid == 1 or os.getppid() != self.parent_pid:
                    self.parent_lost = True
                    os.kill(os.getpid(), signal.SIGTERM)
                    return

        threading.Thread(target=watch, daemon=True).start()

    def spawn(self, command, env=None):
        command = launch_command(command)
        owner = os.environ.get('UNCLE_RUNNER_POOL_OWNER_PID', '')
        if owner and os.environ.get('UNCLE_RUNNER_REUSE', '1') != '0':
            pool = Path(os.getcwd()) / '.uncle' / 'workflow' / 'runner-pool'
            command = [sys.executable, '-B', str(Path(__file__).with_name('runner_pool.py')),
                       'connect', '--root', str(pool), '--owner', owner,
                       '--runner', self.runner, '--side', self.side, '--', *command]
            self.pooled = True
            self.status('runner_pool', owner=int(owner), pool=str(pool))
        self.child = timed_popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=sys.stderr, text=True, encoding='utf-8', bufsize=1,
                                      env=env or self.env, **group_options())
        def read():
            try:
                for line in self.child.stdout:
                    try:
                        value = json.loads(line)
                        if value.get('type') == 'runner_pool':
                            self.status('runner_reused' if value.get('reused') else 'runner_started',
                                        pool_pid=value.get('pool_pid'))
                            continue
                        self.read_cache.observe(value)
                        self.timing.observe(value)
                        self.events.put(value)
                    except ValueError:
                        continue
            finally:
                self.events.put({'_eof':True})
        threading.Thread(target=read, daemon=True).start()

    def send(self, message):
        self.child.stdin.write(json.dumps(message) + '\n')
        self.child.stdin.flush()

    def rpc(self, method, params, id=None):
        id = id or uuid.uuid4().hex
        self.send(dict(jsonrpc='2.0', id=id, method=method, params=params))
        return id

    def wait(self, id):
        deadline = time.monotonic()+60
        deferred = []
        try:
            while time.monotonic()<deadline:
                event = self.events.get(timeout=max(.1, deadline-time.monotonic()))
                if event.get('_eof'):
                    raise ValueError('Native runner exited during initialization')
                if event.get('id') == id:
                    if 'error' in event:
                        raise ValueError(str(event['error']))
                    return event.get('result', {})
                deferred.append(event)
            raise ValueError('Native runner initialization timed out')
        finally:
            for event in deferred:
                self.events.put(event)

    def ready(self, directory):
        self.channel = Path(directory)/'inbox'
        self.channel.mkdir()
        self.status('steering_ready', channel=str(self.channel), session=self.session, turn=self.turn)
        if self.note:
            # The prompt carrying a supervisor note has been submitted to the runner.
            self.status('note_received', note=self.note)

    def submitted(self, id):
        self.turns.append(id)

    def responded(self, response_id=None):
        # A completed response answers the input at the head of the submission
        # order, and only when that input was steering the runner accepted.
        # Acceptance alone never counts as an answer; without a turn-ordered
        # runner nothing is answered here (see `answered`).
        if self.correlation != 'turn' or not self.turns:
            return
        head = self.turns.pop(0)
        if head in self.accepted:
            self.accepted.discard(head)
            self.status('steering_answered', message_id=head, response_id=response_id)

    def answered(self, id, response_id=None):
        # A runner that names the input a response belongs to (correlation 'message').
        if id in self.accepted:
            self.accepted.discard(id)
            self.status('steering_answered', message_id=id, response_id=response_id)

    def incoming(self, steer):
        if not self.channel:
            return
        for path in sorted(self.channel.glob('*.json')):
            try:
                if path.stat().st_size > 1024*1024:
                    raise ValueError('Steering message too large')
                data = json.loads(path.read_text())
                if not isinstance(data.get('text'), str) or not data['text'].strip():
                    raise ValueError('Empty steering message')
                id = data['id']
                steer(data['text'], id)
            except (OSError, ValueError, KeyError) as exc:
                self.status('steering_rejected', message_id=path.stem, detail=str(exc))
            finally:
                path.unlink(missing_ok=True)

    def ack(self, event):
        id = event.get('id')
        if id not in self.pending:
            return False
        self.pending.pop(id)
        if 'error' not in event:
            self.accepted.add(id)
            self.status('steering_accepted', message_id=id, detail='', correlation=self.correlation)
        else:
            if id in self.turns: self.turns.remove(id)
            self.status('steering_rejected', message_id=id, detail=str(event.get('error', '')))
        return True

    def loop(self, handler, steer):
        seconds = int(os.environ.get('WORKFLOW_NATIVE_STAGE_SECONDS', '3600'))
        while time.monotonic()-self.started < seconds:
            self.incoming(steer)
            if self.context_budget_hit:
                hit, self.context_budget_hit = self.context_budget_hit, 0
                steer(CONTEXT_BUDGET_NOTE % hit, 'context-budget')
            try:
                event = self.events.get(timeout=.1)
            except queue.Empty:
                continue
            if self.ack(event):
                continue
            if event.get('_eof'):
                raise ValueError('Native runner disconnected before completing the stage')
            if handler(event):
                return
        raise ValueError('Native stage exceeded its time limit')

    def codex(self, directory):
        command = [os.environ.get('WORKFLOW_CODEX_CMD','codex'), 'app-server', '--listen', 'stdio://']
        for i, arg in enumerate(self.args[:-1]):
            if arg == '-c': command += ['-c', self.args[i+1]]
        self.spawn(command)
        self.wait(self.rpc('initialize', {'clientInfo':{'name':'uncle','version':'1.0'}}))
        self.send({'method':'initialized'})
        params = {'cwd':os.getcwd(), 'approvalPolicy':'never',
                  'sandbox':'workspace-write' if self.side=='agent' else 'read-only', 'ephemeral':True}
        if self.model: params['model']=self.model
        result=self.wait(self.rpc('thread/start',params))
        self.session=result['thread']['id']
        self.model=result.get('model',self.model)
        params={'threadId':self.session,'input':[{'type':'text','text':self.prompt}], 'effort':self.effort}
        result=self.wait(self.rpc('turn/start',params))
        self.turn=result['turn']['id']
        self.ready(directory)
        def steer(text,id):
            self.pending[id]=True
            self.rpc('turn/steer',{'threadId':self.session,'expectedTurnId':self.turn,
                                 'input':[{'type':'text','text':text}]},id)
        def handle(event):
            method,p=event.get('method'),event.get('params',{})
            if method=='item/agentMessage/delta': self.text(p.get('delta',''))
            if method=='item/completed' and p.get('item',{}).get('type')=='agentMessage':
                self.completed_answer(p['item'].get('text',''),p['item'].get('id'),p['item'].get('phase'))
            if method=='thread/tokenUsage/updated':
                u=p.get('tokenUsage',{}).get('total',{})
                self.tokens(dict(input_tokens=u.get('inputTokens'),output_tokens=u.get('outputTokens'),
                                 cache_read_input_tokens=u.get('cachedInputTokens')))
            if method=='model/rerouted': self.model=p.get('toModel',self.model)
            if method=='turn/completed' and p.get('turn',{}).get('id')==self.turn:
                if p['turn'].get('status')!='completed': raise ValueError(str(p['turn'].get('error') or p['turn']['status']))
                return True
            if 'id' in event and method:
                self.send({'id':event['id'],'error':{'code':-32601,'message':'Unsupported stage request'}})
        self.loop(handle,steer)

    def kimi(self, directory):
        help_text=subprocess.run([os.environ.get('WORKFLOW_KIMI_CMD','kimi'),'--help'],
                                 capture_output=True,text=True,timeout=15).stdout
        if '--wire' not in help_text:
            from native_kimi import run
            return run(self,directory)
        model = self.model
        if model.startswith('kimi:'): model=model[5:]
        elif model=='kimi': model=os.environ.get('WORKFLOW_KIMI_MODEL','moonshot-ai/kimi-k2.7-code-highspeed')
        command=[os.environ.get('WORKFLOW_KIMI_CMD','kimi'),'--wire','--yolo']
        if model: command+=['--model',model]
        if self.side=='reviewer':
            command+=['--agent-file',str(Path(__file__).resolve().parents[2]/'lib/kimi/reviewer.md')]
        self.spawn(command)
        self.wait(self.rpc('initialize',{'protocol_version':'1.4','client':{'name':'uncle'}}))
        self.turn=self.rpc('prompt',{'user_input':self.prompt})
        self.ready(directory)
        steps={}
        step=0
        def steer(text,id):
            self.pending[id]=True
            self.rpc('steer',{'user_input':text},id)
        def handle(event):
            nonlocal step
            if event.get('id')==self.turn:
                if event.get('result',{}).get('status')!='finished': raise ValueError(str(event.get('error') or event.get('result')))
                return True
            if event.get('method')=='event':
                e=event.get('params',{}); p=e.get('payload',{})
                if e.get('type')=='StepBegin':
                    step=p.get('n',step+1)
                    self.final_answer=''
                if e.get('type')=='ContentPart' and p.get('type')=='text':
                    self.text(p.get('text',''));self.final_answer+=p.get('text','')
                if e.get('type')=='StatusUpdate' and p.get('token_usage'):
                    u=p['token_usage'];steps[p.get('message_id') or step]=dict(input_tokens=u.get('input_other',0),
                        output_tokens=u.get('output',0),cache_read_input_tokens=u.get('input_cache_read',0),
                        cache_creation_input_tokens=u.get('input_cache_creation',0))
                    self.tokens({k:sum(v.get(k,0) for v in steps.values()) for k in KEYS},inclusive=False)
        self.loop(handle,steer)

    def claude(self, directory):
        args=list(self.args)
        # Existing driver flags, including budgets, tools and session reuse, stay intact.
        if self.side=='reviewer':
            args=['-p','--output-format','stream-json','--verbose','--allowedTools','Read,Glob,Grep',
                  '--strict-mcp-config']
            if self.model: args+=['--model',self.model]
            if self.effort: args+=['--effort',self.effort]
        args+=['--input-format','stream-json','--replay-user-messages']
        self.spawn([os.environ.get('WORKFLOW_CLAUDE_CMD','claude')]+args)
        def message(text,id):
            self.send({'type':'user','uuid':id,'session_id':self.session or '',
                       'message':{'role':'user','content':text}})
        self.correlation='turn'
        first=uuid.uuid4().hex
        self.submitted(first)
        message(self.prompt,first)
        outstanding = 1
        completed_usage = dict.fromkeys(KEYS, 0)
        live_usage = {}
        self.ready(directory)
        def steer(text,id):
            self.pending[id]=True
            self.submitted(id)
            message(text,id)
        def handle(e):
            nonlocal outstanding
            if e.get('type')=='system': self.session=e.get('session_id',self.session)
            if e.get('type')=='user' and e.get('uuid') in self.pending:
                self.ack({'id':e['uuid'],'result':{}})
            if e.get('type')=='assistant':
                message_usage=e.get('message',{}).get('usage')
                message_id=e.get('message',{}).get('id')
                if message_usage and message_id:
                    live_usage[message_id]=message_usage
                    self.tokens({k:completed_usage[k]+sum(u.get(k,0) or 0 for u in live_usage.values()) for k in KEYS},inclusive=False)
                self.final_answer=''
                for part in e.get('message',{}).get('content',[]):
                    if part.get('type')=='text':
                        self.text(part['text']);self.final_answer+=part['text']
            if e.get('type')=='result':
                for key in KEYS:
                    completed_usage[key] += (e.get('usage') or {}).get(key,0) or 0
                live_usage.clear()
                self.tokens(completed_usage,e.get('total_cost_usd'),inclusive=False)
                if e.get('is_error'):
                    # Claude sometimes returns the unusable detail "success"
                    # for an account/session-limit refusal, while its final
                    # assistant message contains the actionable reason. Never
                    # surface that as a mysterious successful implementation
                    # failure or hand it to the supervisor as such.
                    detail = e.get('error_detail') or e.get('errors')
                    if not detail or str(detail).strip().lower() == 'success':
                        detail = self.final_answer or e.get('subtype')
                    raise ValueError(str(detail))
                self.responded(e.get('uuid') or e.get('session_id'))
                outstanding -= 1
                return outstanding <= 0 and not self.pending
        self.loop(handle,steer)

    def cline(self, directory):
        binary=Path(shutil.which(os.environ.get('WORKFLOW_CLINE_CMD','cline')) or '').resolve()
        sdk=None
        for parent in binary.parents:
            candidate=parent/'node_modules/@cline/sdk/dist/index.js'
            if candidate.is_file(): sdk=candidate;break
        if sdk is None: raise ValueError('Installed Cline SDK not found; install the current npm Cline package')
        self.spawn([shutil.which('node') or 'node',str(Path(__file__).with_name('cline-native.mjs')),str(sdk)])
        self.rpc('start',{'prompt':self.prompt,'model':self.model,'effort':self.effort,'cwd':os.getcwd(),
                          'mode':'act' if self.side=='agent' else 'plan',
                          'turns':int(self.option('--max-turns') or 80)},'start')
        def steer(text,id):
            self.pending[id]=True
            self.rpc('steer',{'text':text},id)
        def handle(e):
            if e.get('method')=='ready':
                self.session=e['params']['sessionId'];self.ready(directory)
            if e.get('method')=='agent_event':
                p=e['params']
                if p.get('type')=='content_end' and p.get('contentType')=='text':
                    self.text(p.get('text',''));self.completed_answer(p.get('text',''),p.get('id'))
                if p.get('type')=='error':
                    self.status('chat_output',text='Cline: '+str(p.get('message') or p.get('error') or 'runner error'))
                if p.get('type')=='usage': self.tokens(dict(input_tokens=p.get('totalInputTokens'),output_tokens=p.get('totalOutputTokens'),
                    cache_read_input_tokens=p.get('totalCacheReadTokens'),cache_creation_input_tokens=p.get('totalCacheWriteTokens')),p.get('totalCost'))
            if e.get('id')=='start':
                if 'error' in e: raise ValueError(str(e['error']))
                r=e.get('result',{});u=r.get('usage',{})
                if r.get('text'):
                    self.final_answer=r['text']
                    if not self.answer: self.text(r['text'])
                if u: self.tokens(dict(input_tokens=u.get('inputTokens'),output_tokens=u.get('outputTokens'),
                    cache_read_input_tokens=u.get('cacheReadTokens'),cache_creation_input_tokens=u.get('cacheWriteTokens')),u.get('totalCost'))
                if r.get('finishReason')!='completed': raise ValueError('Cline stage did not complete: '+str(r.get('text') or r.get('finishReason')))
                return True
        self.loop(handle,steer)

    def run(self):
        def interrupted(*_): raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,interrupted)
        if hasattr(signal,'SIGBREAK'): signal.signal(signal.SIGBREAK,interrupted)
        self.status('start', stage_index=int(os.environ.get('UNCLE_STATUS_STAGE_INDEX','0')),
                    stage_total=int(os.environ.get('UNCLE_STATUS_STAGE_TOTAL','0')))
        self.watch_parent()
        success=False
        error=''
        with tempfile.TemporaryDirectory(prefix='uncle-native-') as directory:
            try:
                if self.runner=='self-hosted':
                    from native_opencode import run
                    run(self,directory)
                else:
                    getattr(self,self.runner)(directory)
                success=True
                if self.output:
                    Path(self.output).write_text(self.output_answer(),encoding='utf-8')
            except (OSError,ValueError,KeyError,TypeError,queue.Empty,KeyboardInterrupt) as exc:
                error='Workflow parent exited; native stage cancelled' if self.parent_lost else str(exc) or 'Stage interrupted'
            finally:
                self.timing.finish()
                self.parent_watch_stop.set()
                if self.channel:
                    self.status('steering_closed',channel=str(self.channel))
                    for path in self.channel.glob('*.json'):
                        self.status('steering_rejected',message_id=path.stem,detail='Stage completed before delivery')
                for id in self.pending:
                    self.status('steering_rejected',message_id=id,detail='Stage ended before acknowledgment')
                for id in sorted(self.accepted):
                    self.status('steering_unconfirmed',message_id=id,detail='Stage ended without a correlated reply')
                if self.child is not None:
                    if self.child.poll() is None:
                        if self.pooled:
                            self.child.terminate()
                        else:
                            kill_tree(self.child)
                        self.child.wait()
                    finish_check(self.child)
        result=dict(type='result',uncle_timing_native=True,subtype='success' if success else 'error_during_execution',is_error=not success,
            error_detail=error,usage=self.usage,total_cost_usd=self.cost,input_includes_cache=self.inclusive,
            num_turns=1,duration_ms=int((time.monotonic()-self.started)*1000))
        print(json.dumps(result),flush=True)
        return 0 if success else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--runner',required=True,choices=['codex','claude','kimi','cline','self-hosted'])
    parser.add_argument('--side',required=True,choices=['agent','reviewer'])
    parser.add_argument('--stage',required=True)
    parser.add_argument('args',nargs=argparse.REMAINDER)
    opts=parser.parse_args()
    args=opts.args[1:] if opts.args[:1]==['--'] else opts.args
    sys.exit(Stage(opts.runner,opts.side,opts.stage,args).run())
