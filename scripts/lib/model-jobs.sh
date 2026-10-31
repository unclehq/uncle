# Bounded model work for self-hosted planning. Hosted scheduling is unchanged.
# Sourced by the entry points as well as hermetic extracted-function tests.
workflow_model_jobs() {
    local stage="$1" value="${WORKFLOW_SELF_HOSTED_STAGE_JOBS:-}"
    if ! stage_uses_self_hosted "$stage" AGENT; then printf '0\n'; return 0; fi
    if [[ -z "$value" ]] && declare -f uncle_config_get >/dev/null; then
        value="$(uncle_config_get self-hosted.stage-jobs)"
    fi
    value="${value:-4}"
    case "$value" in
        [1-8]) printf '%s\n' "$value" ;;
        *) echo 'Invalid self-hosted.stage-jobs / WORKFLOW_SELF_HOSTED_STAGE_JOBS (use 1–8); using 4.' >&2
           printf '4\n' ;;
    esac
}

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
    if ! stage_uses_self_hosted "$stage" AGENT; then "$@"; return $?; fi
    local limit pid guard heartbeat status=0
    limit="$(UNCLE_STATUS_STAGE="$stage-worker-edits" python3 -B "$ROOT/scripts/lib/writer_deadline.py" seconds)" || return 1
    heartbeat="$(mktemp "${TMPDIR:-/tmp}/uncle-writer-progress.XXXXXX")" || return 1
    ( export UNCLE_WRITER_PROGRESS_FILE="$heartbeat"; "$@" ) &
    pid=$!
    UNCLE_STATUS_STAGE="$stage-worker-edits" python3 -B "$ROOT/scripts/lib/writer_deadline.py" watch "$pid" "$limit" "$3" "$heartbeat" "${LOG_DIR:-/tmp}/$3.jsonl" &
    guard=$!
    wait "$pid" || status=$?
    kill "$guard" 2>/dev/null || true
    wait "$guard" 2>/dev/null || true
    rm -f "$heartbeat"
    return "$status"
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
    local worker="$1" status="$2" detail
    detail="$(tail -n 12 "$LOG_DIR/$worker.log" 2>/dev/null | tr '\n' ' ')"
    printf 'Updated-plan writer %s failed: runner exit code %s; %s\n' "$worker" "$status" "$detail" | tee -a "$LOG_DIR/UPDATED_PLAN.log" >> "$LOG_DIR/UPDATED_PLAN.speculative.log"
}
