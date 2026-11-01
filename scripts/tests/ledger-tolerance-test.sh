#!/usr/bin/env bash
set -euo pipefail
# SB9: historical ledger rows with a removed Cline runner must still parse, and
# must not change the figures computed for the remaining runners.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
python3 - "$TMP" <<'PY'
import json, os, sys
d = sys.argv[1]
def row(runner, model, i, o, cr, cw, inc):
    return dict(kind='agent', stage='implementation', runner=runner, model=model, input_tokens=i,
                output_tokens=o, cache_read_tokens=cr, cache_write_tokens=cw,
                input_includes_cache=inc, elapsed_seconds=10, attempts=1)
base = [row('claude', 'claude-x', 1000, 200, 300, 50, False), row('codex', 'gpt-x', 2000, 400, 500, 0, True),
        row('kimi', 'moonshot-ai/kimi-k3', 3000, 600, 100, 20, False), row('self-hosted', 'local/m', 500, 50, 0, 0, False)]
old = row('/x/scripts/agent-cline.sh', 'cline-pass/m', 900, 90, 300, 0, False)
for name, rows in (('with', base + [old]), ('without', base)):
    m = os.path.join(d, name, '.uncle', 'workflow', 'metrics'); os.makedirs(m)
    for n, r in enumerate(rows): json.dump(r, open(os.path.join(m, '%d.json' % n), 'w'))
PY
for s in with without; do
    for f in "$TMP/$s/.uncle/workflow/metrics"/*.json; do python3 "$ROOT/scripts/lib/usage-cost.py" "$f"; done
    bash "$ROOT/scripts/performance-report.sh" "$TMP/$s" > "$TMP/$s.out"
done
for n in 0 1 2 3; do
    cmp -s "$TMP/with/.uncle/workflow/metrics/$n.json" "$TMP/without/.uncle/workflow/metrics/$n.json" \
        || { echo "FAIL: non-cline row $n changed"; exit 1; }
done
grep -q '^| agent | implementation | 4 |' "$TMP/without.out" || { echo "FAIL: baseline table missing"; exit 1; }
grep -q '^| agent | implementation | 5 |' "$TMP/with.out" || { echo "FAIL: legacy row not counted"; exit 1; }
echo "ledger-tolerance-test: ok"
