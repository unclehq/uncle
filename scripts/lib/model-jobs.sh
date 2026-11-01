# Refill when *any* worker finishes, not when the oldest one finishes. The
# caller retains every PID and owns wait/status handling and packet validation.
# No wait -n: the system Bash on macOS is 3.2.
workflow_model_slot() {
    local limit="$1" pid active
    shift
    [[ "$limit" != 0 ]] || return 0
    while :; do
        active=0
        for pid in "$@"; do
            if kill -0 "$pid" 2>/dev/null; then active=$((active + 1)); fi
        done
        (( active < limit )) && return 0
        sleep 0.05
    done
}

# If prompt preparation fails after siblings launched, finish those siblings
# before a caller starts its fallback. Hosted failure handling stays unchanged.
workflow_model_drain() {
    local limit="$1" pid
    shift
    [[ "$limit" != 0 ]] || return 0
    for pid in "$@"; do wait "$pid" || true; done
}

# Runner selection is shared with the stage driver. Extracted-function tests
# may provide only the historical stage_uses_self_hosted predicate.
workflow_model_runner() {
    local stage="$1" side="${2:-AGENT}"
    if declare -f stage_uses_self_hosted >/dev/null && stage_uses_self_hosted "$stage" "$side"; then
        printf 'self-hosted\n'
    elif declare -f uncle_stage_runner >/dev/null; then
        uncle_stage_runner "$stage"
    else
        printf 'claude\n'
    fi
}

workflow_model_capacity() {
    local runner="${3:-$(workflow_model_runner "$1" "${2:-AGENT}")}" prefix config
    # Keep the default hosted path free of interpreter startup in every unit.
    if [[ "$runner" != self-hosted ]]; then
        prefix="WORKFLOW_$(printf '%s' "$runner" | tr '[:lower:]-' '[:upper:]_')_MAX_CONCURRENCY"
        config="${UNCLE_CONFIG:-${PROJECT_ROOT:-$PWD}/.uncle/config}"
        if [[ -z "$(compgen -A variable "$prefix")" ]] && \
                { [[ ! -s "$config" ]] || ! grep -qE '^[^#]*\.max-concurrency[[:space:]]' "$config"; }; then
            printf '0\n'; return 0
        fi
    fi
    python3 -B "$ROOT/scripts/lib/unit_scheduler.py" capacity "$runner" "$1"
}

workflow_model_granularity() {
    python3 -B "$ROOT/scripts/lib/unit_scheduler.py" granularity "$(workflow_model_runner "$1")" "$1"
}

workflow_model_group_size() {
    python3 -B "$ROOT/scripts/lib/unit_scheduler.py" group-size "$(workflow_model_runner "$1")" "$1"
}

# Call inside the background unit, before any agent work. All fan-outs in this
# driver share the provider pool, including speculative reviewers. The lease
# lives through private retries and is released on every shell exit path.
workflow_model_enter() {
    [[ "${3:-}" != 0 ]] || return 0
    local stage="$1" runner limit
    runner="$(workflow_model_runner "$stage" "${2:-AGENT}")"
    limit="${3:-$(workflow_model_capacity "$stage" "${2:-AGENT}" "$runner")}" || return 1
    [[ "$limit" != 0 ]] || return 0
    UNCLE_MODEL_UNIT_POOL="$STATE_DIR/model-units/$$/$runner"
    mkdir -p "$UNCLE_MODEL_UNIT_POOL"
    UNCLE_MODEL_UNIT_FILE="$(mktemp "$UNCLE_MODEL_UNIT_POOL/pid.XXXXXX")"
    UNCLE_MODEL_UNIT_PID=""
    trap 'workflow_model_leave' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    # Run directly: command substitution introduces another shell on Bash 3.2.
    python3 -B "$ROOT/scripts/lib/unit_scheduler.py" acquire "$UNCLE_MODEL_UNIT_POOL" "$limit" 0 "$$" > "$UNCLE_MODEL_UNIT_FILE" || return 1
    read -r UNCLE_MODEL_UNIT_PID < "$UNCLE_MODEL_UNIT_FILE"
    rm -f "$UNCLE_MODEL_UNIT_FILE"
}

workflow_model_leave() {
    local status=$?
    rm -f "${UNCLE_MODEL_UNIT_FILE:-}"
    [[ -z "${UNCLE_MODEL_UNIT_PID:-}" ]] || python3 -B "$ROOT/scripts/lib/unit_scheduler.py" release "$UNCLE_MODEL_UNIT_POOL" "$UNCLE_MODEL_UNIT_PID" || true
    return "$status"
}

workflow_model_cancel() {
    [[ -d "$STATE_DIR/model-units/$$" ]] || return 0
    python3 -B "$ROOT/scripts/lib/unit_scheduler.py" cancel "$STATE_DIR/model-units/$$" || true
}

# Bound the whole runner call, including streaming, retries and child processes.
workflow_model_writer() {
    local stage="$1"; shift
    local limit=3600 pid guard heartbeat status=0 finding_limit="" idle_mode="" ceiling=""
    # UNCLE_WRITER_CEILING (seconds) is a wall-clock ceiling for any runner, hosted ones included; unset, zero or non-numeric means none.
    [[ "${UNCLE_WRITER_CEILING:-}" =~ ^[1-9][0-9]*$ ]] && ceiling="$UNCLE_WRITER_CEILING"
    # UNCLE_WRITER_SIDE=REVIEWER bounds a reviewer-side call (a panel lens) by the reviewer's configured runner.
    if declare -F stage_uses_self_hosted >/dev/null && stage_uses_self_hosted "$stage" "${UNCLE_WRITER_SIDE:-AGENT}"; then
        limit="$(UNCLE_STATUS_STAGE="$3" python3 -B "$ROOT/scripts/lib/writer_deadline.py" seconds)" || return 1
    else
        idle_mode=ceiling-only
    fi
    [[ -z "$ceiling" ]] || limit="$(python3 -c 'import sys; print(min(map(float, sys.argv[1:])))' "$limit" "$ceiling")"
    if [[ -n "${UNCLE_UPDATED_PLAN_ATTEMPTS_DIR:-}" && -n "${UNCLE_UPDATED_PLAN_FINDINGS:-}" ]]; then
        finding_limit="$(python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" remaining "$UNCLE_UPDATED_PLAN_ATTEMPTS_DIR" "$UNCLE_UPDATED_PLAN_FINDINGS" "$3")" || return 1
        if [[ "$finding_limit" == 0 || "$finding_limit" == 0.0 ]]; then
            echo 'finding wall-time deadline: attempt chain exhausted' >&2
            return 124
        fi
        limit="$(python3 -c 'import sys; print(min(map(float, sys.argv[1:])))' "$limit" "$finding_limit")"
    elif [[ -n "$idle_mode" && -z "$ceiling" ]]; then
        "$@"; return $?
    fi
    heartbeat="$(mktemp "${TMPDIR:-/tmp}/uncle-writer-progress.XXXXXX")" || return 1
    ( export UNCLE_WRITER_PROGRESS_FILE="$heartbeat"; "$@" ) &
    pid=$!
    UNCLE_STATUS_STAGE="$3" python3 -B "$ROOT/scripts/lib/writer_deadline.py" watch "$pid" "$limit" "$3" "$heartbeat" "${LOG_DIR:-/tmp}/$3.jsonl" "$idle_mode" &
    guard=$!
    wait "$pid" || status=$?
    kill "$guard" 2>/dev/null || true
    wait "$guard" 2>/dev/null || true
    if [[ -e "$heartbeat.failed" ]]; then cat "$heartbeat.failed" >&2; status=124; fi
    rm -f "$heartbeat" "$heartbeat.failed"
    return "$status"
}

# One review lens of a panel, bounded by progress. A lens whose packet is missing or invalid is run once more, alone; it is never
# the whole stage that is restarted. Returns nonzero when the lens still has no valid packet, and the caller decides what to do
# without it.
#   workflow_bounded_lens STAGE NAME OUTPUT DIRECTORY KIND LENS CALL_FUNCTION PROMPT
# CALL_FUNCTION is called as `CALL_FUNCTION PROMPT NAME OUTPUT` (NAME is third on the command line, as the deadline expects).
workflow_bounded_lens() {
    local stage="$1" name="$2" output="$3" directory="$4" kind="$5" lens="$6" call="$7" prompt="$8" probe
    probe="$directory/$lens.validated.json"
    UNCLE_WRITER_CEILING="${UNCLE_WRITER_CEILING-${WORKFLOW_FINAL_AUDIT_LENS_SECONDS:-900}}" UNCLE_WRITER_SIDE=REVIEWER \
        workflow_model_writer "$stage" "$call" "$prompt" "$name" "$output" || true
    if ! python3 -B "$ROOT/scripts/lib/worker_packets.py" "$directory" "$probe" --kind "$kind" --expected "$lens" > /dev/null 2>&1; then
        echo "$name did not deliver a valid packet; running that lens once more." >&2
        rm -f "$output" "$output.delivery.json" "$probe"
        UNCLE_WRITER_CEILING="${UNCLE_WRITER_CEILING-${WORKFLOW_FINAL_AUDIT_LENS_SECONDS:-900}}" UNCLE_WRITER_SIDE=REVIEWER \
            workflow_model_writer "$stage" "$call" "$prompt" "$name-retry" "$output" || true
        python3 -B "$ROOT/scripts/lib/worker_packets.py" "$directory" "$probe" --kind "$kind" --expected "$lens" > /dev/null 2>&1 \
            || { rm -f "$probe"; return 1; }
    fi
    rm -f "$probe"
}

# Bound writer fan-out separately from the provider-wide lease pool.
workflow_writer_jobs() {
    local stage="$1" capacity limit
    capacity="$(workflow_model_capacity "$stage")" || return 1
    if ! stage_uses_self_hosted "$stage" AGENT; then printf '%s\n' "$capacity"; return; fi
    limit="$(UNCLE_STATUS_STAGE="$stage" python3 -B "$ROOT/scripts/lib/writer_deadline.py" jobs)" || return 1
    if [[ "$capacity" != 0 && "$capacity" -lt "$limit" ]]; then limit="$capacity"; fi
    printf '%s\n' "$limit"
}

# Preserve evidence before a canonical attempt path is reused. The canonical
# path remains the latest attempt for existing status readers and recovery.
workflow_archive_attempt() {
    local path round candidate stem suffix
    for path in "$@"; do
        [[ -e "$path" ]] || continue
        round=1; stem="$path"; suffix=""
        if [[ "${path##*/}" == *.* ]]; then stem="${path%.*}"; suffix=".${path##*.}"; fi
        if [[ "$suffix" == .json ]]; then
            local archive_dir
            archive_dir="$(dirname "$path")/attempts"
            mkdir -p "$archive_dir" || return 1
            stem="$archive_dir/${stem##*/}"
        fi
        candidate="$stem-r$round$suffix"
        while [[ -e "$candidate" ]]; do
            round=$((round + 1)); candidate="$stem-r$round$suffix"
        done
        cp -Rp "$path" "$candidate" || return 1
    done
}

workflow_terminal_failure() {
    [[ -e "$STATE_DIR/updated-plan-writers-exhausted" || -e "$STATE_DIR/preflight-readonly-violation" ]] ||
        grep -qE 'writer attempts exhausted|read-only preflight violation' "$STATE_DIR/stop-reason" 2>/dev/null
}

workflow_writer_failure() {
    local worker="$1" status="$2" reason="${3:-runner exit code}" detail
    detail="$(tail -n 12 "${4:-$LOG_DIR/$worker.log}" 2>/dev/null | tr '\n' ' ')"
    printf 'Updated-plan writer %s failed: %s %s; %s\n' "$worker" "$reason" "$status" "$detail" | tee -a "$LOG_DIR/UPDATED_PLAN.log" >> "$LOG_DIR/UPDATED_PLAN.speculative.log"
}

workflow_archive_stage() {
    local stage="$1" path
    for path in "$LOG_DIR/$stage"*.log "$LOG_DIR/$stage"*.jsonl; do
        [[ -e "$path" ]] || continue
        [[ "${path##*/}" =~ -r[0-9]+\.(log|jsonl)$ ]] && continue
        workflow_archive_attempt "$path" || return 1
    done
    if [[ "$stage" == updated-change-plan ]]; then
        workflow_archive_stage updated-plan || return 1
    elif [[ "$stage" == updated-* ]]; then
        workflow_archive_attempt "$LOG_DIR/UPDATED_PLAN.log" || return 1
    fi
}

workflow_writer_exhausted() {
    : > "$STATE_DIR/updated-plan-writers-exhausted"
    printf '%s: writer attempts exhausted\n' "$1" > "$STATE_DIR/stop-reason"
    echo 'Updated-plan writer attempts exhausted; completed packets retained for diagnosis.' >&2
}

workflow_deferred_report() {
    if [[ "${UNCLE_SPECULATIVE:-}" == true ]]; then
        # speculate() already redirects stdout to the speculative log.
        python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" report "$1" | tee -a "$LOG_DIR/UPDATED_PLAN.log"
    else
        python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" report "$1" | tee -a "$LOG_DIR/UPDATED_PLAN.log" "$LOG_DIR/UPDATED_PLAN.speculative.log"
    fi
}

workflow_publish_updated_plan() {
    local stage="$1" directory="$2" status=0
    python3 -B "$ROOT/scripts/lib/updated_plan_defer.py" prepare-publication "$directory" "$stage" || status=$?
    if [[ "$status" == 3 ]]; then
        . "$ROOT/scripts/lib/updated-plan-repair.sh"
        run_updated_plan_structure_repair "$directory/publication-candidate.json" "$(cat "$directory/publication-error.log")" "$stage" || return 1
        return 0
    elif [[ "$status" != 0 ]]; then
        return "$status"
    else
        python3 "$ROOT/scripts/lib/publish_agent_artifact.py" "$stage" "$LOG_DIR/$stage.jsonl" . "$directory/merged.json" || return 1
    fi
    workflow_deferred_report "$directory"
}
