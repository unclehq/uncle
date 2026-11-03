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
import fnmatch
from functools import lru_cache
import json
import os
import re
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


def _glob_matches(token, path):
    """Match a token with glob metacharacters against a path, one segment at a
    time -- fnmatch's own '*' crosses '/', which would make a declared
    `scripts/tests/*.sh` reach into subdirectories no plan writer intended."""
    token_parts = token.split('/')
    path_parts = path.split('/')
    @lru_cache(None)
    def match(i, j):
        if i == len(token_parts):
            return j == len(path_parts)
        if token_parts[i] == '**':
            return match(i + 1, j) or (j < len(path_parts) and match(i, j + 1))
        return (j < len(path_parts) and fnmatch.fnmatchcase(path_parts[j], token_parts[i])
                and match(i + 1, j + 1))
    return match(0, 0)


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
        if any(ch in token for ch in '*?[') and _glob_matches(token, path):
            return True
        lockfiles = LOCKFILE_OF_MANIFEST.get(token.rsplit('/', 1)[-1])
        if lockfiles and path.rsplit('/', 1)[-1] in lockfiles and _dirname(token) == _dirname(path):
            return True
    return False


def group(total, owned, deps, ignore_deps=False):
    """Consecutive runs of steps that share no owned path and break no dependency.

    `ignore_deps` groups by ownership alone.  Implementation workers write only their own files, read none of
    another step's and run nothing (the Speed rule in the step prompt), so a `Depends on:` buys them nothing
    at this stage -- the plan's interfaces are what they build to -- and honouring it just serialises: a runner
    that "depends on" the mutation list and the app waited for all of them, adding a whole step's time.
    Ordering that matters is checked by verification, after the merge.

    A step that declared nothing owns everything: silence must never be read as
    'safe to run beside anything'.
    """
    groups, current, held = [], [], set()
    for step in range(1, total + 1):
        mine = owned.get(step) or {'*'}
        clash = '*' in mine or '*' in held or bool(mine & held)
        waits = (not ignore_deps) and any(on in [s for g in [current] for s in g] for on in deps.get(step, ()))
        if current and (clash or waits):
            groups.append(current)
            current, held = [], set()
        current.append(step)
        held |= mine
    if current:
        groups.append(current)
    return groups


# What a step is for, from the files it owns. Tests are written by their own workers on purpose (a test written by the
# agent that wrote the code can encode that code's bugs), and scaffold and config files change for different reasons than the
# application does. The application's own files, though, refer to each other by string -- a component's `className`, the
# stylesheet's selector for it, the state a view reads -- and workers that cannot see one another's files name those things
# differently (live: `className="keypad"` in one step, no `.keypad` rule in the stylesheet step).
TEST_PATH = re.compile(r'(^|/)(tests?|e2e|specs?|__tests__|cypress)(/|$)|\.(test|spec)\.[A-Za-z]+$|(^|/)[^/]*(mutat|defect-inject)[^/]*$', re.I)
SCAFFOLD_PATH = re.compile(r'(^|/)(package\.json|package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|index\.html|README(\.md)?|'
                           r'\.gitignore|\.uncle/.*|tsconfig[^/]*\.json|[^/]*\.config\.[cm]?[jt]s|\.eslintrc[^/]*|\.prettierrc[^/]*|\.env[^/]*)$', re.I)


# The entry files link everything else: the page links the scripts and stylesheets, `main` and `App` import the components and the
# theme (live: `src/theme.css` never imported, so the page had no theme, because the step that wrote the entry files and the
# step that wrote the stylesheet were different workers). A step that owns an entry file beside application source, and
# otherwise only scaffold, belongs to the application's worker. Scaffold alone stays scaffold; anything with tests stays mixed.
ENTRY_FILE = re.compile(r'(^|/)(index\.html|main\.[cm]?[jt]sx?|App\.[cm]?[jt]sx?)$', re.I)


def role(paths):
    """'test', 'scaffold' or 'app' when every owned path agrees; 'mixed' for anything else, including a step that owns `*`."""
    paths = {p for p in paths if p}
    if not paths or '*' in paths:
        return 'mixed'
    kinds = {'test' if TEST_PATH.search(p) else 'scaffold' if SCAFFOLD_PATH.search(p) else 'app' for p in paths}
    if kinds == {'scaffold', 'app'} and any(ENTRY_FILE.search(p) for p in paths):
        return 'app'
    return kinds.pop() if len(kinds) == 1 else 'mixed'


# A step that owns nothing but the defect-injection runner is not model-written: the driver supplies that file (parallel-provided.sh),
# so folding it into another worker would make a model write what the driver already provides. Same test as parallel-implement.sh.
RUNNER_NAMES = {'run', 'runner', 'mutate', 'run-mutations', 'run_mutations', 'runmutations', 'mutation-runner', 'mutation_runner',
                'run-defects', 'defect-runner', 'run-injections', 'inject'}


def provided_runner(paths):
    paths = [p.strip() for p in paths if p and p.strip()]
    if len(paths) != 1:
        return False
    match = re.match(r'^(?:.*/)?([^/]+)\.m?js$', paths[0])
    return bool(match and match.group(1).lower() in RUNNER_NAMES and re.search(r'mutat|defect|inject', paths[0].lower()))


MUTATION_PATH = re.compile(r'mutat|defect-inject', re.I)


def wave_rank(paths):
    """0 = scaffold and application source, 1 = tests, 2 = the defect-injection list.

    Tests and the mutation list are written to match code they must name exactly: a selector, an export, a find string
    that has to occur once in a source file. Written beside that code by workers that cannot see it, they disagree with it
    (live: six of nine injection patches matched zero or two times, and the digit limit no step owned was never built), and
    a repair pass was then needed every run. Running them after the source lets them read what they test."""
    paths = {p for p in paths if p}
    if not paths or '*' in paths:
        return 0
    if all(MUTATION_PATH.search(p) for p in paths):
        return 2
    if all(TEST_PATH.search(p) for p in paths):
        return 1
    return 0


# The step that owns the package manifest is the scaffold, whatever else it owns: it declares the dependencies and the test runner's
# configuration every other step's checks depend on. Recognizing it by its other files was fragile (live run 12: it also owned
# `vitest.setup.js`, which the scaffold pattern does not match, so it was not separated and the module workers ran their own tests
# with no dependencies installed and no test configuration, and passed in an environment the real project does not have).
MANIFEST = re.compile(r'(^|/)(package\.json|pyproject\.toml|Cargo\.toml|go\.mod|Gemfile|composer\.json)$')


def owns_manifest(paths):
    return any(MANIFEST.search(p) for p in paths if p)


def is_module(paths):
    """A vertical module: one step that owns application source and its own tests (and usually its styles and a contract).

    Such a step is not a layer. Its worker writes code and the tests for that code together, so it can run those tests itself, and
    nothing it owns waits on another worker's files except through a declared contract. Scaffold files alone, tests alone, `*` and a
    step that declares nothing are not modules."""
    paths = {p for p in paths if p}
    if not paths or '*' in paths:
        return False
    has_tests = any(TEST_PATH.search(p) for p in paths)
    has_source = any(not TEST_PATH.search(p) and not SCAFFOLD_PATH.search(p) for p in paths)
    return has_tests and has_source


def waves_enabled():
    return os.environ.get('WORKFLOW_IMPLEMENT_TEST_WAVES', '1') == '1'


def waves(groups, owned):
    """Split each parallel group into consecutive waves by `wave_rank`, so a step that checks code runs after the code.

    WORKFLOW_IMPLEMENT_TEST_WAVES=0 restores one concurrent group. Steps that mix roles, own `*` or declare nothing stay in wave 0."""
    if not waves_enabled():
        return groups
    out = []
    for g in groups:
        # A module worker runs its own tests, which needs the dependencies the scaffold declares: with modules in the group the
        # scaffold lands first, alone, so the driver can install before they start. Without modules it stays beside the source.
        modules = any(is_module(owned.get(s, ())) for s in g)
        ranks = {s: -1 if modules and (role(owned.get(s, ())) == 'scaffold' or owns_manifest(owned.get(s, ()))) else
                 wave_rank(owned.get(s, ())) for s in g}
        out.extend([s for s in g if ranks[s] == r] for r in sorted(set(ranks.values())))
    return out


MERGE_MODES = ('0', '1', '2')


def merge_mode():
    mode = os.environ.get('WORKFLOW_IMPLEMENT_MERGE_APP', '1').strip()
    return mode if mode in MERGE_MODES else '1'


def merge_map(owned, group):
    """{primary: [absorbed, ...]}: the steps of one parallel group that a single worker writes.

    WORKFLOW_IMPLEMENT_MERGE_APP: 0 = every step its own worker (the old fan-out); 1 (the default) = application steps share one worker while scaffold and test steps stay independent;
    2 = two workers: one for the application's source, one for everything that builds and verifies it (scaffold,
    config, tests, the defect-injection list). Both halves were failing at their seams: a stylesheet written without the
    component's class names, a `package.json` without the packages the tests import, an include glob that matched no test, a
    mutation list naming tests that do not exist. Tests stay out of the application's worker so that nobody checks code against
    tests it wrote itself.

    A step that mixes roles, declares nothing or owns `*`, and the driver-supplied mutation runner, stay on their own. A unit of
    fewer than two steps has nothing to merge.
    """
    mode = merge_mode()
    if mode == '0':
        return {}
    roles = {step: role(owned.get(step, ())) for step in group}
    units = [[s for s in group if roles[s] == 'app']]
    if mode == '2':
        units.append([s for s in group if roles[s] in ('test', 'scaffold') and not provided_runner(owned.get(s, ()))])
    return {unit[0]: unit[1:] for unit in units if len(unit) > 1}


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


def merge_map_main(plan, group):
    lib = Path(__file__).resolve().parent
    rows = subprocess.run(['bash', '-c', '. "%s/plan-scope.sh"; plan_step_owns "%s"' % (lib, plan)],
                          capture_output=True, text=True).stdout.splitlines()
    print(json.dumps({str(k): v for k, v in merge_map(owns(rows), [int(n) for n in group]).items()}))
    return 0


def load_plan(plan):
    """(steps, owned, deps) as the plan declares them."""
    lib = Path(__file__).resolve().parent

    def sh(fn):
        return subprocess.run(['bash', '-c', '. "$1/plan-scope.sh"; "$2" "$3"', 'step-groups', str(lib), fn, str(plan)],
                              capture_output=True, text=True, check=True).stdout.splitlines()

    sys.path.insert(0, str(lib))
    from plan_records import load, step_data
    model = load(plan)
    if model is not None:
        return step_data(model)
    return [s for s in sh('plan_steps') if s.strip()], owns(sh('plan_step_owns')), depends(sh('plan_step_depends'))


def writes_source(paths):
    """True when a step owns at least one application source file: not a test, not scaffold, not `*`. Such a wave can be built."""
    return any(p and p != '*' and not TEST_PATH.search(p) and not SCAFFOLD_PATH.search(p) for p in paths)


def has_source_main(plan, steps):
    """One line per requested step: 1 when it owns application source, else 0."""
    _, owned, _ = load_plan(plan)
    for step in steps:
        print(1 if writes_source(owned.get(int(step), ())) else 0)
    return 0


def module_step_main(plan, steps):
    """One line per requested step: 1 when it is a vertical module and waves are on, else 0."""
    _, owned, _ = load_plan(plan)
    for step in steps:
        print(1 if waves_enabled() and is_module(owned.get(int(step), ())) else 0)
    return 0


def has_module_main(plan, _steps):
    """1 when any step of the plan is a vertical module (owns application source and its own tests), else 0."""
    _, owned, _ = load_plan(plan)
    print(1 if any(is_module(paths) for paths in owned.values()) else 0)
    return 0


def wave_rank_main(plan, steps):
    """One rank per requested step, one per line: 0 source and scaffold, 1 tests, 2 the defect-injection list."""
    _, owned, _ = load_plan(plan)
    for step in steps:
        print(wave_rank(owned.get(int(step), ())))
    return 0


def main():
    if sys.argv[1:2] == ['merge-map']:
        return merge_map_main(sys.argv[2], sys.argv[3:])
    if sys.argv[1:2] == ['wave-rank']:
        return wave_rank_main(sys.argv[2], sys.argv[3:])
    if sys.argv[1:2] == ['has-source']:
        return has_source_main(sys.argv[2], sys.argv[3:])
    if sys.argv[1:2] == ['has-module']:
        return has_module_main(sys.argv[2], sys.argv[3:])
    if sys.argv[1:2] == ['module-step']:
        return module_step_main(sys.argv[2], sys.argv[3:])
    plan, root = sys.argv[1], sys.argv[2]
    steps, owned, deps = load_plan(plan)
    total = len(steps)
    ignore_deps = os.environ.get('WORKFLOW_IMPLEMENT_IGNORE_DEPENDS', '1') == '1'
    groups = waves(group(total, owned, deps, ignore_deps), owned) if total else []
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
        'merged_steps': {str(k): v for g in groups for k, v in merge_map(owned, g).items()},
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
