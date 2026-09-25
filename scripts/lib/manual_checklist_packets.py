#!/usr/bin/env python3
"""Merge authoritative executable checklist packets without a parent model."""
import json, sys
from pathlib import Path


def packet(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except Exception as error:
        raise ValueError('%s: invalid checklist packet: %s' % (path.name, error))
    if (data.get('schema') != 'uncle.artifact/v1'
            or data.get('kind') != 'manual-checklist-worker-packet'
            or not isinstance(data.get('checks'), list)):
        raise ValueError('%s: expected manual-checklist-worker-packet checks array' % path.name)
    for check in data['checks']:
        if (not isinstance(check, dict) or not check.get('id')
                or not check.get('exact_action') or not check.get('expected_result')):
            raise ValueError('%s: every check needs id, exact_action, expected_result' % path.name)
    return data


def main(directory, output, *names):
    checks={}
    for name in names:
        path=Path(directory)/(name+'.json')
        data = packet(path)
        for check in data['checks']:
            ident=check['id']
            if ident in checks and checks[ident] != check: raise ValueError('%s: conflicting duplicate check %s' % (path.name,ident))
            checks[ident]=check
    if not checks: raise ValueError('manual checklist workers produced no checks')
    result={'schema':'uncle.artifact/v1','kind':'manual-checklist','checks':[checks[k] for k in sorted(checks)]}
    Path(output).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == 'validate':
            packet(sys.argv[2])
        else:
            main(*sys.argv[1:])
    except Exception as e: print('manual checklist packets: '+str(e),file=sys.stderr); raise SystemExit(1)
