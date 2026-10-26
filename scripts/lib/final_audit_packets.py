#!/usr/bin/env python3
"""Render a final audit deterministically from collated specialist findings."""
import json,sys
from pathlib import Path
def main(project='.'):
 p=Path(project); state=p/'.uncle/workflow/documents'; source=json.loads((state/'FINAL_AUDIT_WORKERS.json').read_text())
 findings=[]
 rank={'critical':0,'high':1,'medium':2,'low':3}
 for item in source.get('findings',[]):
  evidence='; '.join(item.get('evidence',[])) or '; '.join(item.get('summaries',[]))
  stated=[v for v in item.get('severities',[]) if v in rank]
  # A worker that states a severity is believed: Critical and High block release, Medium and Low
  # are recorded and do not.  One that states nothing keeps the old conservative reading
  # (a blocking MEDIUM), so a prompt or model that omits the field never lets a finding slide.
  severity=min(stated,key=rank.get) if stated else 'medium'
  blocks='NO' if stated and rank[severity]>=2 else 'YES'
  findings.append({'id':item['id'],'severity':severity.upper(),'evidence':evidence,'affected_requirement':'Not stated','required_correction':'; '.join(item.get('summaries',[])) or 'Investigate the recorded finding.','blocks':blocks})
 blocking=[f for f in findings if f['blocks']=='YES']
 verdict='NOT READY' if blocking else ('READY WITH NON-BLOCKING ISSUES' if findings else 'READY')
 payload={'schema':'uncle.artifact/v1','kind':'final-audit','findings':findings,'verdict':verdict}
 (state/'FINAL_AUDIT.json').write_text(json.dumps(payload,indent=2)+'\n')
 import importlib.util
 s=importlib.util.spec_from_file_location('artifact_json',Path(__file__).with_name('artifact_json.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 (p/'.uncle/docs/FINAL_AUDIT.md').write_text(m.render_final_audit(payload))
if __name__=='__main__': main(sys.argv[1] if len(sys.argv)>1 else '.')
