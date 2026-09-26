#!/usr/bin/env bash
# The green-check baseline runs in the background during planning, joined
# before IMPLEMENT. That overlap is deliberate, but it is also the one place
# the workflow competes with itself: a full project suite runs flat out while
# the planning stage waits on a model. On uncle's own repository that suite is
# 85 shell suites, and four review workers doing near-identical work came back
# in 54s, 170s, 205s and 229s -- the same work, a 4.2x spread.
#
# Nothing waits on the baseline until IMPLEMENT, so it yields to the stage that
# is being waited on. Two things have to hold: the job is actually reniced, and
# the suite it forks inherits that.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fail() { echo "baseline-nice-test.sh: FAIL: $*" >&2; exit 1; }

# $$ inside a subshell is still the parent's pid, and $BASHPID is bash 4+
# while this ships on macOS's bash 3.2, so the renice has to come from the
# parent using the pid $! just returned.
grep -q 'renice -n "${WORKFLOW_BASELINE_NICE:-10}" -p "$BASELINE_BG_PID"' \
    "$ROOT/scripts/change-workflow.sh" \
    || fail 'the background baseline is no longer reniced from its parent'
if grep -q 'renice .*\$BASHPID' "$ROOT/scripts/change-workflow.sh"; then
    fail 'BASHPID is unset in bash 3.2; the renice would silently do nothing'
fi

# The mechanism itself, on this machine's bash: a job reniced by its parent,
# and a child forked afterwards.
cat > "$work/probe.sh" <<'PROBE'
#!/bin/bash
( sleep 0.5; sleep 5 & wait ) > /dev/null 2>&1 &
job=$!
renice -n 10 -p "$job" > /dev/null 2>&1 || { echo "renice-failed"; exit 1; }
printf 'job %s\n' "$(ps -o nice= -p "$job" | tr -d ' ')"
sleep 1.5
for child in $(pgrep -P "$job"); do
    printf 'child %s\n' "$(ps -o nice= -p "$child" | tr -d ' ')"
done
kill "$job" 2>/dev/null || true
wait 2>/dev/null || true
PROBE
out="$(/bin/bash "$work/probe.sh")" || fail "probe failed: $out"

[[ "$(printf '%s\n' "$out" | awk '$1=="job"{print $2}')" == 10 ]] \
    || fail "the background job was not reniced: $out"
child="$(printf '%s\n' "$out" | awk '$1=="child"{print $2; exit}')"
[[ -n "$child" ]] || fail "probe forked no child, so inheritance went untested: $out"
[[ "$child" == 10 ]] \
    || fail "a child forked after the renice did not inherit it (nice=$child)"

# Only ever lower. Raising a priority back needs privilege, and a negative
# value here would make the baseline compete harder, not less.
nice_default="$(grep -o 'WORKFLOW_BASELINE_NICE:-[0-9-]*' "$ROOT/scripts/change-workflow.sh" | head -1 | sed 's/.*:-//')"
[[ -n "$nice_default" && "$nice_default" -gt 0 ]] \
    || fail "the default niceness must be positive, got '${nice_default:-unset}'"

echo 'baseline-nice-test.sh: the background baseline yields to the stage being waited on'
