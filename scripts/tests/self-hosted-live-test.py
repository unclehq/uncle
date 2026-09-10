#!/usr/bin/env python3
"""Optional integration: real OpenCode with a loopback OpenAI-compatible fixture."""
import http.server
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts/lib'))
from self_hosted import run_opencode

calls = []
response_text = '## Findings\n\nREADY'
phase = 'reviewer'
edit_requested = False
edit_path = ''
class Server(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        global edit_requested
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        calls.append((self.path, body['model'], self.headers.get('Authorization')))
        assert self.path == '/v1/chat/completions'
        assert body['model'] == 'local-test'
        assert self.headers.get('Authorization') == 'Bearer dummy-local-key'
        data = {'id':'fixture','object':'chat.completion','created':0,'model':'local-test',
                'choices':[{'index':0,'message':{'role':'assistant','content':response_text},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
        tool_names = {tool['function']['name'] for tool in body.get('tools', [])}
        if phase == 'reviewer':
            assert not tool_names.intersection({'write', 'edit', 'apply_patch', 'bash', 'task'}), tool_names
        if phase == 'edit' and not edit_requested and 'write' in tool_names:
            edit_requested = True
            data['choices'][0]['message'] = {'role':'assistant', 'content':None,
                'tool_calls':[{'id':'call_fixture', 'type':'function', 'function':{'name':'write',
                              'arguments':json.dumps({'filePath':edit_path, 'content':'created by OpenCode\n'})}}]}
            data['choices'][0]['finish_reason'] = 'tool_calls'
        if body.get('stream'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            delta = dict(data['choices'][0]['message'])
            if 'tool_calls' in delta:
                delta['tool_calls'][0]['index'] = 0
            chunk = dict(data, object='chat.completion.chunk', choices=[{'index':0,'delta':delta,'finish_reason':None}])
            self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
            chunk['choices'] = [{'index':0,'delta':{},'finish_reason':data['choices'][0]['finish_reason']}]
            self.wfile.write(('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode())
        else:
            raw = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Server)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ['WORKFLOW_SELF_HOSTED_SECONDS'] = '45'
try:
    with tempfile.TemporaryDirectory(prefix='uncle-opencode-live-') as directory:
        root = Path(directory).resolve()
        values = dict(base_url=f'http://127.0.0.1:{server.server_port}/v1', api_key='dummy-local-key',model='local-test')
        for side, stage in [('reviewer',None), ('agent','updated-plan')]:
            phase = side
            if stage:
                response_text = '# Plan\n\n## Verification commands\n```bash\npytest\n```\n\n## Protected verification paths\n```text\ntests/\n```\n'
            usage = {}
            result, turns = run_opencode(side, values, 'Return the requested Markdown document.', root, stage=stage, usage=usage)
            assert result.strip() == response_text.strip(), repr(result)
            assert usage == dict(input_tokens=10,output_tokens=5,total_tokens=15), usage
            assert not (root/'.git').exists()
            if stage:
                assert (root/'UPDATED_PROJECT_PLAN.md').read_text().strip() == response_text.strip()
        phase = 'edit'
        response_text = 'Done.'
        edit_path = str(root/'created.txt')
        usage = {}
        run_opencode('agent', values, 'Create created.txt, then report Done.', root, stage='implementation', usage=usage)
        assert (root/'created.txt').read_text() == 'created by OpenCode\n'
        assert usage['total_tokens'] == 30, usage
        assert calls
        print('OpenCode integration passed: endpoint, model, credentials, JSON, usage, reviewer and plan publication.')
finally:
    server.shutdown()
