"""Consume an explicit stage rerun request while the workflow driver holds its lock."""
import json
import os
import re
from pathlib import Path
import shutil
import sys
import uuid
from supervisor import state_digest

STEP = re.compile(r'implementation-step-([1-9][0-9]*)$')

APP = {'requirements':'REQUIREMENTS','project-plan':'PROJECT_PLAN','adversarial-review':'ADVERSARIAL_REVIEW','updated-plan':'UPDATED_PLAN','preflight':'PREFLIGHT','implementation':'IMPLEMENT','test-review':'TEST_REVIEW','manual-checklist':'MANUAL_CHECKLIST','execute-checklist':'EXECUTE_CHECKLIST','final-audit':'FINAL_AUDIT'}
CHANGE = {'baseline':'ANALYZE','change-plan':'PLAN','adversarial-review':'ADVERSARIAL_REVIEW','updated-change-plan':'UPDATED_PLAN','implementation':'IMPLEMENT','manual-checklist':'CHECKLIST','execute-checklist':'EXECUTE_CHECKLIST','final-audit':'FINAL_AUDIT'}

def supports(name, family):
    """Whether a user may explicitly rerun this named stage."""
    return name in (CHANGE if family == 'change' else APP) or bool(STEP.fullmatch(name))

def consume(root, family):
    root=Path(root); state=root/'.uncle/workflow'; request=state/'rerun-request.json'
    if not request.exists(): return
    data=json.loads(request.read_text()); name=str(data['stage']).strip().lower(); mapping=CHANGE if family=='change' else APP
    step=STEP.fullmatch(name)
    if not supports(name, family): raise ValueError('Unsupported stage for '+family+': '+name)
    target='implementation' if step else name
    step_number=0
    if step:
        steps=state/'implement-steps.txt'
        if not steps.is_file():
            raise ValueError('No saved implementation steps; rerun implementation instead.')
        total=sum(1 for line in steps.read_text().splitlines() if line.strip())
        step_number=int(step.group(1))
        if step_number > total:
            raise ValueError('implementation-step-%d is unavailable; this plan has %d steps.' % (step_number, total))
    archive=state/'stage-reruns'/uuid.uuid4().hex; archive.mkdir(parents=True)
    # Preserve all reports and control records before resetting any derived state.
    for p in root.glob('*.md'):
        if p.is_file() and not p.is_symlink(): shutil.copy2(p,archive/p.name)
    shutil.copy2(request,archive/request.name)
    shutil.copy2(state/'state',archive/'previous-state')
    # Keep prerequisites, invalidate approval for this stage and downstream stages.
    names=list(mapping); position=names.index(target)
    approvals={'requirements':['REQUIREMENTS_INTERPRETATION'],'project-plan':['PROJECT_PLAN'],
      'baseline':['BASELINE_REPORT','CHANGE_SPEC'],'change-plan':['CHANGE_PLAN'],
      'adversarial-review':['ADVERSARIAL_REVIEW'],'updated-plan':['UPDATED_PROJECT_PLAN'],
      'updated-change-plan':['UPDATED_CHANGE_PLAN'],'implementation':['IMPLEMENTATION_REVIEW']}
    invalid={a for n in names[position:] for a in approvals.get(n,[])}
    approval_dir=state/'approvals'
    for p in approval_dir.glob('*'):
        if p.name.split('.')[0] in invalid:
            archived_approvals=archive/'approvals';archived_approvals.mkdir(exist_ok=True);p.rename(archived_approvals/p.name)
    for item in ('review-cache','speculative','change-plan.draft-key','validation-error.txt','stop-reason'):
        p=state/item
        if p.exists(): p.rename(archive/item)
    # Keep the issue binding. The state file for an issue run is "<issue>:<stage>",
    # and writing a bare stage dropped the prefix -- after which the driver saw a
    # COMPLETE run with no issue, decided the finished work belonged to a
    # different one, cleared the verdict and override records and restarted the
    # whole workflow at its first stage. A rewind to one stage became a rebuild.
    previous=(state/'state').read_text().strip() if (state/'state').is_file() else ''
    prefix=previous.split(':',1)[0]+':' if ':' in previous and previous.split(':',1)[0].isdigit() else ''
    # A numbered implementation step is a recovery boundary. Rewind its
    # checkpoint to the preceding step so the driver does not replay steps
    # 1..N; it runs this requested step and all downstream stages.
    if step:
        done=state/'implement-step-done'
        if step_number == 1:
            done.unlink(missing_ok=True)
        else:
            done.write_text(str(step_number - 1) + '\n')
        (state/'implement-report-done').unlink(missing_ok=True)
    pending=state/'state.rerun-pending';pending.write_text(prefix+mapping[target]+'\n');os.replace(pending,state/'state')
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
