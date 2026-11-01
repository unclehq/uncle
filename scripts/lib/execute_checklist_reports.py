#!/usr/bin/env python3
"""Render authoritative checklist reports directly from collated worker JSON."""
import json, sys
from pathlib import Path

def main(project='.', empty=False):
 p=Path(project); docs=p/'.uncle/docs'; state=p/'.uncle/workflow/documents'
 workers={'results': []} if empty else json.loads((state/'EXECUTE_CHECKLIST_WORKERS.json').read_text())
 checklist=json.loads((state/'MANUAL_CHECKLIST.json').read_text())
 checks=checklist.get('checks')
 if not isinstance(checks,list):
  raise ValueError('Canonical checklist must contain an explicit checks list')
 required={c['id']:bool(c.get('required',True)) for c in checks}
 rows=[]
 for r in workers['results']:
  rows.append({'id':r['id'],'required':required.get(r['id'],True),'status':r['status'],'evidence':r['evidence'],'action':r['action'],'expected_result':r['expected_result'],'actual_result':r['actual_result'],'defect_ids':[r['defect_reference']] if r.get('defect_reference') else []})
 observed={r['id'] for r in rows}
 for c in checks:
  if c['id'] not in observed:
   rows.append({'id':c['id'],'required':required[c['id']],'status':'NOT RUN',
    'evidence':'No worker observation was supplied for this checklist item.',
    'action':c.get('exact_action',''),'expected_result':c.get('expected_result',''),
    'actual_result':'Not performed.','defect_ids':[]})
 if not any(required.values()):
  scope_id='CHECKLIST-SCOPE'
  while scope_id in required: scope_id+='-EMPTY'
  rows.append({'id':scope_id,'required':True,'status':'PASS',
   'evidence':'.uncle/workflow/documents/MANUAL_CHECKLIST.json contains zero required checks; optional observations remain NOT RUN unless supplied.',
   'action':'Inspect the canonical checklist for required checks.',
   'expected_result':'No required checklist work remains uncovered.',
   'actual_result':'Zero required checks are declared.','defect_ids':[]})
 payload={'schema':'uncle.artifact/v1','kind':'execute-checklist','results':rows}
 (state/'EXECUTE_CHECKLIST.json').write_text(json.dumps(payload,indent=2)+'\n')
 # VERIFICATION_REPORT is the canonical acceptance-routing artifact. Keep it
 # beside the richer execution packet so shared gates never need Markdown.
 verification={'schema':'uncle.artifact/v1','kind':'acceptance-report','rows':[
  {'id':r['id'],'required':r['required'],'status':r['status'],'evidence':r['evidence']} for r in rows]}
 (state/'VERIFICATION_REPORT.json').write_text(json.dumps(verification,indent=2)+'\n')
 blockers=[r for r in rows if r['status'] != 'PASS']
 defects={'schema':'uncle.artifact/v1','kind':'defects','defects':[
  {'id':(r.get('defect_ids') or [r['id']])[0],'status':r['status'],'evidence':r['evidence'],
   'expected_result':r.get('expected_result',''),'actual_result':r.get('actual_result','')} for r in blockers]}
 (state/'DEFECTS.json').write_text(json.dumps(defects,indent=2)+'\n')
 import importlib.util
 s=importlib.util.spec_from_file_location('fallback',Path(__file__).with_name('checklist_report_fallback.py')); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.render_from_json(p)
if __name__=='__main__':
 args=sys.argv[1:]
 empty='--empty' in args
 args=[arg for arg in args if arg != '--empty']
 main(args[0] if args else '.', empty)
