#!/usr/bin/env python3
"""Route a no-op source repair to plan revision when its own notes prove it is plan-owned."""
import argparse
import importlib.util
import json
from pathlib import Path


def blockers(notes):
    spec = importlib.util.spec_from_file_location('plan_executability', Path(__file__).with_name('plan-executability.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.blockers(notes)


def route(notes, classification, output):
    rows = [row for row in blockers(notes) if row.get('class') != 'CODING']
    if not rows:
        return False
    failed = []
    path = Path(classification)
    if path.is_file():
        for line in path.read_text(errors='replace').splitlines():
            status, _, command = line.partition('\t')
            if status == 'REGRESSION' and command:
                failed.append(command)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        'schema': 'uncle.artifact/v1', 'kind': 'repair-plan-revision',
        'source': 'green-check', 'blockers': rows, 'failed_commands': failed,
    }, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('notes'); parser.add_argument('classification'); parser.add_argument('output')
    args = parser.parse_args()
    raise SystemExit(0 if route(args.notes, args.classification, args.output) else 1)
