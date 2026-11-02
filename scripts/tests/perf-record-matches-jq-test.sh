#!/usr/bin/env bash
# perf_record.py must produce the record the old jq pipeline did, for every log shape the runners write. The reference below is the jq
# program that perf_record used before it moved to one Python process, kept verbatim; the cases compare the published records
# field by field (the timestamps differ by the clock, so only their difference is compared).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }

old_record() {  # state_dir log elapsed status speculative -> the jq pipeline, unchanged
    local dir="$1/metrics" tmp log="$2"
    [[ -f "$log" ]] || log=/dev/null      # perf_record fell back to /dev/null for a log that was never written
    mkdir -p "$dir"; tmp="$(mktemp "$dir/.pending.XXXXXX")"
    jq -R -s -c --arg kind agent --arg stage implementation --arg runner claude --arg model opus --arg effort high \
        --arg log "$log" --arg state IMPLEMENT --arg run_id run-123 --argjson elapsed "$3" --argjson exit_code "$4" \
        --argjson ended "$(date +%s)" --argjson speculative "$5" '
        [split("\n")[] | fromjson? | select(type == "object" and .type == "result")] as $results
        | ($results[-1] // {}) as $r
        | [scan("tokens used[\\r\\n ]+([0-9,]+)") | .[0] | gsub(","; "") | tonumber] as $totals
        | {schema:1, kind:$kind, stage:$stage, workflow_state:$state, run_id:$run_id,
           runner:$runner, model:($r.model // $model), effort:$effort, speculative:$speculative,
           ended_at:$ended, started_at:($ended-$elapsed), elapsed_seconds:$elapsed,
           process_exit:$exit_code, reported_error:$r.is_error,
           turns:($r.num_turns // null), input_tokens:($r.usage.input_tokens // null),
           output_tokens:($r.usage.output_tokens // null),
           reported_total_tokens:($r.usage.total_tokens // $totals[-1] // null),
           cache_read_tokens:($r.usage.cache_read_input_tokens // $r.usage.cached_input_tokens // null),
           cache_write_tokens:($r.usage.cache_creation_input_tokens // $r.usage.cache_write_input_tokens // null),
           reported_cost_usd:($r.total_cost_usd // null),
           usage_scope:($r.usage_scope // "last reported result"),
           usage_source:($r.usage_source // null),
           input_includes_cache:($r.input_includes_cache // false),
           log:$log}' "$log" > "$tmp" 2>/dev/null || { rm -f "$tmp"; return 0; }
    python3 "$ROOT/scripts/lib/usage-cost.py" "$tmp" || true
    mv "$tmp" "$tmp.json"
}
new_record() {
    ( export STATE_DIR="$1" UNCLE_TIMING_DIR=/x/run-123 UNCLE_SPECULATIVE="$5" WORKFLOW_METRICS=1; state=IMPLEMENT
      . "$ROOT/scripts/lib/performance.sh"; perf_record agent implementation "$3" "$4" "$2" claude opus high ) 2>/dev/null
}

r1='{"type":"result","subtype":"success","is_error":false,"num_turns":3,"model":"claude-x","total_cost_usd":0.12,"usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":7,"cache_creation_input_tokens":3,"total_tokens":160}}'
r2='{"type":"result","is_error":true,"num_turns":1}'
printf '' > "$TMP/empty.log"
printf '%s\n' "$r1" > "$TMP/claude.log"
printf 'working\ntokens used\n1,234\nmore\ntokens used  5,678\n' > "$TMP/codex.log"
printf 'junk line\n%s\n{"type":"assistant"}\n%s\nnot json {\n' "$r1" "$r2" > "$TMP/multi.log"
printf '%s\n' "$r2" > "$TMP/err.log"
printf '{"type":"result","usage":{"input_tokens":10,"output_tokens":5,"cached_input_tokens":4,"cache_write_input_tokens":2},"usage_source":"api","usage_scope":"session","input_includes_cache":true,"model":"moonshot-ai/kimi-k3"}\n' > "$TMP/kimi.log"
printf '{"type":"result","usage":7}\n' > "$TMP/badusage.log"
printf '{"type":"result","model":"m","usage":null,"total_cost_usd":0}\n' > "$TMP/nullusage.log"

compare() {  # name log elapsed status speculative
    local name="$1" a="$TMP/$1.old" b="$TMP/$1.new"
    mkdir -p "$a" "$b"
    old_record "$a" "$2" "$3" "$4" "$5"; new_record "$b" "$2" "$3" "$4" "$5"
    python3 - "$a" "$b" <<'PY' || bad "$name" 'perf_record.py differs from the jq pipeline'
import glob, json, sys
def rec(d):
    files = glob.glob(d + '/metrics/.pending.*.json')
    return json.loads(open(files[0]).read()) if files else None
a, b = rec(sys.argv[1]), rec(sys.argv[2])
def norm(x):
    if x is None: return None
    x = dict(x)
    assert abs((x.pop('ended_at') - x.pop('started_at')) - x['elapsed_seconds']) < 1e-6
    return x
if norm(a) != norm(b):
    print('old:', norm(a)); print('new:', norm(b)); sys.exit(1)
PY
    ok
}
compare empty-log "$TMP/empty.log" 5 0 false
compare claude "$TMP/claude.log" 12 0 false
compare codex-tokens "$TMP/codex.log" 30 1 true
compare multi-results "$TMP/multi.log" 7 0 false
compare error-result "$TMP/err.log" 2 3 false
compare kimi-priced "$TMP/kimi.log" 12.5 0 true
compare null-usage "$TMP/nullusage.log" 4 0 false
compare malformed-usage-is-dropped "$TMP/badusage.log" 4 0 false
compare missing-log "$TMP/nope.log" 9 0 false

if [[ "$FAIL" -ne 0 ]]; then echo "perf-record-matches-jq-test.sh: $FAIL failed"; exit 1; fi
echo "perf-record-matches-jq-test.sh: $PASS cases match the jq pipeline"
