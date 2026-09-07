#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/performance.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STATE_DIR="$TMP/.uncle/workspace"
mkdir -p "$STATE_DIR"
cat > "$TMP/log" <<'EOF'
startup text
{"type":"result","usage":{"input_tokens":10}}
{"type":"result","is_error":false,"usage":{"input_tokens":100,"output_tokens":20,"cached_input_tokens":80}}
EOF
perf_record agent implementation 9 0 "$TMP/log" runner model medium
perf_record agent implementation 2 1 /dev/null runner model low
perf_record approval plan 30 0
printf 'tokens used\n1,234\n' > "$TMP/reviewer"
perf_record reviewer audit 5 0 "$TMP/reviewer"
for i in 1 2 3 4 5; do perf_record check "check $i" 1 0 & done
wait
python3 -B - "$STATE_DIR/metrics" <<'PY'
import json, pathlib, sys
records=[json.loads(p.read_text()) for p in pathlib.Path(sys.argv[1]).glob('*.json')]
assert len(records)==9, records
known=next(r for r in records if r['input_tokens'] is not None)
assert known['input_tokens']==100 and known['output_tokens']==20
assert known['cache_read_tokens']==80 and known['reported_error'] is False
unknown=next(r for r in records if r['process_exit']==1)
assert unknown['input_tokens'] is None and unknown['reported_cost_usd'] is None
assert sum(r['elapsed_seconds'] for r in records if r['kind']=='agent')==11
assert next(r for r in records if r['kind']=='reviewer')['reported_total_tokens']==1234
PY
bash "$ROOT/scripts/performance-report.sh" "$TMP" > "$TMP/report"
grep -qF '| agent | implementation | 2 | 11 | 1/2 | 100 | 20 |' "$TMP/report"
WORKFLOW_METRICS=0 perf_record check disabled 1 0
[[ "$(find "$STATE_DIR/metrics" -name '*.json' | wc -l | tr -d ' ')" == 9 ]]
echo 'performance-test.sh: concurrent records, unknown usage, cumulative results, report, and opt-out passed'
