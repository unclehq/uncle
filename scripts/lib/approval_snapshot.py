"""Bind implementation approval to content, independently of review formatting."""
import hashlib,json,os
from pathlib import Path
import sys
from evidence_index import save
from review_paths import paths


def tracked_names(state):
    state=Path(state)
    names=set(paths(os.environ.get('WORKFLOW_UNTRACKED_BASELINE')))
    names.update(n for n in ('REQUIREMENTS.md','.uncle/docs/UPDATED_PROJECT_PLAN.md','.uncle/docs/CHANGE_SPEC.md','.uncle/docs/CHANGE_PLAN.md') if Path(n).exists())
    names.update(str(state/n) for n in ('verification.paths','verification.manifest','green-check.current.tsv') if (state/n).exists())
    return names


def snapshot(names):
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
    if action=='prepare':save(pending,snapshot(tracked_names(state)));return
    if action=='record':
        inputs=json.loads(pending.read_text())
        # Re-hash exactly the paths `prepare` looked at, not a freshly
        # re-derived git-status set. review_paths.paths() calls git diff/
        # ls-files live, so a background job still finishing between prepare
        # and record -- backgrounded preflight is the default, and approval
        # is near-instant under --unattended -- could add or remove a path
        # and fail this over a set difference, not an actual content change
        # to anything that was reviewed. That killed the whole driver right
        # after a correctly auto-recorded approval, leaving state parked at
        # WAIT_IMPLEMENT_APPROVAL with no process running and no further
        # explanation -- indistinguishable from "still waiting for approval."
        if inputs!=snapshot(inputs.keys()):raise ValueError('Inputs changed during approval; review again')
        save(approved,{'review_digest':approval.read_text().strip(),'inputs':inputs});return
    saved=json.loads(approved.read_text())
    # Unlike prepare/record (a split-second pair with no legitimate new file
    # in between), this later re-verification must still catch a tree that
    # moved after approval, including a genuinely new file -- keep it on the
    # live, freshly-derived set.
    if saved['review_digest']!=approval.read_text().strip() or saved['inputs']!=snapshot(tracked_names(state)):
        raise ValueError('Approved implementation inputs changed')

if __name__=='__main__':
    try:main(*sys.argv[1:3])
    except (OSError,ValueError,KeyError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
