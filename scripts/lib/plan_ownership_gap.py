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
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step_groups import covers, owns
from plan_records import canonical_path, load, step_data
from plan_model import protected_paths


def normalized_path(path):
    while path.startswith('./'):
        path = path[2:]
    return path


def load_protected_paths(plan, state_dir):
    json_path = canonical_path(plan, state_dir)
    if json_path is None:
        text = Path(plan).read_text(encoding='utf-8')
        section = re.search(r'^#{2,3} Protected verification paths\s*\n(.*?)(?=^#{2,3} |\Z)', text, re.M | re.S)
        if not section:
            return []
        body = section.group(1)
        fence = re.search(r'```(?:text)?\n(.*?)\n```', body, re.S)
        return protected_paths(fence.group(1)) if fence else re.findall(r'^\s*-\s*`([^`]+)`', body, re.M)
    try:
        payload = json.loads(json_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('cannot read protected paths: %s' % json_path) from error
    raw = payload.get('protected_verification_paths') or ''
    return protected_paths(raw)


def specifically_owned(plan, state_dir=None):
    lib = Path(__file__).resolve().parent
    def sh(fn):
        return subprocess.run(['bash', '-c', '. "$1/plan-scope.sh"; "$2" "$3"', 'ownership-gap', str(lib), fn, str(plan)],
                              capture_output=True, text=True, check=True).stdout.splitlines()
    model = load(plan, state_dir)
    owned = step_data(model)[1] if model is not None else owns(sh('plan_step_owns'))
    specific = list(owned.values())
    return [{normalized_path(path) for path in paths if path and normalized_path(path) != '*'}
            for paths in specific if paths]


def owns_something_under(specific, directory):
    """A protected directory (`tests/`) is owned when the plan assigns files inside it.

    `covers` answers the other direction -- does a declared token cover this path -- and a file under a
    directory does not cover the directory, so every directory entry was reported as having no owner even
    when steps 5-8 owned every test file in it (noinit: three triage rounds on `tests/`, none of which
    could fix a plan that was right).  The directory stays protected as a whole; what it needs is someone
    tasked with creating what goes in it.
    """
    prefix = directory.rstrip('/') + '/'
    return any(token.startswith(prefix) for paths in specific for token in paths)


def is_directory_entry(path, root):
    return path.endswith('/') or (Path(root) / path).is_dir()


def unowned_protected_paths(plan, root, protected, state_dir=None):
    root = Path(root)
    specific = specifically_owned(plan, state_dir)
    gaps = []
    for path in protected:
        path = normalized_path(path)
        if not path or path.startswith('.uncle/'):
            continue
        if (root / path).exists():
            continue
        if any(covers(paths, path) for paths in specific):
            continue
        if is_directory_entry(path, root) and owns_something_under(specific, path):
            continue
        gaps.append(path)
    return gaps


def main(argv):
    if len(argv) != 3:
        raise ValueError('usage: plan_ownership_gap.py PLAN.md PROJECT_ROOT STATE_DIR')
    plan, root, state_dir = argv
    protected = load_protected_paths(plan, state_dir)
    gaps = unowned_protected_paths(plan, root, protected, state_dir)
    for gap in gaps:
        print(gap)
    return 1 if gaps else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
