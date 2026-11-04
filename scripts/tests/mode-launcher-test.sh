#!/usr/bin/env bash
# Launcher mode resolution: refusals happen before any state is created, a
# user-supplied UNCLE_MODE_RESOLVED is cleared, and --attended with piped stdin
# text is refused, while stdin left free is detected automatically.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNCLE="$ROOT/uncle"
fail=0
NOTTY='uncle: attended mode needs an interactive terminal on stdin, or stdin left free to answer gates (not consumed by a bare --application, bare --issue or --change-request).'
CONTRA='uncle: --attended and --unattended contradict each other; choose one.'

check() { # name want_status want_stderr_substr status stderr stdout
    if [[ "$4" != "$2" || "$5" != *"$3"* || -n "$6" ]]; then
        printf 'FAIL %s: status=%s (want %s) stdout=[%s] stderr=[%s]\n' "$1" "$4" "$2" "$6" "$5" >&2
        fail=1
    else
        printf 'ok %s\n' "$1"
    fi
}

run() { # name want_status want_substr -- env... -- args...  (stdin is /dev/null, never a tty)
    local name="$1" want="$2" sub="$3"; shift 3
    local envs=() out err st
    while [[ "$1" != -- ]]; do envs+=("$1"); shift; done
    shift
    err="$(mktemp)"
    out="$(cd "$(mktemp -d)" && env "${envs[@]}" bash "$UNCLE" "$@" </dev/null 2>"$err")"; st=$?
    check "$name" "$want" "$sub" "$st" "$(cat "$err")" "$out"
    rm -f "$err"
}

run contradictory-flags 1 "$CONTRA" UNCLE_SKIP_UPGRADE=1 -- --attended --unattended
run attended-no-tty 1 "$NOTTY" UNCLE_SKIP_UPGRADE=1 -- --attended
run env-attended-no-tty 1 "$NOTTY" UNCLE_SKIP_UPGRADE=1 UNCLE_ATTENDED=1 --
# A user-supplied UNCLE_MODE_RESOLVED=1 with UNCLE_UNATTENDED=1 must be cleared:
# --attended then re-resolves and hits the TTY rule instead of being refused as
# a contradiction of an inherited decision.
run resolved-cleared 1 "$NOTTY" UNCLE_SKIP_UPGRADE=1 UNCLE_MODE_RESOLVED=1 UNCLE_UNATTENDED=1 -- --attended
# Bare --application consumes stdin, so attended has none left for gates: refused.
run bare-application-attended-refused 1 "$NOTTY" UNCLE_SKIP_UPGRADE=1 -- --application --attended
run claimed-stdin-env-ignored 1 "$NOTTY" UNCLE_SKIP_UPGRADE=1 UNCLE_ATTENDED_STDIN=1 -- --application --attended
# Text given on the command line leaves stdin free: no refusal, no env var needed.
err="$(mktemp)"
( cd "$(mktemp -d)" && UNCLE_SKIP_UPGRADE=1 timeout 5 bash "$UNCLE" --application hello --attended --bogus </dev/null >/dev/null 2>"$err" )
if grep -qF "attended mode needs" "$err"; then echo "FAIL free-stdin-auto: refusal printed" >&2; fail=1; else echo "ok free-stdin-auto"; fi
rm -f "$err"

exit "$fail"
