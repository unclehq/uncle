#!/usr/bin/env bash
# Two repair passes are all there is: a second pass that changes nothing spends the rest and goes to the final audit, not to a person.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
J="$ROOT/scripts/lib/repair-judge.sh"
SG="$ROOT/scripts/stagegate.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }

judge() {   # <auto attempts> <noops so far|none> <repair-count> -> prints "rc=N" and the files
    rm -rf "$work/s"; mkdir -p "$work/s/documents"
    printf '%s\n' .uncle/docs/TEST_REVIEW.md > "$work/s/repair-source"
    printf '%s\n' "$3" > "$work/s/repair-count"
    [[ "$2" == none ]] || printf '%s\n' "$2" > "$work/s/repair-noop-count"
    : > "$work/s/repair-retry"
    env -i PATH="$PATH" REPAIR_ON="${REPAIR_ON:-1}" bash --norc --noprofile -c "
        STATE_DIR='$work/s'; ROOT='$ROOT'; WORKFLOW_REPAIR=\${REPAIR_ON:-1}; WORKFLOW_AUTO_REPAIR_ATTEMPTS='$1'
        python3() { case \"\$*\" in *'repair_check.py judge'*|*'repair_check.py'*' judge '*) echo ASSERTIONS; return 1;; *repair_plan_route*) return 1;; esac; return 0; }
        supervision_validation_failed() { :; }
        triage_stop_reason() { echo \"stop-reason=\$2\"; }
        set_state() { :; }
        . '$J'
        repair_judge; echo rc=\$?"
}

out="$(judge 2 1 1)"
grep -q 'rc=6' <<< "$out"                   || bad "a second no-op pass with repair on should return 6: $out"
grep -q 'stop-reason' <<< "$out"            && bad "it must not stop for a person"
[[ "$(cat "$work/s/repair-count")" == 2 ]]  || bad "the remaining passes were not spent (repair-count=$(cat "$work/s/repair-count"))"
[[ ! -e "$work/s/repair-retry" && ! -e "$work/s/repair-noop-count" ]] || bad "the retry markers were left behind"

out="$(judge 2 none 1)"
grep -q 'rc=3' <<< "$out"                   || bad "the first no-op pass still retries once with a brief: $out"

out="$(judge 0 1 1)"
grep -q 'rc=1' <<< "$out" && grep -q 'stop-reason=human' <<< "$out" || bad "with automatic repair off the second no-op still stops for a person: $out"
out="$(REPAIR_ON=0 judge 2 1 1)"
grep -q 'rc=1' <<< "$out"                   || bad "WORKFLOW_REPAIR=0 still stops for a person: $out"

# the driver sends 6 to the final audit
block="$(sed -n '/repair_judge || repair_status=\$?/,/^                esac/p' "$SG")"
printf '%s\n' "$block" | grep -q '6) set_state FINAL_AUDIT; continue' || bad "REPAIR does not route 6 to FINAL_AUDIT"
[[ $fail == 0 ]] && echo "repair-noop-route-test.sh: ok"
exit $fail
