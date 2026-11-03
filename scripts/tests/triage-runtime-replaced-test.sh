#!/usr/bin/env bash
set -uo pipefail
# `brew upgrade` during a run deletes and recreates the versioned install a driver started from. Helper scripts vanish partway through a
# stage, the stage reads as a model failure, and the triage bundle said "stop reason: MISSING" (uncle issue 141, at FINAL_AUDIT).
# A driver that finds its own install gone now records that, so the operator knows to rerun rather than debug the run.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

# A stand-in install: just what triage.sh needs, reached through a stable link like Homebrew's opt path.
mkdir -p "$TMP/keg-1/scripts/lib"
cp "$REPO/scripts/lib/triage.sh" "$REPO/scripts/lib/state.sh" "$TMP/keg-1/scripts/lib/"
ln -s keg-1 "$TMP/opt"

run() {   # <keg-to-delete|-> <exit status> [existing stop-reason]
    local dir="$TMP/state.$RANDOM"; mkdir -p "$dir"
    [[ -z "${3:-}" ]] || printf '%s\n' "$3" > "$dir/stop-reason"
    (
        ROOT="$TMP/opt"; UNATTENDED=1; STATE_DIR="$dir"
        write_triage() { :; }
        . "$ROOT/scripts/lib/triage.sh"
        [[ "$1" == - ]] || rm -rf "$TMP/$1"
        triage_on_exit "$2"
    ) > /dev/null 2>&1
    echo "$dir"
}

d="$(run - 1)"
check "an intact install records nothing" test ! -s "$d/stop-reason"
d="$(run keg-1 1)"
check "a deleted install is named as the cause" grep -q "reinstalled or upgraded while this run was in progress" "$d/stop-reason"
check "and says to rerun" grep -q "rerun to resume" "$d/stop-reason"
mkdir -p "$TMP/keg-1/scripts/lib"; cp "$REPO/scripts/lib/triage.sh" "$REPO/scripts/lib/state.sh" "$TMP/keg-1/scripts/lib/"
d="$(run keg-1 1 'validation: something specific')"
check "an existing reason is never replaced" test "$(cat "$d/stop-reason")" == "validation: something specific"
mkdir -p "$TMP/keg-1/scripts/lib"; cp "$REPO/scripts/lib/triage.sh" "$REPO/scripts/lib/state.sh" "$TMP/keg-1/scripts/lib/"
d="$(run keg-1 0)"
check "a successful exit records nothing" test ! -s "$d/stop-reason"

if [[ "$fails" -ne 0 ]]; then echo "triage-runtime-replaced-test.sh: $fails failed"; exit 1; fi
echo "triage-runtime-replaced-test.sh: all checks passed"
