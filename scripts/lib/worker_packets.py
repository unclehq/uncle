#!/usr/bin/env python3
"""Strict, compact transport for all read-only specialist worker panels."""
import argparse, json, re, sys
from pathlib import Path

SCHEMA='uncle.artifact/v1'
PLACEHOLDER_ID=re.compile(r'^\s*(?:no\s+finding|none|n/?a|tbd)(?:\s|$|[-_:])', re.I)
class PacketError(ValueError): pass

def load(path, kind):
    name=Path(path).name
    try: value=json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError: raise PacketError('%s: worker packet is missing' % name)
    except json.JSONDecodeError as e:
        # Some OpenCode transports append a single quote fragment after an
        # otherwise complete final message. Repair only that unambiguous
        # transport suffix; never invent a missing string/value or accept an
        # actually truncated object.
        raw=Path(path).read_text(encoding='utf-8')
        repaired=re.sub(r',\s*"\s*([}\]])', r'\1', raw)
        repaired=re.sub(r',\s*([}\]])', r'\1', repaired)
        if repaired == raw: raise PacketError('%s: invalid JSON worker packet: %s' % (name,e))
        try: value=json.loads(repaired)
        except json.JSONDecodeError: raise PacketError('%s: invalid JSON worker packet: %s' % (name,e))
        Path(path).write_text(repaired, encoding='utf-8')
    except OSError as e: raise PacketError('%s: invalid JSON worker packet: %s' % (name,e))
    if not isinstance(value,dict) or value.get('schema') != SCHEMA or not str(value.get('kind','')).endswith('-worker-packet'):
        raise PacketError('%s: expected schema %s and a worker-packet kind' % (name,SCHEMA))
    items=value.get('findings')
    if not isinstance(items,list): raise PacketError('%s: findings must be an array' % name)
    out=[]
    for i,item in enumerate(items,1):
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id'].strip() or not isinstance(item.get('summary'),str) or not item['summary'].strip():
            raise PacketError('%s: finding %d requires nonempty id and summary' % (name,i))
        identifier=item['id'].strip()
        if PLACEHOLDER_ID.match(identifier):
            raise PacketError('%s: finding %d needs a stable finding ID, not placeholder %r' % (name,i,identifier))
        # Findings are merged by stable ID below.  Keep duplicate observations
        # from one worker too: rejecting them loses evidence merely because a
        # model reused an ID.  This is intentionally different from checklist
        # check IDs, where a duplicate would mean two executions of one row.
        out.append({'id':identifier,'summary':item['summary'].strip(), 'evidence':str(item.get('evidence','')).strip()})
    return out

def collate(directory, output, kind, expected):
    merged={}; workers=[]
    for source in expected:
        findings=load(Path(directory)/(source+'.json'),kind); workers.append({'source':source,'status':'ok','finding_count':len(findings)})
        for item in findings:
            target=merged.setdefault(item['id'],{'id':item['id'],'summaries':[],'evidence':[],'sources':[]})
            for key,value in (('summaries',item['summary']),('evidence',item['evidence'])):
                if value and value not in target[key]: target[key].append(value)
            if source not in target['sources']:
                target['sources'].append(source)
    payload={'schema':SCHEMA,'kind':kind+'s','workers':workers,'findings':[merged[k] for k in sorted(merged)]}
    Path(output).parent.mkdir(parents=True,exist_ok=True); Path(output).write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(); p.add_argument('directory');p.add_argument('output');p.add_argument('--kind',required=True);p.add_argument('--expected',nargs='+',required=True);a=p.parse_args()
    try: collate(a.directory,a.output,a.kind,a.expected)
    except PacketError as e: print('worker packets: '+str(e),file=sys.stderr);return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
