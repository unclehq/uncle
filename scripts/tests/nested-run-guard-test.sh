#!/usr/bin/env bash
# worktree-run-test.sh drives worktrees and from-issue.sh. Inside a live uncle
# build -- which is what uncle green-checking its own repository produces -- it
# contends with the run that invoked it and never finishes.
#
# Measured on this repository: about 15 seconds on its own, against the
# harness's 600-second timeout inside a build, with 85 of 86 suites finished
# and the whole baseline waiting on this one. The build then sits at IMPLEMENT
# blocked on a baseline that cannot complete, twice observed.
#
# The guard has to be exactly as narrow as that: skip only when a build is
# genuinely live, because a suite that skips when it could have run is a test
# nobody notices has stopped testing anything.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUITE="$ROOT/scripts/tests/worktree-run-test.sh"
work="$(mktemp -d)"
LIVE=""
trap 'if [[ -n "$LIVE" ]]; then kill "$LIVE" 2>/dev/null; fi; rm -rf "$work"' EXIT

FAILED=0
check() {
    local label="$1" want="$2" got="$3"
    if [[ "$want" == "$got" ]]; then
        echo "  ok: $label"
    else
        echo "  FAIL: $label (wanted $want, got $got)" >&2
        FAILED=1
    fi
}

# The guard reads only UNCLE_PROJECT_ROOT and the lock, and exits before the
# suite does any work -- so these run in well under a second each. Only the
# cases that must NOT skip pay for a real run, and those are covered by the
# suite's own presence in the battery rather than repeated here.
lock="$work/project/.uncle/workflow/lock"
mkdir -p "$lock"

# A process that is genuinely alive for the duration of this test.
sleep 120 & LIVE=$!

status() {
    local root="${1:-}" allow="${2:-}"
    env ${root:+UNCLE_PROJECT_ROOT="$root"} ${allow:+UNCLE_TEST_ALLOW_NESTED="$allow"} \
        timeout 20 bash "$SUITE" > "$work/out" 2>&1
    echo $?
}

# Whether the guard let the suite through, without waiting for the suite to
# finish. Asserting "exit 0" would mean running the whole battery and calling a
# slow machine a failure; the guard exits before any of that, so a few seconds
# is enough to prove it was not skipped. A timeout kill (124) is a pass here:
# it means the suite was still running.
ran() {
    local root="${1:-}" allow="${2:-}" code
    env ${root:+UNCLE_PROJECT_ROOT="$root"} ${allow:+UNCLE_TEST_ALLOW_NESTED="$allow"} \
        timeout 5 bash "$SUITE" > "$work/out" 2>&1
    code=$?
    if [[ "$code" == 77 ]] || grep -q 'skipped, a live uncle build' "$work/out"; then
        echo skipped
    else
        echo ran
    fi
}

printf '%s\n' "$LIVE" > "$lock/pid"
out="$(status "$work/project")"
check "live build skips with 77" 77 "$out"
grep -q "a live uncle build (pid $LIVE)" "$work/out" \
    && echo "  ok: names the owning pid" || { echo "  FAIL: message does not name the pid" >&2; FAILED=1; }
grep -q "UNCLE_TEST_ALLOW_NESTED=1" "$work/out" \
    && echo "  ok: message names the override" || { echo "  FAIL: message hides the override" >&2; FAILED=1; }

# A killed run leaves its lock directory behind. That names a pid which is
# gone, and must not silence the suite forever after.
kill "$LIVE" 2>/dev/null; wait "$LIVE" 2>/dev/null; dead="$LIVE"; LIVE=""
printf '%s\n' "$dead" > "$lock/pid"
out="$(ran "$work/project")"
check "stale lock does not skip" ran "$out"

# Lock directory with no pid file at all: not proof of anything.
rm -f "$lock/pid"
out="$(ran "$work/project")"
check "lock without a pid does not skip" ran "$out"

# No lock, and no UNCLE_PROJECT_ROOT: the ordinary developer case.
rm -rf "$lock"
out="$(ran "$work/project")"
check "no lock does not skip" ran "$out"
out="$(ran "" "")"
check "no UNCLE_PROJECT_ROOT does not skip" ran "$out"

if [[ "$FAILED" == 0 ]]; then
    echo 'nested-run-guard-test.sh: the suite skips a live build and nothing else'
else
    echo 'nested-run-guard-test.sh: FAILED' >&2
fi
exit "$FAILED"
