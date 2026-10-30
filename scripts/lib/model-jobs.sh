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
