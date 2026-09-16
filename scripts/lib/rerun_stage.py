"""Consume an explicit stage rerun request while the workflow driver holds its lock."""
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
from supervisor import state_digest

APP = {'requirements':'REQUIREMENTS','project-plan':'PROJECT_PLAN','adversarial-review':'ADVERSARIAL_REVIEW','updated-plan':'UPDATED_PLAN','preflight':'PREFLIGHT','implementation':'IMPLEMENT','test-review':'TEST_REVIEW','manual-checklist':'MANUAL_CHECKLIST','execute-checklist':'EXECUTE_CHECKLIST','final-audit':'FINAL_AUDIT'}
CHANGE = {'baseline':'ANALYZE','change-plan':'PLAN','adversarial-review':'ADVERSARIAL_REVIEW','updated-change-plan':'UPDATED_PLAN','implementation':'IMPLEMENT','manual-checklist':'CHECKLIST','execute-checklist':'EXECUTE_CHECKLIST','final-audit':'FINAL_AUDIT'}

def consume(root, family):
    root=Path(root); state=root/'.uncle/workflow'; request=state/'rerun-request.json'
    if not request.exists(): return
    data=json.loads(request.read_text()); name=data['stage']; mapping=CHANGE if family=='change' else APP
    if name not in mapping: raise ValueError('Unsupported stage for '+family+': '+name)
    archive=state/'stage-reruns'/uuid.uuid4().hex; archive.mkdir(parents=True)
    # Preserve all reports and control records before resetting any derived state.
    for p in root.glob('*.md'):
        if p.is_file() and not p.is_symlink(): shutil.copy2(p,archive/p.name)
    shutil.copy2(request,archive/request.name)
    shutil.copy2(state/'state',archive/'previous-state')
    # Keep prerequisites, invalidate approval for this stage and downstream stages.
    names=list(mapping); position=names.index(name)
    approvals={'requirements':['REQUIREMENTS_INTERPRETATION'],'project-plan':['PROJECT_PLAN'],
      'baseline':['BASELINE_REPORT','CHANGE_SPEC'],'change-plan':['CHANGE_PLAN'],
      'adversarial-review':['ADVERSARIAL_REVIEW'],'updated-plan':['UPDATED_PROJECT_PLAN'],
      'updated-change-plan':['UPDATED_CHANGE_PLAN'],'implementation':['IMPLEMENTATION_REVIEW']}
    invalid={a for n in names[position:] for a in approvals.get(n,[])}
    approval_dir=state/'approvals'
    for p in approval_dir.glob('*'):
        if p.name.split('.')[0] in invalid:
            target=archive/'approvals';target.mkdir(exist_ok=True);p.rename(target/p.name)
    for item in ('review-cache','speculative','change-plan.draft-key','validation-error.txt','stop-reason'):
        p=state/item
        if p.exists(): p.rename(archive/item)
    pending=state/'state.rerun-pending';pending.write_text(mapping[name]+'\n');os.replace(pending,state/'state')
    # A supervisor retry retains a correction before requesting the rewind.
    # Bind that note to the newly reset control state so the next stage launch
    # can claim it. Explicit /run requests normally have no such note.
    note=state/'supervision'/('retry-note-'+name+'.json')
    if note.is_file():
        data=json.loads(note.read_text())
        if data.get('delivery')=='pending':
            data['state_digest']=state_digest(state)
            temporary=note.with_name(note.name+'.pending')
            temporary.write_text(json.dumps(data,sort_keys=True)+'\n')
            os.replace(temporary,note)
    request.unlink()
    print('Explicit rerun: '+name+'. Previous reports preserved at '+str(archive))

if __name__=='__main__':
    try:consume(Path.cwd(),sys.argv[1])
    except (OSError,ValueError,KeyError) as e:
        print('Stage rerun refused: '+str(e),file=sys.stderr);sys.exit(1)
