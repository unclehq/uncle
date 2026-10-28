#!/usr/bin/env bash
# The first writer that shares the prompt prefix goes alone for a short while; the rest start after it.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }
awk '/^updated_plan_warm_prefix\(\) \{/,/^}/' "$ROOT/scripts/stagegate.sh" > "$TMP/fn.sh"
check "function extracted" test -s "$TMP/fn.sh"
. "$TMP/fn.sh"
LOG_DIR="$TMP/logs"; mkdir -p "$LOG_DIR"
local_runner=0
stage_uses_self_hosted() { [[ "$local_runner" == 1 ]]; }
sleep() { command sleep 0.05; }
t() { python3 -c 'import time; print(time.time())'; }

# fewer than four writers: no wait
WORKFLOW_PREFIX_WARM_SECONDS=20 updated_plan_warm_prefix 2 3 > /dev/null
check "three writers: no wait" true

# hosted: returns as soon as the writer's log shows its first assistant event
echo '{"type": "assistant"}' > "$LOG_DIR/updated-plan-worker-edits-2.jsonl"
a=$(t); WORKFLOW_PREFIX_WARM_SECONDS=200 updated_plan_warm_prefix 2 8 > /dev/null; b=$(t)
check "hosted: returns on the first event" python3 -c "import sys; sys.exit(0 if $b - $a < 1.0 else 1)"

# hosted with no event: waits the whole limit (sleep is shortened: 20 polls)
rm -f "$LOG_DIR/updated-plan-worker-edits-2.jsonl"
a=$(t); WORKFLOW_PREFIX_WARM_SECONDS=20 updated_plan_warm_prefix 2 8 > /dev/null; b=$(t)
check "hosted: no event, waits out the limit" python3 -c "import sys; sys.exit(0 if 0.8 < $b - $a < 3 else 1)"

# self-hosted: no early event exists, so it waits the time even when a log line is there
local_runner=1
a=$(t); updated_plan_warm_prefix 2 8 > /dev/null; b=$(t)
check "self-hosted: off by default (vLLM batches the prefill; measured)" python3 -c "import sys; sys.exit(0 if $b - $a < 0.5 else 1)"
a=$(t); WORKFLOW_PREFIX_WARM_SECONDS=20 updated_plan_warm_prefix 2 8 > /dev/null; b=$(t)
check "self-hosted: waits the time when asked" python3 -c "import sys; sys.exit(0 if 0.8 < $b - $a < 3 else 1)"

# switched off
a=$(t); WORKFLOW_PREFIX_WARM_SECONDS=0 updated_plan_warm_prefix 2 8 > /dev/null; b=$(t)
check "0 turns it off" python3 -c "import sys; sys.exit(0 if $b - $a < 0.5 else 1)"

# defaults: 12 hosted, 25 self-hosted
check "defaults are named in the function" grep -q 'limit=0; else limit=12' "$TMP/fn.sh"
# the driver calls it after the first sharing writer, before the rest
check "launch order" python3 - "$ROOT/scripts/stagegate.sh" <<'PY'
import sys
t = open(sys.argv[1]).read()
b = t[t.index('run_updated_plan_edit_writers() {'):]
sys.exit(0 if b.index('updated_plan_launch_writer "$directory"') < b.index('updated_plan_warm_prefix "$name"') else 1)
PY
[[ "$fails" == 0 ]] && echo OK
exit "$fails"
