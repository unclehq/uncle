#!/usr/bin/env python3
"""How much of a plan's implementation can run at once, said while the plan can still change.

step_groups.py answers this after the code exists.  The plan stages are where the answer is
cheap to act on: a plan whose steps form one chain implements them one at a time, and the
only people who see that are the ones waiting for it.  This is advisory -- it never fails a
stage -- and names, for each step that starts a new group, why it could not join the one before.

usage: plan_parallelism.py PLAN.md    (prints a short report; exit status is always 0)
"""
import subprocess
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB))
from step_groups import depends, group, owns


def shell(plan, function):
    command = '. "%s/plan-scope.sh"; %s "%s"' % (LIB, function, plan)
    return subprocess.run(['bash', '-c', command], capture_output=True, text=True).stdout.splitlines()


def analyse(plan):
    steps = [s for s in shell(plan, 'plan_steps') if s.strip()]
    owned, deps = owns(shell(plan, 'plan_step_owns')), depends(shell(plan, 'plan_step_depends'))
    total = len(steps)
    groups = group(total, owned, deps) if total else []
    reasons = {}
    placed = {}
    for index, members in enumerate(groups):
        for step in members:
            placed[step] = index
    for index, members in enumerate(groups[1:], 1):
        first = members[0]
        previous = groups[index - 1]
        mine = owned.get(first) or {'*'}
        blockers = [d for d in sorted(deps.get(first, ())) if placed.get(d) == index - 1]
        clash = sorted({p for s in previous for p in (owned.get(s) or {'*'})} & mine)
        all_deps = sorted(deps.get(first, ()))
        if total >= 4 and len(all_deps) >= total - 3 and first != total:
            reasons[first] = ('waits for %d other steps, a serial tail; if it only runs or checks their files at '
                              'verification time it can be written beside them' % len(all_deps))
        elif first == total and (owned.get(first) == {'*'} or len(all_deps) >= total - 3) and total >= 4:
            reasons[first] = ('is a final step that owns every file and waits for the rest; the driver runs the '
                              'verification and a repair stage fixes mismatches, so it can be dropped')
        elif blockers:
            reasons[first] = 'depends on step %s' % ', '.join(map(str, blockers))
        elif first not in owned:
            reasons[first] = 'declares no `Owns:`, so it is treated as owning every file'
        elif mine == {'*'}:
            reasons[first] = 'owns `*`, every file'
        elif clash == ['*']:
            reasons[first] = 'follows a step that owns `*` or declares no `Owns:`'
        elif clash:
            reasons[first] = 'shares %s with the step before it' % ', '.join(clash[:3])
        else:
            reasons[first] = 'owns everything or declares nothing'
    return total, groups, reasons


def report(plan):
    total, groups, reasons = analyse(plan)
    if total == 0:
        return 'Plan parallelism: no implementation steps with declared ownership were found.'
    together = sum(len(g) for g in groups if len(g) > 1)
    lines = ['Plan parallelism: %d steps run in %d groups; %d of them can run beside another step.'
             % (total, len(groups), together)]
    tail = [first for first, why in reasons.items() if 'serial tail' in why or 'final step' in why]
    if tail and total >= 5 and len(groups) < total - 1:
        lines.append('Serial tail: ' + '; '.join('step %d %s' % (first, reasons[first]) for first in sorted(tail)))
    if total >= 5 and len(groups) >= total - 1:
        lines.append('This plan implements almost one step at a time. Steps that start a new group:')
        for first, why in sorted(reasons.items())[:6]:
            lines.append('  step %d %s' % (first, why))
        lines.append('Fewer `Depends on:` edges, interfaces fixed in the plan, and one owner per file let steps run together.')
    return '\n'.join(lines)


def main(argv):
    if len(argv) != 1 or not Path(argv[0]).is_file():
        print('Plan parallelism: no plan to read.')
        return 0
    try:
        print(report(argv[0]))
    except Exception as error:  # advisory: never stop a stage over it
        print('Plan parallelism: not computed (%s).' % error)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
