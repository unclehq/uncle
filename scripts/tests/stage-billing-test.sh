#!/usr/bin/env bash
# SB9: a historical ledger row with runner=cline and a clinepass billing field
# still parses and is counted through the generic path (no exception, no drop).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
mkdir -p "$TMP/p/.uncle/workflow/metrics"
M="$TMP/p/.uncle/workflow/metrics"
rec() { printf '{"kind":"agent","stage":"%s","elapsed_seconds":%s,"input_tokens":%s,"output_tokens":10,"cache_read_tokens":0,"cache_write_tokens":0,"reported_cost_usd":%s,"runner":"%s","billing":"%s"}\n' "$@"; }
rec implementation 5 100 0.5 scripts/agent-claude.sh none > "$M/1.json"
rec implementation 6 200 0.25 scripts/agent-codex.sh none > "$M/2.json"
rec historical-cline-row 7 300 0.125 scripts/agent-cline.sh clinepass > "$M/3.json"
# usage-cost.py on a historical cline row: exit 0, row kept, reported cost preserved
cp "$M/3.json" "$TMP/row.json"
python3 "$ROOT/scripts/lib/usage-cost.py" "$TMP/row.json" || fail 'usage-cost.py rejected historical cline row'
[[ "$(jq -r '.cost_status' "$TMP/row.json")" == reported ]] || fail 'cline row not aggregated as reported'
[[ "$(jq -r '.runner' "$TMP/row.json")" == scripts/agent-cline.sh ]] || fail 'row mutated'
out="$(bash "$ROOT/scripts/performance-report.sh" "$TMP/p" 2>&1)" || fail 'performance-report.sh failed'
grep -q 'historical-cline-row | 1 ' <<<"$out" || fail 'cline row dropped from report'
grep -q '| agent | implementation | 2 | 11 | 2/2 | 300 |' <<<"$out" || fail 'non-cline totals changed'
echo 'stage-billing-test: passed'
