#!/usr/bin/env bash
# The wall-clock ceiling applies to every runner, not only self-hosted: a hung hosted worker is killed (with its children) at the ceiling,
# a worker that finishes passes its status through, and with no ceiling the call is untouched. A hung hosted final-audit lens is retried.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"; trap 'pkill -f "sleep 2971" 2>/dev/null; rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }
mkdir -p "$work/logs"

# A 25 s watchdog: if the ceiling is broken the hung call must fail this test quickly, not wait out its own sleep.
harness() { env -i PATH="$PATH" HOME="$HOME" ${1:+"$1"} perl -e 'alarm 25; exec @ARGV' bash --norc --noprofile -c "
    ROOT='$ROOT'; STATE_DIR='$work'; LOG_DIR='$work/logs'
    stage_uses_self_hosted() { return 1; }
    . '$ROOT/scripts/lib/model-jobs.sh'
    $2"; }

# --- the ceiling kills a hung hosted worker --------------------------------------------------------------------------------------
start=$SECONDS
out="$(harness UNCLE_WRITER_CEILING=2 'hang() { sleep 2971 > /dev/null 2>&1; }; workflow_model_writer execute-checklist hang x hosted-worker 2>/dev/null; echo rc=$?')"
elapsed=$((SECONDS - start))
eq "a hung hosted worker is stopped at the ceiling" "$out" rc=124
(( elapsed < 15 )) || bad "the hung worker took ${elapsed}s: the ceiling did not stop it"
pgrep -f "sleep 2971" > /dev/null && bad "the hung worker's child was left running"

# --- a finished worker passes its status through ----------------------------------------------------------------------------------
eq "success passes through under a ceiling" "$(harness UNCLE_WRITER_CEILING=30 'quick() { return 0; }; workflow_model_writer execute-checklist quick x w; echo rc=$?')" rc=0
eq "a failing status passes through under a ceiling" "$(harness UNCLE_WRITER_CEILING=30 'quick() { return 7; }; workflow_model_writer execute-checklist quick x w; echo rc=$?')" rc=7

# --- no ceiling, no change ---------------------------------------------------------------------------------------------------------
eq "without a ceiling a hosted call is untouched" "$(harness '' 'quick() { return 5; }; workflow_model_writer execute-checklist quick x w; echo rc=$?')" rc=5
for off in 0 abc -3 ''; do
    eq "a ceiling of '$off' means none" "$(harness UNCLE_WRITER_CEILING="$off" 'quick() { return 4; }; workflow_model_writer execute-checklist quick x w; echo rc=$?')" rc=4
done

# --- a hung hosted final-audit lens is retried ------------------------------------------------------------------------------------
mkdir -p "$work/panel"; : > "$work/panel/calls"
out="$(harness 'WORKFLOW_FINAL_AUDIT_LENS_SECONDS=2' "
    audit_call() {
        echo \"\$2\" >> '$work/panel/calls'
        if [[ \$(wc -l < '$work/panel/calls') -lt 2 ]]; then sleep 2971 > /dev/null 2>&1; fi
        printf '%s' '{\"schema\":\"uncle.artifact/v1\",\"kind\":\"final-audit-worker-packet\",\"findings\":[]}' > \"\$3\"
    }
    workflow_bounded_lens final-audit final-audit-review-worker-scope '$work/panel/scope.json' '$work/panel' final-audit-worker-packet scope audit_call prompt 2>/dev/null
    echo rc=\$?")"
eq "a lens that hung on a hosted runner is retried and recovers" "$out" rc=0
eq "it ran twice: the original and one retry" "$(wc -l < "$work/panel/calls" | tr -d ' ')" 2
grep -q 'worker-scope-retry' "$work/panel/calls" || bad "the retry did not run under its own name"
pgrep -f "sleep 2971" > /dev/null && bad "the hung lens's child was left running"
[[ $fail == 0 ]] && echo "hosted-writer-ceiling-test.sh: ok"
exit $fail
