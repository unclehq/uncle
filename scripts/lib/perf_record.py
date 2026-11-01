#!/usr/bin/env python3
"""One atomic record per completed model attempt: what performance.sh's perf_record did with jq, mktemp, date, usage-cost.py and
session-totals.py (six or seven processes) in one.

    perf_record.py STATE_DIR KIND STAGE ELAPSED STATUS LOG RUNNER MODEL EFFORT WORKFLOW_STATE RUN_ID SPECULATIVE

ELAPSED, STATUS and SPECULATIVE are JSON values, as they were for `jq --argjson`; a value that is not JSON drops the record, as the
failed jq did. Observability must not change the outcome of a workflow: every failure is silent and the exit status is always 0.
The record keeps the old shape and key order, and is published as metrics/.pending.XXXXXX.json.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

TOKENS_USED = re.compile(r'tokens used[\r\n ]+([0-9,]+)')


def alt(*values):
    """jq's `a // b // c`: the first value that is neither null nor false (0 and "" count as present)."""
    for value in values:
        if value is not None and value is not False:
            return value
    return values[-1]


def number(value):
    """jq prints an integral float without the .0."""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def results_of(text):
    found = []
    for line in text.split('\n'):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('type') == 'result':
            found.append(row)
    return found


def field(row, name):
    """`$r.name` for a row that may be missing: null when absent; a value that cannot be indexed is jq's error."""
    if row is None:
        return None
    if not isinstance(row, dict):
        raise TypeError('cannot index ' + type(row).__name__)
    return row.get(name)


def build(kind, stage, elapsed, status, log, runner, model, effort, state, run_id, speculative, text, ended):
    results = results_of(text)
    r = results[-1] if results else {}
    totals = [int(m.group(1).replace(',', '')) for m in TOKENS_USED.finditer(text)]
    usage = field(r, 'usage')
    return {
        'schema': 1, 'kind': kind, 'stage': stage, 'workflow_state': state, 'run_id': run_id,
        'runner': runner, 'model': alt(field(r, 'model'), model), 'effort': effort, 'speculative': speculative,
        'ended_at': ended, 'started_at': number(ended - elapsed), 'elapsed_seconds': elapsed,
        'process_exit': status, 'reported_error': field(r, 'is_error'),
        'turns': alt(field(r, 'num_turns'), None), 'input_tokens': alt(field(usage, 'input_tokens'), None),
        'output_tokens': alt(field(usage, 'output_tokens'), None),
        'reported_total_tokens': alt(field(usage, 'total_tokens'), totals[-1] if totals else None, None),
        'cache_read_tokens': alt(field(usage, 'cache_read_input_tokens'), field(usage, 'cached_input_tokens'), None),
        'cache_write_tokens': alt(field(usage, 'cache_creation_input_tokens'), field(usage, 'cache_write_input_tokens'), None),
        'reported_cost_usd': alt(field(r, 'total_cost_usd'), None),
        'usage_scope': alt(field(r, 'usage_scope'), 'last reported result'),
        'usage_source': alt(field(r, 'usage_source'), None),
        'input_includes_cache': alt(field(r, 'input_includes_cache'), False),
        'log': log,
    }


def load_sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(state_dir, kind, stage, elapsed, status, log, runner, model, effort, state, run_id, speculative):
    elapsed, status, speculative = (json.loads(v) for v in (elapsed, status, speculative))
    metrics = Path(state_dir) / 'metrics'
    metrics.mkdir(parents=True, exist_ok=True)
    path = Path(log) if log and Path(log).is_file() else None
    text = path.read_bytes().decode('utf-8', 'replace') if path else ''
    row = build(kind, stage, elapsed, status, str(path) if path else '/dev/null', runner, model, effort, state, run_id,
                speculative, text, int(time.time()))
    try:
        row = load_sibling('usage-cost').enrich(row)
    except Exception as error:
        print(f'usage-cost: {error}', file=sys.stderr)
    handle, temporary = tempfile.mkstemp(prefix='.pending.', dir=metrics)
    with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as out:
        out.write(json.dumps(row, separators=(',', ':'), ensure_ascii=False) + '\n')
    os.replace(temporary, temporary + '.json')
    try:
        load_sibling('session-totals').update(state_dir)
    except Exception as error:
        print(f'session-totals: {error}', file=sys.stderr)


if __name__ == '__main__':
    try:
        if len(sys.argv) == 13:
            record(*sys.argv[1:])
    except Exception as error:      # a dropped record is acceptable; a failed workflow is not
        print(f'perf_record: {error}', file=sys.stderr)
    sys.exit(0)
