#!/usr/bin/env bash
# The change driver treats an application that cannot be built, served or tested as stagegate.sh does: repair once unattended, record when no repair remains, stop attended.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CW="$ROOT/scripts/change-workflow.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
FUNC="$(awk '/^change_route_unrunnable_application\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$CW")"
[[ -n "$FUNC" ]] || bad "could not extract the function"

n=0
go() {   # <unrunnable|runnable> <repair-count> <unattended 0|1> [marker] [WORKFLOW_REPAIR]
    n="$(( $(cat "$work/n" 2>/dev/null || echo 0) + 1 ))"; echo "$n" > "$work/n"; local dir="$work/p$n"; echo "$dir" > "$work/last"; mkdir -p "$dir/s/logs"
    [[ "$1" == unrunnable ]] && echo 'error when starting dev server' > "$dir/s/logs/green-check.log" || : > "$dir/s/logs/green-check.log"
    printf '%s\n' "$2" > "$dir/s/repair-count"; echo 'run-1' > "$dir/s/run-started-at"; echo '| PASS | `npm ci` |' > "$dir/green-check.md"
    [[ "${4:-}" == marker ]] && : > "$dir/s/runtime-readiness-repair-attempted"
    ( cd "$dir" && env -i PATH="$PATH" bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='s'; LOG_DIR='s/logs'; GREEN_MD='green-check.md'; UNATTENDED=$3
        WORKFLOW_REPAIR=${5:-1}; WORKFLOW_AUTO_REPAIR_ATTEMPTS=2
        record_nonblocking_failure() { echo \"nonblocking:\$1\"; }
        record_test_failure_disposition() { :; }
        set_state() { echo \"state=\$1\"; }
        $FUNC
        change_route_unrunnable_application; echo rc=\$?" 2>&1 )
}

out="$(go runnable 0 1)";  grep -q 'rc=0' <<< "$out" && ! grep -q 'state=' <<< "$out" || bad "a runnable application should go on: $out"

out="$(go unrunnable 0 1)"
grep -q 'rc=2' <<< "$out" && grep -q 'state=REPAIR' <<< "$out" || bad "unattended and unrunnable: repair once, got: $out"
d="$(cat "$work/last")"
[[ "$(cat "$d/s/repair-source")" == "s/runtime-unrunnable-application" ]] || bad "the repair source is not the startup failure"
grep -q 'Application startup verification failed' "$d/s/runtime-unrunnable-application" || bad "the startup failure brief was not written"
[[ -e "$d/s/runtime-readiness-repair-attempted" ]] || bad "the one-shot marker was not set"

out="$(go unrunnable 1 1 marker)"
grep -q 'rc=1' <<< "$out" && ! grep -q 'state=' <<< "$out" || bad "already repaired once and still unrunnable: stop, got: $out"

out="$(go unrunnable 0 0)"
grep -q 'rc=1' <<< "$out" || bad "attended and unrunnable: stop, got: $out"

out="$(go unrunnable 2 1)"
grep -q 'rc=0' <<< "$out" && grep -q 'nonblocking:green-check' <<< "$out" || bad "no repair pass left: record it and let the checklist observe, got: $out"
out="$(go unrunnable 2 1)"; : # the same run must record once:
d="$(cat "$work/last")"; second="$(cd "$d" && env -i PATH="$PATH" bash --norc --noprofile -c "
    ROOT='$ROOT'; STATE_DIR='s'; LOG_DIR='s/logs'; GREEN_MD='green-check.md'; UNATTENDED=1; WORKFLOW_REPAIR=1; WORKFLOW_AUTO_REPAIR_ATTEMPTS=2
    record_nonblocking_failure() { echo \"nonblocking:\$1\"; }; record_test_failure_disposition() { :; }; set_state() { :; }
    $FUNC
    change_route_unrunnable_application; change_route_unrunnable_application" 2>&1)"
grep -q 'nonblocking' <<< "$second" && bad "the failure was recorded again for the same run: $second"

out="$(go unrunnable 0 1 none 0)"
grep -q 'rc=0' <<< "$out" && grep -q 'nonblocking:green-check' <<< "$out" && ! grep -q 'state=' <<< "$out" || bad "repair off: record and go on, got: $out"

# every place that used the old self-hosted-only bounce now uses it
grep -c 'change_route_unrunnable_application || runtime_ready_rc=\$?' "$CW" | grep -qx 4 || bad "expected four call sites (test review, checklist, execute, final audit)"
grep -q '^            if green_requires_implementation_repair' "$CW" && bad "a call site still bounces to IMPLEMENT"
[[ $fail == 0 ]] && echo "change-unrunnable-route-test.sh: ok"
exit $fail
