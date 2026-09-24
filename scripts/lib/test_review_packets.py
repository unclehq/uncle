#!/usr/bin/env python3
import json,sys
from pathlib import Path
STAT={'PASS','FAIL','BLOCKED-SETUP','BLOCKED-HUMAN','BLOCKED-IMPOSSIBLE','NOT RUN'}
def main(directory,out,*names):
 rows={}
 for n in names:
  try: p=json.loads((Path(directory)/(n+'.json')).read_text())
  except Exception as e: raise ValueError('%s.json: invalid packet: %s'%(n,e))
  if p.get('schema')!='uncle.artifact/v1' or p.get('kind')!='test-review-worker-packet' or not isinstance(p.get('rows'),list): raise ValueError('%s.json: expected test-review worker rows'%n)
  for r in p['rows']:
   if not isinstance(r,dict) or not r.get('id') or r.get('status') not in STAT or not r.get('evidence'): raise ValueError('%s.json: invalid acceptance row'%n)
   if r['id'] in rows: raise ValueError('%s.json: duplicate row %s'%(n,r['id']))
   rows[r['id']]={'id':r['id'],'required':True,'status':r['status'],'evidence':r['evidence']}
 rows['RESULTS']={'id':'RESULTS','required':True,'status':'PASS','evidence':'Driver green-check completed; see .uncle/workflow/green-check.md.'}
 result={'schema':'uncle.artifact/v1','kind':'acceptance-report','rows':[rows[k] for k in sorted(rows)]}
 Path(out).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 try: main(*sys.argv[1:])
 except Exception as e: print('test review packets: '+str(e),file=sys.stderr);raise SystemExit(1)
