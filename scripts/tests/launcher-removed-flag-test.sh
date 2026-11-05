#!/usr/bin/env bash
# The retired flag is gone: it is an unknown argument, absent from usage, and
# no did-you-mean suggestion points at it.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNCLE="$ROOT/uncle"
fail=0
check() { if [[ "$2" == 0 ]]; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi; }
run() { UNCLE_SKIP_UPGRADE=1 bash "$UNCLE" "$@" 2>&1; }

out="$(run --help)"; rc=$?
check "help exits 0" "$rc"
! grep -qi 'housekeeping' <<<"$out"; check "usage does not list the removed flag" $?

out="$(run --housekeeping x </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'Unknown argument' <<<"$out"; check "removed flag is an unknown argument (exit 1)" $?

out="$(run --housekeepin x </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && ! grep -q 'Did you mean --housekeeping' <<<"$out"; check "no did-you-mean for the removed flag" $?

out="$(run --application y --housekeeping x </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'Unknown argument' <<<"$out"; check "removed flag after --application still unknown" $?

out="$(run --bogus-flag </dev/null)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'Unknown argument' <<<"$out"; check "other unknown flags unchanged" $?

exit "$fail"
