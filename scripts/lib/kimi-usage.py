"""Recover provider token counts from a uniquely matched local Kimi session."""
import hashlib
import json
import os
from pathlib import Path
import sys


def states(root, cwd):
    result = []
    for path in root.glob('*/*/state.json'):
        try:
            data = json.loads(path.read_text())
            if Path(data['cwd']).resolve() == Path(cwd).resolve():
                result.append(path.parent)
        except (OSError, ValueError, KeyError):
            continue
    return result


def events(path):
    try:
        with path.open() as stream:
            for line in stream:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue  # A killed attempt may end with a partial line.
    except OSError:
        return


def prompt_hash(event):
    value = event.get('input')
    if isinstance(value, list) and all(x.get('type') == 'text' for x in value if isinstance(x, dict)):
        value = ''.join(x.get('text', '') for x in value)
    if not isinstance(value, str):
        return None
    return hashlib.sha256(value.rstrip('\n').encode()).hexdigest()


def summary(session):
    rows = []
    for wire in (session / 'agents').glob('*/wire.jsonl'):
        rows.extend(e for e in events(wire) if e.get('type') == 'usage.record' and e.get('usageScope') == 'turn')
    if not rows:
        return {}
    mapping = {'inputOther': 'input_tokens', 'output': 'output_tokens',
               'inputCacheRead': 'cache_read_input_tokens', 'inputCacheCreation': 'cache_creation_input_tokens'}
    if any(any(not isinstance(r.get('usage', {}).get(k), int) or r['usage'][k] < 0 for k in mapping) for r in rows):
        return {}
    models = {r.get('model') for r in rows}
    return {'model': next(iter(models)) if len(models) == 1 else '',
            'usage': {v: sum(r['usage'][k] for r in rows) for k, v in mapping.items()},
            'total_cost_usd': None, 'usage_scope': 'sum of session usage.record turn events',
            'usage_source': str(session), 'input_includes_cache': False,
            'usage_reports': len(rows)}


def collect(root, cwd, snapshot):
    candidates = []
    for session in states(root, cwd):
        if str(session) in snapshot['existing']:
            continue
        prompts = [e for e in events(session / 'agents/main/wire.jsonl') if e.get('type') == 'turn.prompt']
        if len(prompts) == 1 and prompt_hash(prompts[0]) == snapshot['prompt_sha256']:
            candidates.append(session)
    return summary(candidates[0]) if len(candidates) == 1 else {}


if __name__ == '__main__':
    root = Path(os.environ.get('WORKFLOW_KIMI_SESSIONS_DIR', str(Path.home() / '.kimi-code/sessions')))
    mode, filename = sys.argv[1:3]
    try:
        if mode == 'snapshot':
            snapshot = {'existing': [str(s) for s in states(root, Path.cwd())],
                        'prompt_sha256': hashlib.sha256(sys.stdin.read().rstrip('\n').encode()).hexdigest()}
            Path(filename).write_text(json.dumps(snapshot))
        else:
            print(json.dumps(collect(root, Path.cwd(), json.loads(Path(filename).read_text()))))
    except (OSError, ValueError, KeyError, TypeError):
        if mode != 'snapshot':
            print('{}')
