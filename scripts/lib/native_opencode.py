"""OpenCode HTTP session adapter; keeps the same session throughout steering."""
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.request
from self_hosted import settings, opencode_invocation
from process_tree import timed_popen
from process_tree import launch_command, group_options


def run(stage, directory, values=None, root=None, allow_shell=True):
    values=values or settings(os.environ.get('UNCLE_CONFIG',str(Path.cwd()/'.uncle/config')),stage.stage)
    root=root or Path.cwd()
    values.setdefault('max_turns',int(stage.option('--max-turns') or 80))
    _,env=opencode_invocation(stage.side,values,stage.prompt,root,directory,allow_shell=allow_shell)
    # Bind only on loopback. Authentication is private to this stage invocation.
    import secrets, base64
    password=secrets.token_urlsafe(32)
    env['OPENCODE_SERVER_PASSWORD']=password
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    stage.child=timed_popen(launch_command([os.environ.get('WORKFLOW_OPENCODE_CMD','opencode'),
        'serve','--hostname','127.0.0.1','--port',str(port)]),env=env,stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,cwd=root,**group_options())
    base=f'http://127.0.0.1:{port}'
    auth='Basic '+base64.b64encode(('opencode:'+password).encode()).decode()
    def request(path,body=None,method=None):
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(base+path,data=data,method=method,headers={
            'Authorization':auth,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=20) as response:
            raw=response.read()
            return json.loads(raw) if raw else None
    for _ in range(200):
        if stage.child.poll() is not None: raise ValueError('OpenCode server exited during startup')
        try:
            request('/global/health');break
        except OSError: time.sleep(.1)
    else: raise ValueError('OpenCode server startup timed out')
    session=request('/session',{})['id'];stage.session=session
    stage.model=values['model']
    def send(text):
        request('/session/'+session+'/prompt_async',{'model':{'providerID':'local','modelID':values['model']},
                'agent':'uncle','parts':[{'type':'text','text':text}]})
    send(stage.prompt)
    stage.correlation='message'
    stage.ready(directory)
    steered={}  # OpenCode user message id -> steering id, so a reply's parentID names its steering
    def steer(text,id):
        before={m.get('info',{}).get('id') for m in (request('/session/'+session+'/message') or []) if m.get('info',{}).get('role')=='user'}
        send(text)
        for _ in range(50):
            after=[m.get('info',{}).get('id') for m in (request('/session/'+session+'/message') or []) if m.get('info',{}).get('role')=='user']
            new=[m for m in after if m not in before]
            if new: steered[new[-1]]=id; break
            time.sleep(.1)
        stage.pending[id]=True
        stage.ack({'id':id,'result':{}})
    # Read canonical stored messages so repeated polls never double-count usage or text.
    seen_text={}
    timing_seen={}
    started=False
    empty_response_retries=0
    awaiting_new_user=None
    deadline=time.monotonic()+int(os.environ.get('WORKFLOW_SELF_HOSTED_SECONDS','3600'))
    while time.monotonic()<deadline:
        stage.incoming(steer)
        messages=request('/session/'+session+'/message') or []
        totals=dict(input_tokens=0,output_tokens=0,cache_read_input_tokens=0,cache_creation_input_tokens=0)
        cost=0
        last=None
        users=[msg.get('info',{}).get('id') for msg in messages if msg.get('info',{}).get('role')=='user']
        for msg in messages:
            info=msg.get('info',{})
            fingerprint=json.dumps(msg,sort_keys=True)
            if timing_seen.get(info.get('id')) != fingerprint:
                stage.timing.observe({'method':'http/message','params':msg})
                timing_seen[info.get('id')]=fingerprint
            if info.get('role')!='assistant': continue
            started=True;last=info
            if info.get('error'): raise ValueError(str(info['error']))
            if info.get('parentID') in steered and info.get('time',{}).get('completed'):
                stage.answered(steered.pop(info['parentID']),info.get('id'))
            tokens=info.get('tokens',{});cache=tokens.get('cache',{})
            totals['input_tokens']+=tokens.get('input',0)
            totals['output_tokens']+=tokens.get('output',0)+tokens.get('reasoning',0)
            totals['cache_read_input_tokens']+=cache.get('read',0)
            totals['cache_creation_input_tokens']+=cache.get('write',0)
            cost+=info.get('cost',0) or 0
            for part in msg.get('parts',[]):
                if part.get('type')=='text':
                    key=part['id'];text=part.get('text','');old=seen_text.get(key,'')
                    if text.startswith(old): stage.text(text[len(old):])
                    seen_text[key]=text
                    if text:stage.final_answer=text
        if started:
            stage.tokens(totals,cost,inclusive=False)
            statuses=request('/session/status') or {}
            if statuses.get(session,{}).get('type','idle')=='idle' and last and last.get('time',{}).get('completed') and users and last.get('parentID') == users[-1]:
                if awaiting_new_user == users[-1]:
                    time.sleep(.2)
                    continue  # prompt_async may not have persisted the recovery message yet.
                final_parts = [part.get('text', '') for msg in messages
                               if msg.get('info', {}).get('id') == last.get('id')
                               for part in msg.get('parts', []) if part.get('type') == 'text']
                answer = '\n'.join(final_parts).strip()
                if not answer:
                    if empty_response_retries < 1:
                        empty_response_retries += 1
                        awaiting_new_user = users[-1]
                        stage.status('chat_output', text='OpenCode returned no final text; requesting completion once in the same session.')
                        send('Your turn ended without a final text response. Continue from the work already done. '
                             'Do not rerun completed checks just to produce a response. Finish any remaining required '
                             'artifacts, then return the final response required by the original task. If blocked, '
                             'state the blocker explicitly. Do not claim success from reasoning alone.')
                        continue
                    raise ValueError('OpenCode returned no final text after one same-session recovery attempt '
                                     f'(finish={last.get("finish", "unknown")}; '
                                     f'input tokens={totals["input_tokens"]}; output/reasoning tokens={totals["output_tokens"]}). '
                                     'No successful completion recorded; retry or select another model.')
                stage.final_answer=answer
                return
        time.sleep(.2)
    raise ValueError('OpenCode stage timed out')
