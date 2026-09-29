"""Every file the plan promises to freeze must have an owner before IMPLEMENT starts.

Protected verification paths name files the plan expects to exist and never
change again once authored. A path listed there that no step's `Owns:` covers
-- and which does not already exist in the tree -- has no one tasked with
creating it. Nothing enforces the plan's own promise, and the gap surfaces
only much later as a runtime failure deep in verification (a missing
package.json discovered as an npm ENOENT at green-check time, long after a
full implementation cycle already ran).

`Owns: *` (a reconcile step) does not count as an owner here on purpose: a
real plan had exactly that shape -- a step whose own description said "no new
behavior" was the only thing nominally covering an unauthored package.json.
A wildcard is for incidental touches during reconciliation, not a substitute
for naming who creates a brand-new required file.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step_groups import covers, owns


def load_protected_paths(plan, state_dir):
    json_path = Path(state_dir) / 'documents' / (Path(plan).stem + '.json')
    if not json_path.is_file():
        return []
    try:
        payload = json.loads(json_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    raw = payload.get('protected_verification_paths') or ''
    if not isinstance(raw, str):
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


def specifically_owned(plan):
    lib = Path(__file__).resolve().parent
    def sh(fn):
        return subprocess.run(['bash', '-c', '. "%s/plan-scope.sh"; %s "%s"' % (lib, fn, plan)],
                              capture_output=True, text=True).stdout.splitlines()
    owned = owns(sh('plan_step_owns'))
    specific = {step: {path for path in paths if path != '*'} for step, paths in owned.items()}
    return [paths for paths in specific.values() if paths]


def unowned_protected_paths(plan, root, protected):
    root = Path(root)
    specific = specifically_owned(plan)
    gaps = []
    for path in protected:
        if not path or path.startswith('.uncle/'):
            continue
        if (root / path).exists():
            continue
        if any(covers(paths, path) for paths in specific):
            continue
        gaps.append(path)
    return gaps


def main(argv):
    if len(argv) != 3:
        raise ValueError('usage: plan_ownership_gap.py PLAN.md PROJECT_ROOT STATE_DIR')
    plan, root, state_dir = argv
    protected = load_protected_paths(plan, state_dir)
    gaps = unowned_protected_paths(plan, root, protected)
    for gap in gaps:
        print(gap)
    return 1 if gaps else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
