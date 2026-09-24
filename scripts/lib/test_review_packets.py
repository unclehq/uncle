#!/usr/bin/env python3
import json,sys
from pathlib import Path
STAT={'PASS','FAIL','BLOCKED-SETUP','BLOCKED-HUMAN','BLOCKED-IMPOSSIBLE','NOT RUN'}
# Prefer the most conservative disposition when a single model repeats a row
# with incompatible conclusions.  A duplicate must never erase the evidence
# that justified the stricter outcome or crash an otherwise usable panel.
SEVERITY={'PASS':0, 'NOT RUN':1, 'BLOCKED-HUMAN':2, 'BLOCKED-SETUP':3,
          'BLOCKED-IMPOSSIBLE':4, 'FAIL':5}
EXPECTED={'coverage':{'COVERAGE'}, 'assertions':{'ASSERTIONS'},
          'oracle':{'ORACLE','NEGATIVE'}}

def normalized_id(identifier):
 return str(identifier).upper()

def packet_valid(path, lens):
 try:
  payload=json.loads(Path(path).read_text())
  if payload.get('schema')!='uncle.artifact/v1' or payload.get('kind')!='test-review-worker-packet': return False
  rows=payload.get('rows')
  if not isinstance(rows,list): return False
  ids={normalized_id(row.get('id')) for row in rows if isinstance(row,dict)}
  return EXPECTED.get(lens,set()).issubset(ids) and all(isinstance(row,dict) and row.get('status') in STAT and row.get('evidence') for row in rows)
 except Exception: return False

def merge_row(rows, row, source):
 existing=rows.get(row['id'])
 candidate={'id':row['id'],'required':True,'status':row['status'],
            'evidence':'[%s] %s'%(source,row['evidence'])}
 if existing is None:
  rows[row['id']]=candidate
  return
 # Preserve both observations and select the more conservative status. This
 # is deterministic for repeated rows within one worker and overlaps between
 # workers alike.
 chosen=candidate if SEVERITY[candidate['status']] > SEVERITY[existing['status']] else existing
 other=existing if chosen is candidate else candidate
 chosen['evidence']=chosen['evidence']+'\n'+other['evidence']
 rows[row['id']]=chosen

def integrity_row():
 path=Path('.uncle/workflow/green-check.tsv')
 try:
  records=[line.split('\t',1) for line in path.read_text().splitlines() if line.strip()]
 except OSError as e:
  return {'id':'INTEGRITY','required':True,'status':'BLOCKED-SETUP','evidence':'Driver green-check record is unavailable: %s.'%e}
 if not records or any(len(record)!=2 or record[0]!='PASS' for record in records):
  return {'id':'INTEGRITY','required':True,'status':'BLOCKED-SETUP','evidence':'Driver green-check has missing or non-passing command records; see .uncle/workflow/green-check.tsv.'}
 return {'id':'INTEGRITY','required':True,'status':'PASS','evidence':'Driver green-check recorded %d passing verification command(s); see .uncle/workflow/green-check.tsv.'%len(records)}

def main(directory,out,*names):
 rows={}
 for n in names:
  expected=sorted(EXPECTED.get(n,set()))
  try: p=json.loads((Path(directory)/(n+'.json')).read_text())
  except Exception as e:
   for identifier in expected:
    merge_row(rows,{'id':identifier,'status':'BLOCKED-SETUP','evidence':'Worker packet %s.json was unreadable: %s'%(n,e)},n+'.json')
   continue
  if p.get('schema')!='uncle.artifact/v1' or p.get('kind')!='test-review-worker-packet' or not isinstance(p.get('rows'),list):
   for identifier in expected:
    merge_row(rows,{'id':identifier,'status':'BLOCKED-SETUP','evidence':'Worker packet %s.json did not match the required schema.'%n},n+'.json')
   continue
  for r in p['rows']:
   if not isinstance(r,dict) or not r.get('id') or r.get('status') not in STAT or not r.get('evidence'): raise ValueError('%s.json: invalid acceptance row'%n)
   r=dict(r,id=normalized_id(r['id']))
   merge_row(rows,r,n)
 rows['INTEGRITY']=integrity_row()
 rows['RESULTS']={'id':'RESULTS','required':True,'status':'PASS','evidence':'Driver green-check completed; see .uncle/workflow/green-check.md.'}
 result={'schema':'uncle.artifact/v1','kind':'acceptance-report','rows':[rows[k] for k in sorted(rows)]}
 Path(out).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 try:
  if sys.argv[1]=='validate': raise SystemExit(0 if packet_valid(sys.argv[2],sys.argv[3]) else 1)
  main(*sys.argv[1:])
 except Exception as e: print('test review packets: '+str(e),file=sys.stderr);raise SystemExit(1)
