#!/usr/bin/env python3
"""Backfill existing Kimi attempt metrics from unambiguous local session evidence."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / 'lib' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kimi = load('kimi-usage')
cost = load('usage-cost')


def backfill(project, apply=False):
    root = Path(os.environ.get('WORKFLOW_KIMI_SESSIONS_DIR', str(Path.home() / '.kimi-code/sessions')))
    sessions = []
    for session in kimi.states(root, project):
        prompts = [e for e in kimi.events(session / 'agents/main/wire.jsonl') if e.get('type') == 'turn.prompt']
        if len(prompts) == 1:
            sessions.append((session, prompts[0].get('time', 0) / 1000))
    count = 0
    for path in sorted((project / '.uncle/workspace/metrics').glob('*.json')):
        row = json.loads(path.read_text())
        if not row.get('runner', '').endswith(('agent-kimi.sh', 'reviewer-kimi.sh')) or row.get('usage_source'):
            continue
        start, end = row.get('started_at'), row.get('ended_at')
        if start is None or end is None:
            continue
        matches = [session for session, stamp in sessions if start - 2 <= stamp <= end]
        if len(matches) != 1:
            print(f'{path.name}: skipped ({len(matches)} matching sessions)')
            continue
        session = matches[0]
        # Do not assign tokens from a resumed/ongoing session to a finished attempt.
        if any(e.get('time', 0) > (end + 2) * 1000 for wire in (session / 'agents').glob('*/wire.jsonl')
               for e in kimi.events(wire) if e.get('type') == 'usage.record'):
            continue
        usage = kimi.summary(session)
        if not usage:
            continue
        row.update(model=usage['model'], reported_cost_usd=None,
                   input_tokens=usage['usage']['input_tokens'], output_tokens=usage['usage']['output_tokens'],
                   cache_read_tokens=usage['usage']['cache_read_input_tokens'],
                   cache_write_tokens=usage['usage']['cache_creation_input_tokens'],
                   usage_source=usage['usage_source'], usage_scope=usage['usage_scope'],
                   input_includes_cache=False)
        cost.enrich(row)
        if apply:
            backup = path.parent.parent / 'cost-backfill-originals' / path.name
            backup.parent.mkdir(exist_ok=True)
            if not backup.exists():
                shutil.copy2(path, backup)
            temp = path.with_suffix('.backfill-tmp')
            temp.write_text(json.dumps(row) + '\n')
            temp.replace(path)
        count += 1
        estimate = row.get('estimated_cost_usd')
        label = f'{estimate:.6f}' if estimate is not None else 'unknown'
        print(f"{row['stage']}: {row['input_tokens']} input + {row['output_tokens']} output; estimated USD {label}")
    print(f'{count} records {"updated" if apply else "recoverable (dry run)"}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    backfill(args.project.resolve(), args.apply)
