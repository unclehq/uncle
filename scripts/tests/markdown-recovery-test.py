import json,subprocess,sys,tempfile,unittest
from pathlib import Path
GUARD=Path(__file__).resolve().parents[1]/'lib/triage_guard.py'
class Markdown(unittest.TestCase):
 def test_diagnosis_markdown_and_workflow_state_apply(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'project';root.mkdir();install=Path(d)/'install';install.mkdir()
   state=root/'.uncle/workflow';state.mkdir(parents=True)
   (state/'state').write_text('WAIT')
   (root/'FINAL_AUDIT.md').write_text('original')
   args=[sys.executable,str(GUARD),'--state-dir',str(state),'--project',str(root),'--root',str(install),'--turn','1','--mode','diagnosis']
   info=json.loads(subprocess.check_output(args+['begin']))
   sandbox=Path(info['sandbox']);(sandbox/'FINAL_AUDIT.md').write_text('corrected')
   (sandbox/'.uncle/workflow/state').write_text('COMPLETE')
   result=json.loads(subprocess.check_output(args+['end','--digest',info['digest']]))
   self.assertIn('FINAL_AUDIT.md',result['applied'])
   self.assertEqual((root/'FINAL_AUDIT.md').read_text(),'corrected')
   self.assertEqual((state/'state').read_text(),'COMPLETE')
   self.assertIn('.uncle/workflow/state',result['applied'])
if __name__=='__main__':unittest.main()
