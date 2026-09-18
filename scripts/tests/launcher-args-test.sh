#!/usr/bin/env bash
# `uncle` argument parsing: a near-miss flag gets the flag it was reaching for,
# an unrelated one gets the usage text, and both exit 1 before doing anything.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

run_uncle() { (cd "$TMP" && NO_COLOR=1 bash "$ROOT/uncle" "$@" > "$TMP/out" 2> "$TMP/err"); RC=$?; }

run_uncle --applcation 'build a calculator' --unattended
check "typo exits 1"                        test "$RC" -eq 1
check "typo is named"                       grep -qF "Unknown argument: --applcation" "$TMP/err"
check "typo gets the intended flag"         grep -qF "Did you mean --application?" "$TMP/err"
check "typo does not dump the usage text"   test "$(grep -c "Usage: uncle" "$TMP/err")" -eq 0
leftovers="$(find "$TMP" -mindepth 1 ! -name out ! -name err)"
check "nothing written to the project dir ($leftovers)" test -z "$leftovers"

run_uncle --isue 42
check "second flag also hinted"             grep -qF "Did you mean --issue?" "$TMP/err"

run_uncle --frobnicate
check "unrelated flag exits 1"              test "$RC" -eq 1
check "unrelated flag gets usage"           grep -qF "Usage: uncle" "$TMP/err"
check "unrelated flag gets no hint"         test "$(grep -c "Did you mean" "$TMP/err")" -eq 0

if [[ "$fails" -gt 0 ]]; then echo "launcher-args-test.sh: $fails failure(s)"; exit 1; fi
echo "launcher-args-test.sh: all checks passed"
