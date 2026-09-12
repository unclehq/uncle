"""Kimi Code server transport, using the installed server's REST session API."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.request
from process_tree import launch_command, group_options


def run(stage, directory):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    log_path=Path(directory)/'server.log'
    with log_path.open('w') as log:
        stage.child=subprocess.Popen(launch_command([os.environ.get('WORKFLOW_KIMI_CMD','kimi'),
            'web','--no-open','--host','127.0.0.1','--port',str(port)]),env=stage.env,
            stdout=log,stderr=log,**group_options())
    token=None
    for _ in range(200):
        if stage.child.poll() is not None: raise ValueError('Kimi server exited during startup')
        match=re.search(r'(?:token=|Token:\s*|token:\s*)([A-Za-z0-9_-]+)',log_path.read_text())
        if match: token=match[1];break
        time.sleep(.1)
    if not token: raise ValueError('Kimi server did not provide its authentication token')
    base=f'http://127.0.0.1:{port}/api/v1'
    def request(path, body=None):
        req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=20) as response: result=json.load(response)
        if result.get('code')!=0: raise ValueError(result.get('msg','Kimi request failed'))
        return result.get('data')
    created=request('/sessions',{'metadata':{'cwd':os.getcwd()},'title':'Uncle '+stage.stage})
    session=created['id'];stage.session=session
    path='/sessions/'+session
    config={'thinking':stage.effort,'permission_mode':'auto','plan_mode':stage.side=='reviewer'}
    model=stage.model
    if model.startswith('kimi:'): model=model[5:]
    elif model=='kimi': model=os.environ.get('WORKFLOW_KIMI_MODEL','moonshot-ai/kimi-k2.7-code-highspeed')
    if model:config['model']=model
    if stage.side=='reviewer': config.update(tools=['Read','Glob','Grep'],mcp_servers=[])
    request(path+'/profile',{'agent_config':config})
    def send(text,id=None):
        body={'content':[{'type':'text','text':text}]}
        if id:body['prompt_id']=id
        return request(path+'/prompts',body)
    initial=send(stage.prompt);stage.turn=initial['prompt_id']
    stage.ready(directory)
    def steer(text,id):
        queued=send(text,id)
        if queued['status']=='queued':
            result=request(path+'/prompts:steer',{'prompt_ids':[queued['prompt_id']]})
            if not result.get('steered'):
                raise ValueError('Kimi did not accept steering; the message remains queued in its session')
        stage.status('steering_accepted',message_id=id)
    seen={}
    deadline=time.monotonic()+int(os.environ.get('WORKFLOW_NATIVE_STAGE_SECONDS','3600'))
    while time.monotonic()<deadline:
        stage.incoming(steer)
        snapshot=request(path+'/snapshot')
        info=snapshot['session'];u=info['usage']
        stage.model=info.get('agent_config',{}).get('model') or model
        stage.tokens(dict(input_tokens=u.get('input_tokens'),output_tokens=u.get('output_tokens'),
                          cache_read_input_tokens=u.get('cache_read_tokens'),cache_creation_input_tokens=u.get('cache_creation_tokens')),
                     u.get('total_cost_usd'),inclusive=False)
        # Snapshot messages are newest first; publish in chronological order.
        for msg in reversed(snapshot.get('messages',{}).get('items',[])):
            if msg.get('role')!='assistant':continue
            text=''.join(p.get('text','') for p in msg.get('content',[]) if p.get('type')=='text')
            old=seen.get(msg['id'],'')
            if text.startswith(old):stage.text(text[len(old):])
            seen[msg['id']]=text
            if text:stage.final_answer=text
        prompts=request(path+'/prompts')
        if not info.get('main_turn_active') and not prompts.get('active') and not prompts.get('queued'):
            if info.get('last_turn_reason')!='completed':raise ValueError('Kimi stage '+str(info.get('last_turn_reason')))
            return
        if snapshot.get('pending_approvals') or snapshot.get('pending_questions'):
            raise ValueError('Kimi needs an interactive tool response; inspect the stage log and retry')
        time.sleep(.2)
    raise ValueError('Kimi stage timed out')
