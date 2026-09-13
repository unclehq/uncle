"""Usage attribution for timing spans; no token estimates from elapsed time."""
import importlib.util
import math
from pathlib import Path

FIELDS = ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens')
_spec = importlib.util.spec_from_file_location('timing_prices', Path(__file__).with_name('usage-cost.py'))
_prices = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prices)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def priced(row):
    row = dict(row)
    for key in (*FIELDS, 'reported_cost_usd', 'estimated_cost_usd'):
        if not number(row.get(key)):
            row[key] = None
    values = [row[key] for key in FIELDS]
    if row.get('input_includes_cache') and number(row['input_tokens']) and number(row['output_tokens']):
        computed_total = row['input_tokens'] + row['output_tokens']
    else:
        computed_total = sum(values) if all(number(v) for v in values) else None
    if computed_total is None and number(row.get('reported_total_tokens')):
        computed_total = row['reported_total_tokens']
    if not number(row.get('total_tokens')):
        row['total_tokens'] = computed_total
    if row['estimated_cost_usd'] is None:
        try:
            estimate = _prices.enrich(dict(row, reported_cost_usd=None))
            for key in ('estimated_cost_usd', 'pricing_source', 'pricing_rates', 'pricing_unit', 'pricing_checked_at'):
                if key in estimate:
                    row[key] = estimate[key]
        except (OSError, ValueError, TypeError):
            pass  # Missing/bad pricing cannot affect the build.
    return row


def combine(rows):
    # Models can have different cache semantics and rates; price before summing.
    rows = [priced(row) for row in rows]
    result = {}
    for field in (*FIELDS, 'total_tokens', 'reported_cost_usd', 'estimated_cost_usd'):
        known = [row[field] for row in rows if number(row.get(field))]
        result[field] = sum(known) if known else None
        result[field + '_coverage'] = f'{len(known)}/{len(rows)}'
    result['models'] = sorted({row.get('model', '') for row in rows})
    result['pricing_sources'] = sorted({row['pricing_source'] for row in rows if row.get('pricing_source')})
    return result


def attribute(spans):
    samples = [priced(row) for row in spans if row['kind'] == 'model_usage']
    for index, row in enumerate(spans):
        row = priced(row)
        row.setdefault('usage_scope', 'unavailable for this part')
        candidates = []
        if row['kind'] == 'model_usage':
            row['usage_scope'] = 'runner-reported usage increment'
        elif row['kind'] in ('agent', 'reviewer'):
            row['usage_scope'] = 'runner-reported attempt total'
        elif row['kind'] in ('workflow_stage', 'runner_observation', 'checklist_item', 'tool_call',
                             'runner_event_gap', 'runner_tail_gap', 'runner_first_response'):
            begin = row['started_at']; end = begin + row['elapsed_seconds']
            for sample in samples:
                observed = sample.get('observed_at', sample['started_at'] + sample['elapsed_seconds'])
                if row.get('attempt_id') and row['attempt_id'] != sample.get('attempt_id'):
                    continue
                if begin <= observed < end:
                    candidates.append(sample)
            if candidates:
                row.update(combine(candidates))
                row['usage_scope'] = ('runner-reported attempt total' if row['kind'] == 'runner_observation'
                                      else 'shared usage reported during interval; not exclusive attribution')
        spans[index] = row
    return spans
