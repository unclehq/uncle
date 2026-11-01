#!/usr/bin/env bash
# Execute-checklist workers are bounded by progress like the other writers: the idle limit is longer for them (they run browser steps),
# both drivers wrap the runner call, a hosted runner is passed straight through, and a worker whose packet is rejected is retried once.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }

# --- the idle limit -----------------------------------------------------------------------------------------------------------
idle() { env -i PATH="$PATH" HOME="$HOME" UNCLE_CONFIG="$work/config" UNCLE_STATUS_STAGE="$1" ${2:+"$2"} \
    python3 -B -c "import sys; sys.path.insert(0, '$ROOT/scripts/lib'); import writer_deadline as w; print(w.no_progress_seconds())"; }
eq "execute-checklist workers get the longer idle limit" "$(idle execute-checklist-worker-group-1-batch-1)" 180
eq "so does the stage itself" "$(idle execute-checklist)" 180
eq "a text-only writer keeps 45" "$(idle updated-plan-worker-edits-3)" 45
eq "an adversarial worker keeps 45" "$(idle adversarial-review-worker-regression)" 45
eq "the setting still overrides it" "$(idle execute-checklist-worker-1 WORKFLOW_SELF_HOSTED_WRITER_NO_PROGRESS_SECONDS=30)" 30

# --- both drivers wrap the runner call -----------------------------------------------------------------------------------------
for driver in stagegate.sh change-workflow.sh; do
    body="$(awk '/^checklist_run_worker\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/$driver")"
    eq "$driver wraps both runner calls" "$(printf '%s\n' "$body" | grep -c 'workflow_model_writer execute-checklist run_claude')" 2
    printf '%s\n' "$body" | grep -E '^\s+run_claude ' && bad "$driver still calls run_claude directly"
done

# --- the real function, hosted runner ------------------------------------------------------------------------------------------
for driver in stagegate.sh change-workflow.sh; do
    mkdir -p "$work/$driver/logs"; : > "$work/$driver/calls"
    out="$(env -i PATH="$PATH" HOME="$HOME" bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='$work/$driver'; LOG_DIR='$work/$driver/logs'
        stage_uses_self_hosted() { return 1; }
        run_claude() {
            echo \"\$2\" >> '$work/$driver/calls'
            printf '%s' '{\"schema\":\"uncle.artifact/v1\",\"kind\":\"checklist-execution-worker-packet\",\"results\":[{\"id\":\"MC-1\",\"action\":\"a\",\"expected_result\":\"e\",\"actual_result\":\"r\",\"evidence\":\"v\",\"status\":\"PASS\"}]}' > \"\$UNCLE_WORKER_PACKET_PATH\"
        }
        $(awk '/^checklist_run_worker\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/$driver")
        checklist_run_worker '$work/prompt.md' group-1-batch-1 1 '$work/$driver/packet.json'
        echo rc=\$?" 2>&1)"
    [[ "$out" == *rc=0 ]] || bad "$driver: the hosted worker did not complete: $out"
    eq "$driver: the runner ran once with the worker's log name" "$(cat "$work/$driver/calls")" execute-checklist-worker-group-1-batch-1
    [[ -s "$work/$driver/packet.json" ]] || bad "$driver: no packet was written"
done

# --- a rejected packet is retried once ----------------------------------------------------------------------------------------
: > "$work/retry-calls"
out="$(env -i PATH="$PATH" HOME="$HOME" bash --norc --noprofile -c "
    ROOT='$ROOT'; STATE_DIR='$work'; LOG_DIR='$work/logs'
    stage_uses_self_hosted() { return 1; }
    run_claude() {
        echo x >> '$work/retry-calls'
        if (( \$(wc -l < '$work/retry-calls') == 1 )); then echo not-json > \"\$UNCLE_WORKER_PACKET_PATH\"; else
            printf '%s' '{\"schema\":\"uncle.artifact/v1\",\"kind\":\"checklist-execution-worker-packet\",\"results\":[{\"id\":\"MC-1\",\"action\":\"a\",\"expected_result\":\"e\",\"actual_result\":\"r\",\"evidence\":\"v\",\"status\":\"PASS\"}]}' > \"\$UNCLE_WORKER_PACKET_PATH\"; fi
    }
    $(awk '/^checklist_run_worker\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$ROOT/scripts/stagegate.sh")
    checklist_run_worker '$work/prompt.md' b 1 '$work/retry.json' 2>/dev/null
    echo rc=\$?" 2>&1)"
[[ "$out" == *rc=0 ]] || bad "the retry did not recover: $out"
eq "a rejected packet is run exactly twice" "$(wc -l < "$work/retry-calls" | tr -d ' ')" 2
[[ $fail == 0 ]] && echo "execute-checklist-deadline-test.sh: ok"
exit $fail
