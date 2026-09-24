#!/usr/bin/env python3
"""Render authoritative checklist reports directly from collated worker JSON."""
import json, sys
from pathlib import Path

def main(project='.'):
 p=Path(project); docs=p/'.uncle/docs'; state=p/'.uncle/workflow/documents'
 workers=json.loads((state/'EXECUTE_CHECKLIST_WORKERS.json').read_text())
 checklist=json.loads((state/'MANUAL_CHECKLIST.json').read_text())
 required={c['id']:bool(c.get('required',True)) for c in checklist.get('checks',[])}
 rows=[]
 for r in workers['results']:
  rows.append({'id':r['id'],'required':required.get(r['id'],True),'status':r['status'],'evidence':r['evidence'],'action':r['action'],'expected_result':r['expected_result'],'actual_result':r['actual_result'],'defect_ids':[r['defect_reference']] if r.get('defect_reference') else []})
 payload={'schema':'uncle.artifact/v1','kind':'execute-checklist','results':rows}
 (state/'EXECUTE_CHECKLIST.json').write_text(json.dumps(payload,indent=2)+'\n')
 import importlib.util
 s=importlib.util.spec_from_file_location('fallback',Path(__file__).with_name('checklist_report_fallback.py')); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.render_from_json(p)
if __name__=='__main__': main(sys.argv[1] if len(sys.argv)>1 else '.')
