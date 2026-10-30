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
