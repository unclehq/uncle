#!/usr/bin/env python3
"""Classify a plan so the build can spend review effort where it matters.

A small change does not need four review lenses and nineteen one-finding edit writers; a change that touches signing,
publication or approval does. The driver computes cheap deterministic *features* of the plan (owned files, step and
criterion counts, risk keywords), a model proposes a class and a review profile from them, and the driver *clamps* that
proposal to a safety floor before anything uses it:

  * the class can only be raised above what the features say, never lowered;
  * `requirements` and `regression` always run, `security` runs when any risk keyword matched, and `testability` runs
    whenever there are acceptance criteria, test files or an application build;
  * standard, large and risky plans always get every lens -- the model may only trim the lenses of docs, test-only and small
    changes, and never below the floor;
  * the edit-writer slice (findings per writer) is bounded, and is at most 2 for anything standard or larger.

The model is optional. A runner that fails, answers badly or is disabled gets the deterministic profile, so this stage can
never stop a build. It works for any runner because the answer is read from a delivery file *or* from the runner's final
text; nothing here depends on one runner's output protocol.

    change_class.py features FAMILY PROJECT PLAN
    change_class.py prompt   FAMILY PROJECT PLAN OUT TEMPLATE
    change_class.py finish   FAMILY PROJECT PLAN DELIVERY [LOG]     # validate, clamp, write change-class.json
    change_class.py fallback FAMILY PROJECT PLAN                    # deterministic profile only
    change_class.py owned    FAMILY PROJECT PLAN                    # the files the plan says it will change
    change_class.py force    FAMILY PROJECT PLAN CLASS               # WORKFLOW_CHANGE_CLASS
    change_class.py current  FAMILY PROJECT PLAN                    # exit 0 when change-class.json matches this plan
    change_class.py get      PROJECT KEY [DEFAULT]                  # class | lenses | edit_slice | source
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

LENSES = ('requirements', 'regression', 'security', 'testability')
CLASSES = ('docs', 'test-only', 'small', 'standard', 'large', 'risky')
REDUCIBLE = ('docs', 'test-only', 'small')          # the only classes whose lens set the model may trim
SLICE_BY_CLASS = {'docs': 8, 'test-only': 6, 'small': 4, 'standard': 2, 'large': 2, 'risky': 2}
# How much of the test suite the final check runs (scripts/lib/test_scope.py): impacted tests only, the full suite, or ask the
# operator. Never the model's call: it follows from the class, and only a change request has an existing suite to scope.
TEST_SCOPE = {'docs': 'impacted', 'test-only': 'impacted', 'small': 'impacted', 'standard': 'ask', 'large': 'full', 'risky': 'full'}
OUTPUT = Path('.uncle/workflow/change-class.json')

# Matched against what the *request* says and which files the plan touches, never against the plan's own prose: a plan carries
# boilerplate (test strategy, concurrency notes, CSS design "tokens", Uncle's own "waiver" vocabulary) that mentions these words
# in a calculator as much as in a signing service, and counting them made every plan "risky" and the classifier a no-op.
RISK = re.compile(
    r'(?i)\b(secur\w*|auth(?:entication|orization|orize)?|password\w*|secret\w*|(?:api|access|auth|bearer|csrf|session|oauth|'
    r'personal access)[ -]?tokens?|credential\w*|encrypt\w*|crypto\w*|signing|signature\w*|gpg|permission\w*|privilege\w*|'
    r'sandbox\w*|sql injection|command injection|code injection|prompt injection|sanitiz\w*|redact\w*|payment\w*|billing|'
    r'delet\w+|destroy\w*|migrat\w+|race condition|deadlock|publish\w*|approval gate|attest\w*|force[- ]push)\b')

TEST_PATH = re.compile(r'(^|/)(tests?|e2e|specs?|__tests__|cypress)(/|$)|\.(test|spec)\.[A-Za-z]+$|[-_]test\.[A-Za-z]+$', re.I)
DOC_PATH = re.compile(r'(^|/)(docs?|documentation)/|\.(md|markdown|txt|rst)$|(^|/)(README|CHANGELOG|LICENSE)[^/]*$', re.I)
SCAFFOLD_PATH = re.compile(r'(^|/)(package(-lock)?\.json|pyproject\.toml|requirements\.txt|\.gitignore|\.github/.*|'
                           r'[^/]*\.config\.[cm]?[jt]s|tsconfig[^/]*\.json|\.env[^/]*)$', re.I)


def digest(text):
    return hashlib.sha256(text.encode('utf-8', 'replace')).hexdigest()


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def request_text(family, project):
    project = Path(project)
    names = (['CHANGE_REQUEST.md', '.uncle/docs/CHANGE_REQUEST.md'] if family == 'change'
             else ['.uncle/docs/REQUIREMENTS.md', 'REQUIREMENTS.md'])
    for name in names:
        text = _read(project / name)
        if text.strip():
            return text
    return ''


def plan_steps_and_owns(plan):
    """Steps and owned paths, from the driver's own plan parser (the same one implementation grouping uses)."""
    lib = Path(__file__).resolve().parent
    if not Path(plan).is_file():
        return 0, []

    def run(function):
        done = subprocess.run(['bash', '-c', '. "%s/plan-scope.sh"; %s "%s"' % (lib, function, plan)],
                              capture_output=True, text=True)
        return [line for line in done.stdout.splitlines() if line.strip()]

    steps = run('plan_steps')
    owned = set()
    for row in run('plan_step_owns'):
        _, _, path = row.partition('\t')
        path = path.strip().strip('`')
        if path and path != '*':
            owned.add(path)
    return len(steps), sorted(owned)


def kind_of(path):
    if TEST_PATH.search(path):
        return 'test'
    if DOC_PATH.search(path):
        return 'docs'
    if SCAFFOLD_PATH.search(path):
        return 'scaffold'
    return 'app'


def criteria_count(project):
    try:
        spec = json.loads(_read(Path(project) / '.uncle/workflow/documents/CHANGE_SPEC.json'))
        return len(spec.get('acceptance_criteria') or [])
    except ValueError:
        return 0


def criteria_text(family, project):
    if family != 'change':
        return ''
    try:
        spec = json.loads(_read(Path(project) / '.uncle/workflow/documents/CHANGE_SPEC.json'))
    except ValueError:
        return ''
    return '\n'.join('%s %s' % (row.get('criterion', ''), row.get('verification', ''))
                     for row in spec.get('acceptance_criteria') or [] if isinstance(row, dict))


def features(family, project, plan):
    request = request_text(family, project)
    plan_text = _read(plan)
    steps, owned = plan_steps_and_owns(plan)
    kinds = {'test': 0, 'docs': 0, 'scaffold': 0, 'app': 0}
    for path in owned:
        kinds[kind_of(path)] += 1
    hits = sorted({m.group(1).lower() for m in RISK.finditer(request + '\n' + criteria_text(family, project) + '\n' + '\n'.join(owned))})
    directories = {path.rsplit('/', 1)[0] if '/' in path else '' for path in owned}
    return {
        'family': family, 'request_chars': len(request), 'plan_chars': len(plan_text), 'steps': steps,
        'owned_files': len(owned), 'directories': len(directories), 'file_kinds': kinds,
        'criteria': criteria_count(project) if family == 'change' else 0, 'risk_hits': hits[:12],
        'owned_sample': owned[:12], 'plan_sha': digest(plan_text),
    }


def deterministic_class(f):
    if f['risk_hits']:
        return 'risky'
    kinds, files = f['file_kinds'], f['owned_files']
    if f['family'] == 'change' and files and kinds['docs'] == files:
        return 'docs'
    if f['family'] == 'change' and files and kinds['test'] == files:
        return 'test-only'
    if f['steps'] >= 7 or files >= 15 or f['directories'] >= 6:
        return 'large'
    if f['steps'] <= 2 and files <= 4 and f['criteria'] <= 4 and f['family'] == 'change':
        return 'small'
    return 'standard'


def required_lenses(f):
    need = {'requirements', 'regression'}
    if f['risk_hits']:
        need.add('security')
    if f['criteria'] or f['file_kinds']['test'] or f['family'] == 'app':
        need.add('testability')
    return need


def ordered(lenses):
    return [lens for lens in LENSES if lens in lenses]


def profile(cls, f, proposed=None):
    """The clamped profile for a class: the model's proposal can only add scrutiny or trim within the floor."""
    need = required_lenses(f)
    if cls in REDUCIBLE:
        chosen = set(need)
        if proposed:
            chosen |= {lens for lens in proposed.get('adversarial_lenses', []) if lens in LENSES}
        elif cls != 'docs':
            chosen.add('testability')
    else:
        chosen = set(LENSES)
    bound = SLICE_BY_CLASS[cls]
    wanted = (proposed or {}).get('edit_slice')
    size = bound if not isinstance(wanted, int) or isinstance(wanted, bool) else max(1, min(wanted, bound))
    if cls not in REDUCIBLE:
        size = min(size, 2)
    return {'adversarial_lenses': ordered(chosen), 'edit_slice': size,
            'test_scope': TEST_SCOPE[cls] if f['family'] == 'change' else 'full'}


def merge(cls_floor, cls_model):
    if cls_model not in CLASSES:
        return cls_floor
    return CLASSES[max(CLASSES.index(cls_floor), CLASSES.index(cls_model))]


def build(family, project, plan, proposal, source, note=''):
    f = features(family, project, plan)
    floor = deterministic_class(f)
    proposal = proposal if isinstance(proposal, dict) else None
    cls = merge(floor, proposal.get('class') if proposal else None)
    result = {
        'schema': 'uncle.artifact/v1', 'kind': 'change-class', 'family': family, 'class': cls, 'source': source,
        'floor_class': floor, **profile(cls, f, proposal),
        'rationale': str((proposal or {}).get('rationale') or note)[:300], 'features': f,
    }
    return result


def write(project, result):
    target = Path(project) / OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    temporary.replace(target)


def proposal_from(delivery, log=None):
    """The model's packet, from the delivery file or else the last JSON object in the runner's final text."""
    candidates = [_read(delivery)] if delivery else []
    if log:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            from runner_events import texts
            for line in reversed(_read(log).splitlines()):
                try:
                    candidates.extend(reversed(list(texts(json.loads(line)))))
                except (ValueError, TypeError):
                    continue
        except ImportError:
            pass
    for text in candidates:
        for chunk in [text] + re.findall(r'\{.*\}', text, re.S):
            try:
                payload = json.loads(chunk.strip().strip('`'))
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get('kind') == 'change-class':
                return payload
    return None


PROMPT_FOOTER = '''

## Features computed by the driver

```json
%s
```

## Your answer

Reply with one JSON object and nothing else. If you can write files, also write the same object to the delivery path.

`{"schema":"uncle.artifact/v1","kind":"change-class","class":"docs|test-only|small|standard|large|risky","adversarial_lenses":["requirements","regression","security","testability"],"edit_slice":2,"rationale":"one sentence"}`

The driver clamps your answer: it can raise the class but never lower it below the features, it always keeps the lenses the
features require, and it gives every standard, large or risky plan all four lenses. Trim lenses and raise `edit_slice` only
for a genuinely small, low-risk change.
'''


def prompt(family, project, plan, out, template):
    f = features(family, project, plan)
    request = request_text(family, project)[:3500]
    body = _read(template) + '\n\n## The request\n\n' + request + PROMPT_FOOTER % json.dumps(f, indent=2)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(body, encoding='utf-8')


def get(project, key, default=''):
    try:
        data = json.loads(_read(Path(project) / OUTPUT))
    except ValueError:
        data = {}
    value = data.get({'lenses': 'adversarial_lenses'}.get(key, key))
    if value in (None, '', []):
        return default
    return ' '.join(value) if isinstance(value, list) else str(value)


def main(argv):
    command = argv[1] if len(argv) > 1 else ''
    if command == 'features' and len(argv) == 5:
        print(json.dumps(features(*argv[2:5]), indent=2))
    elif command == 'prompt' and len(argv) == 7:
        prompt(*argv[2:7])
    elif command == 'finish' and len(argv) in (6, 7):
        family, project, plan, delivery = argv[2:6]
        proposal = proposal_from(delivery, argv[6] if len(argv) == 7 else None)
        result = build(family, project, plan, proposal, 'model' if proposal else 'fallback',
                       '' if proposal else 'the classifier gave no usable answer; deterministic profile')
        write(project, result)
        print('%s (%s): lenses=%s edit_slice=%s' % (result['class'], result['source'],
                                                  ','.join(result['adversarial_lenses']), result['edit_slice']))
    elif command == 'fallback' and len(argv) == 5:
        family, project, plan = argv[2:5]
        result = build(family, project, plan, None, 'fallback', 'deterministic profile')
        write(project, result)
        print('%s (fallback): lenses=%s edit_slice=%s' % (result['class'], ','.join(result['adversarial_lenses']),
                                                        result['edit_slice']))
    elif command == 'owned' and len(argv) == 5:
        for path in plan_steps_and_owns(argv[4])[1]:
            print(path)
    elif command == 'force' and len(argv) == 6:
        family, project, plan, cls = argv[2:6]
        if cls not in CLASSES:
            print('unknown class %r; expected one of %s' % (cls, ', '.join(CLASSES)), file=sys.stderr)
            return 2
        result = build(family, project, plan, {'class': cls, 'rationale': 'forced by WORKFLOW_CHANGE_CLASS'}, 'forced')
        write(project, result)
        print('%s (forced): lenses=%s edit_slice=%s' % (result['class'], ','.join(result['adversarial_lenses']),
                                                      result['edit_slice']))
    elif command == 'current' and len(argv) == 5:
        family, project, plan = argv[2:5]
        try:
            stored = json.loads(_read(Path(project) / OUTPUT))
        except ValueError:
            return 1
        return 0 if stored.get('features', {}).get('plan_sha') == digest(_read(plan)) else 1
    elif command == 'get' and len(argv) in (4, 5):
        print(get(argv[2], argv[3], argv[4] if len(argv) == 5 else ''))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
