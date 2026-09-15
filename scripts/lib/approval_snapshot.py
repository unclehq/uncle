"""Bind implementation approval to content, independently of review formatting."""
import hashlib,json,os
from pathlib import Path
import sys
from evidence_index import save
from review_paths import paths


def snapshot(state):
    state=Path(state)
    names=set(paths(os.environ.get('WORKFLOW_UNTRACKED_BASELINE')))
    names.update(n for n in ('REQUIREMENTS.md','UPDATED_PROJECT_PLAN.md','CHANGE_SPEC.md','CHANGE_PLAN.md') if Path(n).exists())
    names.update(str(state/n) for n in ('verification.paths','verification.manifest','green-check.current.tsv') if (state/n).exists())
    result={}
    for name in sorted(names):
        p=Path(name)
        if p.is_symlink():
            result[name]={'link':os.readlink(p)}
        elif p.is_file():
            h=hashlib.sha256()
            with p.open('rb') as stream:
                while chunk:=stream.read(65536):h.update(chunk)
            result[name]={'sha256':h.hexdigest(),'executable':bool(p.stat().st_mode & 0o111)}
        else:result[name]={'missing':True}
    return result


def main(action,state):
    state=Path(state); pending=state/'approval-inputs.pending.json';approved=state/'approvals/IMPLEMENTATION_REVIEW.inputs.json'
    approval=state/'approvals/IMPLEMENTATION_REVIEW.sha256'
    if action=='prepare':save(pending,snapshot(state));return
    if action=='record':
        inputs=json.loads(pending.read_text())
        if inputs!=snapshot(state):raise ValueError('Inputs changed during approval; review again')
        save(approved,{'review_digest':approval.read_text().strip(),'inputs':inputs});return
    saved=json.loads(approved.read_text())
    if saved['review_digest']!=approval.read_text().strip() or saved['inputs']!=snapshot(state):
        raise ValueError('Approved implementation inputs changed')

if __name__=='__main__':
    try:main(*sys.argv[1:3])
    except (OSError,ValueError,KeyError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
