#!/usr/bin/env bash
set -uo pipefail
# A driver told to stop with SIGTERM (143) records why when nothing else did: grove issue 7's unattended run was killed from outside and its triage
# bundle read "stop reason: MISSING", with nothing to say the run was healthy and only needed resuming. The real uncle_cancel runs.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

cancel() {   # code [existing stop-reason]
    local dir="$TMP/state.$RANDOM"; mkdir -p "$dir"
    [[ -z "${2:-}" ]] || printf '%s\n' "$2" > "$dir/stop-reason"
    ( ROOT="$REPO"; STATE_DIR="$dir"; . "$REPO/scripts/lib/terminal-title.sh"; uncle_cancel "$1" ) > /dev/null 2>&1
    echo "$?" > "$dir/rc"; echo "$dir"
}

d="$(cancel 143)"
check "143 keeps its exit status" test "$(cat "$d/rc")" == 143
check "143 with no reason records one" grep -q "SIGTERM from outside" "$d/stop-reason"
check "the reason says the run can be resumed" grep -q "rerun to resume" "$d/stop-reason"
d="$(cancel 143 'validation: something specific')"
check "an existing reason is never replaced" test "$(cat "$d/stop-reason")" == "validation: something specific"
d="$(cancel 143 human)"
check "a human stop stays a human stop" test "$(cat "$d/stop-reason")" == human
d="$(cancel 130)"
check "130 (a person's Ctrl-C) keeps its status" test "$(cat "$d/rc")" == 130
check "130 records no reason of its own" test ! -s "$d/stop-reason"

if [[ "$fails" -ne 0 ]]; then echo "cancel-stop-reason-test.sh: $fails failed"; exit 1; fi
echo "cancel-stop-reason-test.sh: all checks passed"
