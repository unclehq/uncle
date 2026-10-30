#!/usr/bin/env bash
# Stage runtime policy. Definitions only; the caller supplies configuration
# and runner hooks, stage order, and the optional status path.

# The investigate/format split (test-review, updated-plan) exists for weak
# self-hosted models that lose an exact JSON schema over a long, read-heavy
# turn. Proprietary models (claude, codex, ...) do not show that failure, and
# the split only adds an extra call and an extra place to fail, so it is
# gated on the stage's actually-configured runner rather than applied
# unconditionally.
# Requirements intentionally inherit the project-plan configuration so users
# configure this coupled early-planning pair once.  Keep runner lookup aligned
# with the existing model lookup; otherwise a local model reaches the default
# Claude command after the self-hosted paths are split.
app_stage_runner_config_name() {
    case "$1" in
        requirements|requirements-investigate) printf '%s\n' project-plan ;;
        preview-build-part-*) printf '%s\n' preview-build ;;
        *) printf '%s\n' "$1" ;;
    esac
}

# Whether this stage's agent can be forced to answer in schema-checked JSON (see run_claude): the direct
# Claude CLI only.  Codex, self-hosted models and a custom command keep the drivers' file contracts.
app_stage_supports_structured_output() {
    local stage="$1" UNCLE_RESOLVED_RUNNER
    [[ "${WORKFLOW_STRUCTURED_OUTPUT:-1}" == 1 ]] || return 1
    stage="$(stage_runner_config_name "$stage")"
    uncle_resolve_stage_runner "$stage" AGENT 2>/dev/null || return 1
    [[ "$UNCLE_RESOLVED_RUNNER" == claude ]] && [[ "$(stage_agent_cmd "$stage" 2>/dev/null)" == *claude ]]
}

# Whether this stage's agent can be forced to answer in schema-checked JSON (see run_claude): the direct Claude
# CLI only -- also when it runs through native_stage.py, which relays the validated object.  Codex, self-hosted
# models and a custom command keep the file contract.
change_stage_supports_structured_output() {
    local stage="$1" UNCLE_RESOLVED_RUNNER
    [[ "${WORKFLOW_STRUCTURED_OUTPUT:-1}" == 1 ]] || return 1
    uncle_resolve_stage_runner "$stage" AGENT 2>/dev/null || return 1
    [[ "$UNCLE_RESOLVED_RUNNER" == claude ]] && [[ "$(stage_agent_cmd "$stage" 2>/dev/null)" == *claude ]]
}

app_stage_uses_self_hosted() {
    local stage="$1" side="$2" UNCLE_RESOLVED_RUNNER
    stage="$(stage_runner_config_name "$stage")"
    uncle_resolve_stage_runner "$stage" "$side" 2>/dev/null || true
    [[ "$UNCLE_RESOLVED_RUNNER" == self-hosted ]]
}

change_stage_uses_self_hosted() {
    local stage="$1" side="$2" UNCLE_RESOLVED_RUNNER
    uncle_resolve_stage_runner "$stage" "$side" 2>/dev/null || true
    [[ "$UNCLE_RESOLVED_RUNNER" == self-hosted ]]
}

# Report the current stage to the TUI status channel. The exports feed the
# agent shims' own status writes; the start event written here covers every
# stage directly, including runners with no shim (plain claude, reviewers).
app_status_stage_context() {
    local log_name="$1"
    local model="${2:-(runner default)}"
    local mode="${3:-act}"
    local s i=1 index=0 n=0
    for s in $STATUS_STAGE_SEQ; do
        n=$((n + 1))
        if [[ "$s" == "$log_name" ]]; then
            index=$i
        fi
        i=$((i + 1))
    done
    local turns
    turns="$(stage_turns "$log_name")"
    export UNCLE_STATUS_STAGE="$log_name"
    export UNCLE_STATUS_STAGE_INDEX="$index"
    export UNCLE_STATUS_STAGE_TOTAL="$n"
    export UNCLE_STATUS_STAGE_TURNS="$turns"
    # Read per stage, like every other setting: an operator who discovers at a
    # gate that verification needs a local server can turn it on there.
    UNCLE_STAGE_NETWORK="$(uncle_stage_network "$log_name")"
    export UNCLE_STAGE_NETWORK
    if [[ -n "${UNCLE_STATUS_FILE:-}" ]]; then
        printf '{"event":"start","model":"%s","mode":"%s","stage":"%s","stage_index":%s,"stage_total":%s,"stage_turns":%s}\n' \
            "$model" "$mode" "$log_name" "$index" "$n" "$turns" \
            >> "$UNCLE_STATUS_FILE"
    fi
}

# Report the current stage to the TUI status channel. The exports feed the
# agent shims' own status writes; the start event written here covers every
# stage directly, including runners with no shim (plain claude, reviewers).
change_status_stage_context() {
    local log_name="$1"
    local turns="${2:-0}"
    local model="${3:-(runner default)}"
    local mode="${4:-act}"
    local base="${log_name%%-step-*}"     # implementation-step-3 -> implementation
    base="${base%-base}"                   # manual-checklist-base -> manual-checklist
    base="${base%-delta}"                  # manual-checklist-delta -> manual-checklist
    local s i=1 index=0 n=0
    for s in $STATUS_STAGE_SEQ; do
        n=$((n + 1))
        if [[ "$s" == "$base" ]]; then
            index=$i
        fi
        i=$((i + 1))
    done
    export UNCLE_STATUS_STAGE="$log_name"
    export UNCLE_STATUS_STAGE_INDEX="$index"
    export UNCLE_STATUS_STAGE_TOTAL="$n"
    export UNCLE_STATUS_STAGE_TURNS="$turns"
    # Keyed on the normalized name, so a -step-/-base/-delta variant inherits
    # the setting its parent stage was configured with.
    UNCLE_STAGE_NETWORK="$(uncle_stage_network "$base")"
    export UNCLE_STAGE_NETWORK
    if [[ -n "${UNCLE_STATUS_FILE:-}" ]]; then
        printf '{"event":"start","model":"%s","mode":"%s","stage":"%s","stage_index":%s,"stage_total":%s,"stage_turns":%s}\n' \
            "$model" "$mode" "$log_name" "$index" "$n" "$turns" \
            >> "$UNCLE_STATUS_FILE"
    fi
}
