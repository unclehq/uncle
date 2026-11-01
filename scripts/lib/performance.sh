#!/usr/bin/env bash
# One atomic record per completed attempt, safe for concurrent/speculative
# stages. Observability must not change the outcome of a workflow.
#
# The library directory is worked out once, when this file is sourced: perf_record, perf_stage and perf_stream run on every model call
# and every state, and `${BASH_SOURCE[0]%/*}` inside them started a process each time.
PERF_LIB_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
perf_record() (
    [[ "${WORKFLOW_METRICS:-1}" == 1 && -n "${STATE_DIR:-}" ]] || exit 0
    local timing_dir="${UNCLE_TIMING_DIR:-}"
    # One process builds, prices and publishes the record and refreshes the session totals (it was jq, mktemp, date, usage-cost.py and
    # session-totals.py). Arguments: kind stage elapsed status [log runner model effort]. Never fails the workflow.
    python3 "$PERF_LIB_DIR/perf_record.py" "$STATE_DIR" "$1" "$2" "$3" "$4" "${5:-/dev/null}" "${6:-}" "${7:-}" "${8:-}" \
        "${state:-}" "${timing_dir##*/}" "${UNCLE_SPECULATIVE:-false}" || true
    exit 0
)

# State boundaries are separate from model attempts: they include driver work
# and human waits, and remain readable while a build is still running.
perf_stage() {
    [[ -n "${UNCLE_TIMING_DIR:-}" && "${WORKFLOW_METRICS:-1}" == 1 ]] || return 0
    export UNCLE_TIMING_STAGE="$1"
    python3 -B "$PERF_LIB_DIR/build_timing.py" stage "$1" 2>/dev/null || true
}

# Transparent raw-stream observation; native adapters retain their own events.
perf_stream() {
    if [[ -n "${UNCLE_TIMING_DIR:-}" && "${WORKFLOW_METRICS:-1}" == 1 ]]; then
        UNCLE_TIMING_MODEL="${model:-}" python3 -B "$PERF_LIB_DIR/runner_timing.py" stream "$1"
    else
        cat
    fi
}
export UNCLE_TIMING_HELPER="$PERF_LIB_DIR/runner_timing.py"
