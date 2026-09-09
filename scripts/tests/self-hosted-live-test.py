#!/usr/bin/env python3
"""Optional integration test: installed Aider, loopback server, no external networking."""
import http.server, json, os, pathlib, sys, tempfile, threading
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts/lib'))
from self_hosted import run_aider
calls=[]
mode="reviewer"
class Server(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        calls.append((self.path,body['model'],self.headers.get('Authorization')=='Bearer dummy-local-key'))
        payload={'id':'test','object':'chat.completion','model':'local-test','choices':[{'index':0,'message':{'role':'assistant','content':('## Findings\n\nREADY' if mode=='reviewer' else 'GENERATED.md\n```\n# Created by the local fixture\n```')},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
        data=json.dumps(payload).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Server)
threading.Thread(target=server.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory(prefix='uncle-aider-local-test-') as tmp:
    root=pathlib.Path(tmp).resolve();guard=root/'guard';guard.mkdir();workspace=root/'project';workspace.mkdir()
    (workspace/'README.md').write_text('Local fixture for reviewer test.\n')
    (guard/'sitecustomize.py').write_text('''import socket
original_connect=socket.socket.connect
original_connect_ex=socket.socket.connect_ex
original_getaddrinfo=socket.getaddrinfo
def check(address):
    if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):
        raise OSError('Non-loopback networking disabled for this test')
def connect(self,address):
    check(address); return original_connect(self,address)
def connect_ex(self,address):
    check(address); return original_connect_ex(self,address)
def getaddrinfo(host,*args,**kwargs):
    if host not in ('127.0.0.1','::1','localhost',None): raise OSError('Non-loopback DNS disabled for this test')
    return original_getaddrinfo(host,*args,**kwargs)
socket.socket.connect=connect
socket.socket.connect_ex=connect_ex
socket.getaddrinfo=getaddrinfo
''')
    os.environ['PYTHONPATH']=str(guard)
    os.environ['WORKFLOW_SELF_HOSTED_SECONDS']='30'
    os.environ['NO_PROXY']='127.0.0.1,localhost,::1'
    values={'base_url':f'http://127.0.0.1:{server.server_port}/v1','api_key':'dummy-local-key','model':'local-test'}
    try:
        answer,turns=run_aider('reviewer',values,'Return a Findings heading and READY.',workspace)
        assert answer=='## Findings\n\nREADY',repr(answer)
        assert calls and all(path=='/v1/chat/completions' and model=='local-test' and auth for path,model,auth in calls),calls
        mode='agent'
        answer,turns=run_aider('agent',values,'Create GENERATED.md containing exactly: # Created by the local fixture',workspace)
        assert (workspace/'GENERATED.md').read_text().strip()=='# Created by the local fixture'
        assert all(path=='/v1/chat/completions' and model=='local-test' and auth for path,model,auth in calls),calls
        print('Aider local-only integration passed: endpoint, model, auth, reviewer Markdown and agent file editing verified.')
    finally:
        server.shutdown()
