#!/usr/bin/env python3
"""Which implementation steps could have run together, and would it have been safe?

A probe, not an executor. It reads the plan's declared per-step file ownership,
computes the groups a parallel implementation would have used, and -- once the
code exists -- checks those declarations against what the tree actually shows.

The question it answers is the one that decides whether parallel implementation
is worth building: can a plan partition its own work accurately? Under-declare
and a real run would abort groups for touching unowned files; over-declare and
everything serialises and nothing is gained.

Grouping follows checklist_groups.py, which solves the same problem for checks:
consecutive runs that share no declared resource, dependencies respected, and
any doubt collapsing to one unit per group.
"""
import json
import subprocess
import sys
from pathlib import Path


def owns(rows):
    out = {}
    for line in rows:
        if '\t' not in line:
            continue
        step, path = line.split('\t', 1)
        out.setdefault(int(step), set()).add(path.strip())
    return out


def depends(rows):
    out = {}
    for line in rows:
        if '\t' not in line:
            continue
        step, on = line.split('\t', 1)
        out.setdefault(int(step), set()).add(int(on.strip()))
    return out


# A step that legitimately owns a manifest also owns its lockfile: the
# lockfile is a deterministic byproduct of installing or updating what that
# manifest already declares, not new scope the plan failed to name. Real
# runs repeatedly aborted a merge over exactly this -- a step scaffolding
# `package.json` also produces `package-lock.json`, and no plan writer
# reliably remembers to name the lockfile too. This is deliberately narrow:
# only the paired lockfile of an *already-declared* manifest, in the same
# directory, never a whole new file the plan never mentioned at all.
LOCKFILE_OF_MANIFEST = {
    'package.json': ('package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb'),
    'Cargo.toml': ('Cargo.lock',),
    'Gemfile': ('Gemfile.lock',),
    'composer.json': ('composer.lock',),
    'pyproject.toml': ('poetry.lock', 'uv.lock', 'Pipfile.lock'),
    'Pipfile': ('Pipfile.lock',),
    'go.mod': ('go.sum',),
}


def _dirname(path):
    return path.rsplit('/', 1)[0] if '/' in path else ''


def covers(owned, path):
    """Does a declared token cover this path? Directories cover what is under them."""
    for token in owned:
        if token == '*':
            return True
        if token == path:
            return True
        if token.endswith('/') and path.startswith(token):
            return True
        if path.startswith(token.rstrip('/') + '/'):
            return True
        lockfiles = LOCKFILE_OF_MANIFEST.get(token.rsplit('/', 1)[-1])
        if lockfiles and path.rsplit('/', 1)[-1] in lockfiles and _dirname(token) == _dirname(path):
            return True
    return False


def group(total, owned, deps):
    """Consecutive runs of steps that share no owned path and break no dependency.

    A step that declared nothing owns everything: silence must never be read as
    'safe to run beside anything'.
    """
    groups, current, held = [], [], set()
    for step in range(1, total + 1):
        mine = owned.get(step) or {'*'}
        clash = '*' in mine or '*' in held or bool(mine & held)
        waits = any(on in [s for g in [current] for s in g] for on in deps.get(step, ()))
        if current and (clash or waits):
            groups.append(current)
            current, held = [], set()
        current.append(step)
        held |= mine
    if current:
        groups.append(current)
    return groups


WORKFLOW_DOCS = {
    'REQUIREMENTS.md', 'REQUIREMENTS_INTERPRETATION.md', 'PROJECT_PLAN.md',
    'UPDATED_PROJECT_PLAN.md', 'ADVERSARIAL_REVIEW.md', 'PREFLIGHT_REPORT.md',
    'AUTOMATED_TEST_REPORT.md', 'IMPLEMENTATION_NOTES.md', 'TEST_REVIEW.md',
    'MANUAL_CHECKLIST.md', 'VERIFICATION_REPORT.md', 'FINAL_AUDIT.md',
    'CHANGE_REQUEST.md', 'CHANGE_SPEC.md', 'CHANGE_PLAN.md', 'BASELINE_REPORT.md',
    'CHANGE_TEST_REPORT.md', 'DEFECTS.md',
}


def changed_files(root):
    for args in (['git', 'diff', '--name-only', 'HEAD'], ['git', 'ls-files', '--others', '--exclude-standard']):
        result = subprocess.run(args, cwd=root, capture_output=True, text=True)
        for name in result.stdout.splitlines():
            name = name.strip()
            # The workflow's own documents are not implementation output: no
            # step would ever claim REQUIREMENTS.md, and counting them made
            # every build look like it had declared nothing.
            if not name or name.startswith('.uncle/'):
                continue
            base = name.rsplit('/', 1)[-1]
            if base in WORKFLOW_DOCS or base == '.gitignore':
                continue
            yield name


def main():
    plan, root = sys.argv[1], sys.argv[2]
    lib = Path(__file__).resolve().parent

    def sh(fn):
        return subprocess.run(['bash', '-c', '. "%s/plan-scope.sh"; %s "%s"' % (lib, fn, plan)],
                              capture_output=True, text=True).stdout.splitlines()

    steps = [s for s in sh('plan_steps') if s.strip()]
    owned, deps = owns(sh('plan_step_owns')), depends(sh('plan_step_depends'))
    total = len(steps)
    groups = group(total, owned, deps) if total else []
    declared = sorted({p for v in owned.values() for p in v})
    actual = sorted(set(changed_files(root)))
    # Accuracy is measured against *specific* claims only. A reconciling step
    # declaring `Owns: *` covers every file by definition, so counting it would
    # report perfect accuracy for any plan containing one -- and tell us
    # nothing about whether the parallelisable steps declared honestly.
    specific = {s: {p for p in v if p != '*'} for s, v in owned.items()}
    specific = {s: v for s, v in specific.items() if v}
    unclaimed = [f for f in actual if not any(covers(v, f) for v in specific.values())]
    multi = [g for g in groups if len(g) > 1]
    parallel_steps = sorted({s for g in multi for s in g})

    report = {
        'steps': total,
        'steps_declaring_ownership': len(owned),
        'groups': groups,
        'largest_group': max((len(g) for g in groups), default=0),
        'declared_paths': declared,
        'changed_files': actual,
        'declared_but_untouched': [p for p in declared
                                   if p != '*' and not any(covers({p}, f) for f in actual)],
        'steps_that_could_run_in_parallel': parallel_steps,
        'changed_but_claimed_by_no_specific_step': unclaimed,
        'declaration_accuracy': (
            round(100.0 * (len(actual) - len(unclaimed)) / len(actual), 1) if actual else None),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
