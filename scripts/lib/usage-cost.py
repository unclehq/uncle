"""Attach labeled token-price estimates; never represent estimates as invoices."""
import json
import math
import os
from pathlib import Path
import sys

# USD per million tokens, from the official Kimi pricing pages, verified
# 2026-09-09. The pages list cache-hit and cache-miss input prices only;
# cache writes bill as ordinary (cache-miss) input.
CHECKED = '2026-09-09'
SOURCES = {
    'moonshot-ai/kimi-k2.7-code': 'https://platform.kimi.ai/docs/pricing/chat-k27-code',
    'moonshot-ai/kimi-k2.7-code-highspeed': 'https://platform.kimi.ai/docs/pricing/chat-k27-code',
    'moonshot-ai/kimi-k3': 'https://platform.kimi.ai/docs/pricing/chat-k3',
}
RATES = {
    'moonshot-ai/kimi-k2.7-code': dict(input=0.95, output=4, cache_read=0.19, cache_write=0.95),
    'moonshot-ai/kimi-k2.7-code-highspeed': dict(input=1.9, output=8, cache_read=0.38, cache_write=1.9),
    'moonshot-ai/kimi-k3': dict(input=3, output=15, cache_read=0.3, cache_write=3),
}


def enrich(record):
    for field in ('estimated_cost_usd', 'pricing_source', 'pricing_rates', 'pricing_unit', 'pricing_checked_at'):
        record.pop(field, None)
    actual = record.get('reported_cost_usd')
    record['cost_status'] = 'reported' if actual is not None else 'unknown'
    if actual is not None:
        return record
    model = record.get('model', '')
    rates = RATES.get(model)
    source = SOURCES.get(model) if rates else None
    override = os.environ.get('WORKFLOW_PRICING_FILE')
    if override:
        custom = json.loads(Path(override).read_text())
        if model in custom:
            rates = custom[model]
            source = str(Path(override).resolve())
    keys = [('input', 'input_tokens'), ('output', 'output_tokens'),
            ('cache_read', 'cache_read_tokens'), ('cache_write', 'cache_write_tokens')]
    if not rates or any(record.get(field) is None for _, field in keys):
        return record
    if any(not isinstance(rates.get(k), (int, float)) or not math.isfinite(rates[k]) or rates[k] < 0 for k, _ in keys):
        raise ValueError('All four model rates must be finite nonnegative USD per million tokens')
    values = {k: record[field] for k, field in keys}
    # Codex/Cline input includes cache reads; Claude/Kimi use disjoint buckets.
    if record.get('input_includes_cache'):
        values['input'] -= values['cache_read'] + values['cache_write']
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in values.values()):
        return record
    record.update(estimated_cost_usd=sum(values[k] * rates[k] for k, _ in keys) / 1_000_000,
                  cost_status='estimated', pricing_source=source, pricing_rates=rates,
                  pricing_unit='USD per million tokens', pricing_checked_at=CHECKED if source in SOURCES.values() else None)
    return record


if __name__ == '__main__':
    path = Path(sys.argv[1])
    data = enrich(json.loads(path.read_text()))
    path.write_text(json.dumps(data) + '\n')
