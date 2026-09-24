#!/usr/bin/env python3
"""Render a final audit deterministically from collated specialist findings."""
import json,sys
from pathlib import Path
def main(project='.'):
 p=Path(project); state=p/'.uncle/workflow/documents'; source=json.loads((state/'FINAL_AUDIT_WORKERS.json').read_text())
 findings=[]
 for item in source.get('findings',[]):
  evidence='; '.join(item.get('evidence',[])) or '; '.join(item.get('summaries',[]))
  findings.append({'id':item['id'],'severity':'MEDIUM','evidence':evidence,'affected_requirement':'Not stated','required_correction':'; '.join(item.get('summaries',[])) or 'Investigate the recorded finding.','blocks':'YES'})
 payload={'schema':'uncle.artifact/v1','kind':'final-audit','findings':findings,'verdict':'NOT READY' if findings else 'READY'}
 (state/'FINAL_AUDIT.json').write_text(json.dumps(payload,indent=2)+'\n')
 import importlib.util
 s=importlib.util.spec_from_file_location('artifact_json',Path(__file__).with_name('artifact_json.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 (p/'.uncle/docs/FINAL_AUDIT.md').write_text(m.render_final_audit(payload))
if __name__=='__main__': main(sys.argv[1] if len(sys.argv)>1 else '.')
