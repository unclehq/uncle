#!/usr/bin/env bash
# A self-hosted updated-change-plan is not drafted speculatively; other runners still are.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT+1)); [[ "$2" == "$3" ]] || { FAILED=$((FAILED+1)); echo "FAIL: $1: expected [$2] got [$3]"; }; }

STATE_DIR="$TMP/state"; PROJECT_ROOT="$TMP"; ROOT="$HERE/../.."
. "$HERE/../lib/speculate-change.sh"
f="$TMP/gate.md"; echo plan > "$f"

run() {  # run <runner>
    ( uncle_stage_runner_value="$1"
      uncle_stage_runner() { printf '%s' "$uncle_stage_runner_value"; }
      ROOT="$ROOT"; export ROOT
      # stop right after the runner decision: the mirror step would need a real repo
      python3() { return 1; }
      speculate_updated_plan "$f" 2>&1 )
}
check "self-hosted skips the draft" "Not drafting the updated plan during review: self-hosted stages write it as a patch in the foreground." "$(run self-hosted)"
check "claude still drafts (reaches the mirror step)" "Speculation unavailable: could not mirror the working tree." "$(run claude)"

if [[ "$FAILED" -ne 0 ]]; then echo "speculate-self-hosted-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "speculate-self-hosted-test.sh: $COUNT checks passed"
