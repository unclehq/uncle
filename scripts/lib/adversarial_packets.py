#!/usr/bin/env python3
import json,sys
from pathlib import Path
def main(project='.'):
 p=Path(project); state=p/'.uncle/workflow/documents'; source=json.loads((state/'ADVERSARIAL_REVIEW_WORKERS.json').read_text())
 findings=[]
 for x in source.get('findings',[]):
  summary='; '.join(x.get('summaries',[])); evidence='; '.join(x.get('evidence',[]))
  findings.append({'id':x['id'],'title':summary or x['id'],'severity':'MEDIUM','references':evidence or 'Worker evidence not stated','failure':summary or 'Review finding recorded.','fix':'Resolve the recorded finding in the plan or implementation.','verify':'Re-run the affected verification.'})
 payload={'schema':'uncle.artifact/v1','kind':'adversarial-review','findings':findings,'overall_assessment':'Review findings require disposition.' if findings else 'No findings.'}
 (state/'ADVERSARIAL_REVIEW.json').write_text(json.dumps(payload,indent=2)+'\n')
 import importlib.util
 s=importlib.util.spec_from_file_location('artifact_json',Path(__file__).with_name('artifact_json.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 (p/'.uncle/docs/ADVERSARIAL_REVIEW.md').write_text(m.render_adversarial(payload))
if __name__=='__main__': main(sys.argv[1] if len(sys.argv)>1 else '.')
