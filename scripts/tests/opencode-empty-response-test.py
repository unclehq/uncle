import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import native_opencode as native

class EmptyResponse(unittest.TestCase):
    def run_case(self, recover):
        stage=Mock();stage.stage='execute-checklist';stage.side='agent';stage.prompt='task'
        stage.option.return_value=None
        child=Mock();child.poll.return_value=None
        posts=[]
        def urlopen(req, **kwargs):
            path=req.full_url.split('/session',1)
            if req.full_url.endswith('/global/health'): value={}
            elif req.full_url.endswith('/session'): value={'id':'s'}
            elif req.full_url.endswith('/prompt_async'):
                posts.append(req.data);value=None
            elif req.full_url.endswith('/session/status'):value={}
            else:
                n=len(posts)
                parts=[{'type':'text','id':'p','text':'Completed report'}] if recover and n>1 else [{'type':'reasoning','text':'not an answer'}]
                value=[{'info':{'id':f'u{n}','role':'user'}},
                       {'info':{'id':f'a{n}','role':'assistant','parentID':f'u{n}',
                                'time':{'completed':1},'tokens':{'input':100,'output':20}},'parts':parts}]
            import json
            response=Mock();response.read.return_value=json.dumps(value).encode()
            cm=Mock();cm.__enter__=Mock(return_value=response);cm.__exit__=Mock(return_value=False)
            return cm
        with tempfile.TemporaryDirectory() as d, patch.object(native,'opencode_invocation',return_value=([],{})), \
             patch.object(native if hasattr(native, 'timed_popen') else native.subprocess, 'timed_popen' if hasattr(native, 'timed_popen') else 'Popen', return_value=child),patch.object(native,'launch_command',side_effect=lambda c:c), \
             patch.object(native.urllib.request,'urlopen',side_effect=urlopen):
            if recover:
                native.run(stage,d,values={'model':'test'},root=d)
                self.assertEqual(stage.final_answer,'Completed report')
            else:
                with self.assertRaisesRegex(ValueError,'after one same-session recovery'):
                    native.run(stage,d,values={'model':'test'},root=d)
            self.assertEqual(len(posts),2)
    def test_recovers_in_same_session(self): self.run_case(True)
    def test_empty_retry_stops(self): self.run_case(False)

if __name__=='__main__':unittest.main()
