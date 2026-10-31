#!/usr/bin/env python3
"""Read scheduling and scope records without parsing the rendered approval view.

Exit 3 means there are no typed records yet; shell readers then use their
legacy Markdown parser. Invalid canonical data is an error, never a fallback.
"""
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_model as pm


def canonical_path(plan, state_dir=None):
    plan = Path(plan)
    if plan.suffix == '.json':
        return plan if plan.is_file() else None
    candidates = []
    state = state_dir or os.environ.get('STATE_DIR')
    if state:
        candidates.append(Path(state) / 'documents' / (plan.stem + '.json'))
    resolved = plan.resolve()
    if resolved.parent.name == 'docs' and resolved.parent.parent.name == '.uncle':
        candidates.append(resolved.parent.parent / 'workflow/documents' / (plan.stem + '.json'))
    candidates.extend([plan.with_suffix('.json'), plan.parent / '.uncle/workflow/documents' / (plan.stem + '.json')])
    return next((p for p in candidates if p.is_file()), None)


def load(plan, state_dir=None):
    if not pm.records_enabled():
        return None
    path = canonical_path(plan, state_dir)
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding='utf-8'))
    if 'sections' in payload:
        return pm.model_of(payload)
    if not pm.sidecar(path).is_file():
        return None
    # Old sidecars are usable only while they still describe this narrative.
    model = json.loads(pm.sidecar(path).read_text(encoding='utf-8'))
    if Counter(pm.words(pm.render(model))) != Counter(pm.words(payload.get('narrative') or '')):
        return None
    return pm.with_protected(model, payload)


def step_data(model):
    errors, _ = pm.validate(model, root=None)
    if errors:
        raise pm.PlanError(errors[0])
    steps = pm.steps_of(model)
    positions = {step['number']: n for n, step in enumerate(steps, 1)}
    owned = {n: set(step['owns']) for n, step in enumerate(steps, 1)}
    deps = {n: {positions[d] for d in step['depends_on']} for n, step in enumerate(steps, 1)}
    return steps, owned, deps


def scope_files(model):
    paths = set()
    found = False
    for section in model['sections']:
        for block in section['blocks']:
            if block.get('row_kind') != 'change_impact':
                continue
            found = True
            for row in block['rows']:
                for field in ('component', 'coverage'):
                    value = row.get(field, '')
                    tokens = re.findall(r'`([^`]+)`', value) or re.split(r'[,\n]', value)
                    for token in tokens:
                        token = token.strip().split(' ', 1)[0]
                        if pm.valid_path(token) and ('/' in token or '.' in token or Path(token).is_file()):
                            paths.add(token)
    return sorted(paths) if found else None


def lines(model, field):
    if field == 'scope':
        return scope_files(model) or []
    steps, owned, deps = step_data(model)
    if field == 'owns':
        return ['%d\t%s' % (n, path) for n, paths in owned.items() for path in sorted(paths)]
    if field == 'depends':
        return ['%d\t%d' % (n, dep) for n, refs in deps.items() for dep in sorted(refs)]
    if field == 'steps':
        # Keep the task text the shell callers expect, but take fields from records.
        tasks = [dict(step, title='Step %s: %s' % (step['label'], step['title'])) if step.get('_heading') else step
                 for step in steps]
        return [re.sub(r'^\d+\.\s*', '', pm.render_block({'kind': 'steps', 'items': [step]}).splitlines()[0])
                for step in tasks]
    raise ValueError('unknown record field: ' + field)


def main(argv):
    try:
        if argv[0] == 'text':
            path = canonical_path(argv[1], argv[2] if len(argv) > 2 and argv[2] else None)
            if path is None:
                return 3
            payload = json.loads(path.read_text(encoding='utf-8'))
            if 'narrative' not in payload:
                return 3
            if not isinstance(payload['narrative'], str):
                raise ValueError('narrative must be text')
            print(payload['narrative'])
            return 0
        model = load(argv[1], argv[2] if len(argv) > 2 and argv[2] else None)
        if model is None and argv[0] in ('steps', 'owns', 'depends'):
            path = canonical_path(argv[1], argv[2] if len(argv) > 2 and argv[2] else None)
            narrative = (json.loads(path.read_text(encoding='utf-8')).get('narrative', '') if path else
                         Path(argv[1]).read_text(encoding='utf-8') if Path(argv[1]).is_file() else '')
            # Existing Markdown forms keep their established awk reader. Only
            # forms it cannot represent need the shared heading-step records.
            new_form = (re.search(r'^(?:#|#{3,6})\s+(?:\d+\.\s*)?Implementation (?:order|steps|sequence)\b', narrative, re.M | re.I)
                        or re.search(r'^#{1,6}\s+(?:Step\s+)?\d+[a-z]+[:.)-]', narrative, re.M | re.I)
                        or re.search(r'^##\s+Step\s+\d+[:.)-]', narrative, re.M | re.I))
            if new_form and pm.heading_steps(narrative):
                model = pm.import_markdown(narrative)
        result = lines(model, argv[0]) if model is not None else None
        if result is None:
            return 3
        for line in result:
            print(line)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('plan records: %s' % error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
