# Per-stage settings, read from the project's .uncle/config at the moment a
# stage starts.
#
# The launcher used to resolve the whole config into environment variables once,
# when it spawned the driver. That made every setting a snapshot: a run stops at
# four human gates, which is exactly when an operator looks at what a stage
# produced and decides the next one should run somewhere else — and that edit
# reached nothing, because the driver was still holding the values it was
# started with.
#
# So the file is the authority and it is re-read per stage. A WORKFLOW_* value
# in the environment still wins, for a driver invoked directly with an explicit
# override, but nothing derives one from the file behind the operator's back.
#
# Format (see .uncle/config.example):
#   <stage>.runner | <stage>.effort | <stage>.model | <stage>.network VALUE
#
# The older global keys (runner / model / effort / reviewer, and a bare
# "<stage> <model>" line) are still honored as the fallback for a stage the
# file does not configure, so a config written before the per-stage format
# keeps working until it is next saved.

UNCLE_REVIEWER_STAGES=" adversarial-review test-review manual-checklist final-audit "
UNCLE_DEFAULT_EFFORT="low"
UNCLE_DEFAULT_CLINE_MODEL="cline-pass/deepseek-v4-pro"
UNCLE_DEFAULT_CLINE_USAGE_MODEL="deepseek/deepseek-v4-flash"
# Free models cost nothing under either billing, so they are offered in both
# lists and say nothing about which purse a stage spends. Kept in step with
# uncle_tui.py's MODEL_CATALOG_FREE by tui-config-test.sh.
UNCLE_CLINE_FREE_MODELS="deepseek/deepseek-v4-flash z-ai/glm-5.3-flash poolside/laguna-s-2.1"

uncle_config_file() {
    printf '%s' "${UNCLE_CONFIG:-${PROJECT_ROOT:-$PWD}/.uncle/config}"
}

# Print the value of one key, or nothing. Comments and blank lines are ignored;
# a repeated key takes its first value, which is what the writers produce.
uncle_config_get() {
    local key="$1" file line
    file="$(uncle_config_file)"
    [[ -s "$file" ]] || return 0
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | tr -s '[:space:]' ' ')"
        line="${line# }"
        line="${line% }"
        [[ -n "$line" ]] || continue
        if [[ "${line%% *}" == "$key" && "$line" == *" "* ]]; then
            printf '%s' "${line#* }"
            return 0
        fi
    done < "$file"
    return 0
}

# The preview is deliberately not a Configure row: it is an implementation
# shortcut, not an independently approved stage.  It therefore inherits the
# first configured model stage, including that stage's runner.  Looking up the
# model alone is unsafe: `local/foo` belongs to OpenCode, not to Cline.
uncle_first_configured_model_stage() {
    local file line key value
    file="$(uncle_config_file)"
    [[ -r "$file" ]] || return 0
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | tr -s '[:space:]' ' ')"
        line="${line# }"
        [[ "${line%% *}" == *.model ]] || continue
        key="${line%% *}"
        value="${line#* }"
        [[ -n "$value" ]] || continue
        printf '%s' "${key%.model}"
        return 0
    done < "$file"
}

# Base and delta are executions of the configured checklist stage.
uncle_config_stage() {
    case "$1" in
        *-review-worker-*) printf '%s' "${1%%-review-worker-*}" ;;
        preview-build)
            local first_model_stage
            first_model_stage="$(uncle_first_configured_model_stage)"
            [[ -n "$first_model_stage" ]] && printf '%s' "$first_model_stage" || printf '%s' "$1"
            ;;
        plan-executability) printf 'adversarial-review' ;;
        plan-recovery) printf 'updated-plan' ;;
        manual-checklist-base|manual-checklist-delta) printf 'manual-checklist' ;;
        # A driver-owned worker inherits the parent stage's runner, model,
        # effort, billing, and network policy for every supported runner.
        *-worker-*) printf '%s' "${1%%-worker-*}" ;;
        implementation-step-*|implementation-report) printf 'implementation' ;;
        *) printf '%s' "$1" ;;
    esac
}

# <stage>.<key> from the config. A repair pass has its own key so it can run
# on a stronger model than bulk implementation; unset, it inherits
# implementation's setting, which is what it always used.
uncle_stage_key() {
    local stage="$1" key="$2" v
    v="$(uncle_config_get "$stage.$key")"
    if [[ -z "$v" && "$stage" == repair ]]; then
        v="$(uncle_config_get "implementation.$key")"
    fi
    printf '%s' "$v"
}

uncle_stage_side() {
    # Preview inherits a configured stage's runner/model, but it is always an
    # implementation write stage. If the inherited model comes from a review
    # stage (for example adversarial-review's self-hosted model), resolving its
    # side after the alias launches reviewer-self-hosted without --max-turns.
    # OpenCode then rejects it before it sees the prompt. Keep the inherited
    # runner/model pairing while preserving preview's agent protocol.
    [[ "$1" == "preview-build" ]] && { printf '%s' agent; return 0; }
    [[ "$1" == *-review-worker-* ]] && { printf '%s' reviewer; return 0; }
    local stage
    stage="$(uncle_config_stage "$1")"
    case "$UNCLE_REVIEWER_STAGES" in
        *" $stage "*) printf 'reviewer' ;;
        *)        printf 'agent' ;;
    esac
}

# The CLI that runs one stage. The sides are not interchangeable: an agent
# stage writes code, a reviewer stage must stay read-only, and codex has no
# agent shim.
uncle_runner_cmd() {
    local runner="$1" side="$2" root="${ROOT:-.}"
    if [[ "$side" == "reviewer" ]]; then
        case "$runner" in
        aider|opencode|self-hosted) printf '%s' "$root/scripts/$side-self-hosted.sh" ;;
            kimi)   printf '%s' "$root/scripts/reviewer-kimi.sh" ;;
            codex)  printf 'codex' ;;
            claude) printf '%s' "$root/scripts/reviewer-claude.sh" ;;
            *)      printf '%s' "$root/scripts/reviewer-cline.sh" ;;
        esac
        return 0
    fi
    case "$runner" in
        aider|opencode|self-hosted) printf '%s' "$root/scripts/$side-self-hosted.sh" ;;
        claude) printf 'claude' ;;
        kimi)   printf '%s' "$root/scripts/agent-kimi.sh" ;;
        codex)  printf '%s' "$root/scripts/agent-codex.sh" ;;
        *)      printf '%s' "$root/scripts/agent-cline.sh" ;;
    esac
}

# Only executable regular PATH files count; never execute a discovery probe.
uncle_installed_runners() {
    local binary runner rest dir found
    for binary in claude codex kimi cline opencode; do
        rest="${PATH-}:"
        found=false
        while [[ "$rest" == *:* ]]; do
            dir="${rest%%:*}"; rest="${rest#*:}"
            dir="${dir:-.}"
            if [[ -d "$dir" && ( ! -r "$dir" || ! -x "$dir" ) ]]; then
                printf 'uncle: cannot search PATH directory: %s\n' "$dir" >&2
                continue
            fi
            if [[ -f "$dir/$binary" ]]; then
                if [[ -x "$dir/$binary" ]]; then found=true; break; fi
                printf 'uncle: not executable: %s\n' "$dir/$binary" >&2
            fi
        done
        if [[ "$found" == true ]]; then
            runner="$binary"
            [[ "$binary" != opencode ]] || runner=self-hosted
            printf '%s\n' "$runner"
        fi
    done
}

uncle_no_runner() {
    echo 'uncle: no agents installed. Install claude, codex, kimi, cline, or opencode and add its executable to PATH.' >&2
    return 1
}

# Dynamically scoped in each driver invocation, so command/model share a runner.
# Explicit commands bypass discovery, including when no binaries are installed.
uncle_resolve_stage_runner() {
    local stage="$1" side="$2" var global
    var="WORKFLOW_${side}_CMD_$(printf '%s' "$stage" | tr '[:lower:]-.' '[:upper:]__')"
    global="WORKFLOW_${side}_CMD"
    UNCLE_RESOLVED_RUNNER=""
    if [[ -n "${!var:-}" || -n "${!global:-}" ]]; then
        stage="$(uncle_config_stage "$stage")"
        UNCLE_RESOLVED_RUNNER="$(uncle_stage_key "$stage" runner)"
        [[ -n "$UNCLE_RESOLVED_RUNNER" ]] || UNCLE_RESOLVED_RUNNER="$(uncle_config_get runner)"
        case "$UNCLE_RESOLVED_RUNNER" in opencode|aider) UNCLE_RESOLVED_RUNNER=self-hosted ;; esac
        return 0
    fi
    UNCLE_RESOLVED_RUNNER="$(uncle_stage_runner "$stage")"
    [[ -n "$UNCLE_RESOLVED_RUNNER" ]] || uncle_no_runner
}

uncle_stage_runner() {
    local stage v
    stage="$(uncle_config_stage "$1")"
    v="$(uncle_stage_key "$stage" runner)"
    [[ -n "$v" ]] || v="$(uncle_config_get runner)"
    [[ "$v" != "opencode" && "$v" != "aider" ]] || v=self-hosted
    if [[ -z "$v" ]]; then
        v="$(uncle_installed_runners)"
        v="${v%%$'\n'*}"
    fi
    printf '%s' "$v"
}

uncle_stage_effort() {
    local stage v
    stage="$(uncle_config_stage "$1")"
    case "$stage" in implementation-step-*|implementation-report) stage=implementation ;; esac
    v="$(uncle_stage_key "$stage" effort)"
    [[ -n "$v" ]] || v="$(uncle_config_get effort)"
    if [[ -z "$v" ]]; then
        case "$stage" in
            adversarial-review|project-plan|implementation|repair) v=medium ;;
            *) v="$UNCLE_DEFAULT_EFFORT" ;;
        esac
    fi
    printf '%s' "$v"
}

# Cline and self-hosted stages use explicit models; other runners have their own default,
# and a model uncle picked for them would be wrong more often than right.
uncle_stage_model() {
    local stage v runner
    stage="$(uncle_config_stage "$1")"
    runner="${2-$(uncle_stage_runner "$stage")}"
    if [[ "$runner" == "self-hosted" ]]; then
        v="${UNCLE_SELF_HOSTED_MODEL:-$(uncle_stage_key "$stage" model)}"
        [[ -n "$v" ]] || v="$(uncle_config_get self-hosted.model)"
        printf '%s' "$v"
        return 0
    fi
    if [[ "$runner" == "claude" ]]; then
        # A claude stage ran on the CLI's default tier with no way to choose
        # one, even though the config header documents `<stage>.model` and both
        # claude paths -- the bare CLI for an agent, reviewer-claude.sh for a
        # reviewer -- already take --model. Empty stays empty, so a stage that
        # names no model keeps the default it has always had.
        uncle_stage_key "$stage" model
        return 0
    fi
    if [[ "$runner" == "kimi" ]]; then
        # Kimi's shell accepts the dispatch token `kimi`; the selected raw
        # provider id travels separately so it is not mistaken for a runner
        # command or silently discarded by the adapter.
        v="$(uncle_stage_key "$stage" model)"
        [[ -n "$v" ]] || v="$(uncle_config_get "$stage")"
        [[ -n "$v" ]] || v="$(uncle_config_get model)"
        [[ -n "$v" ]] && export WORKFLOW_KIMI_MODEL="$v"
        printf 'kimi'
        return 0
    fi
    [[ "$runner" == "cline" ]] || return 0
    v="$(uncle_stage_key "$stage" model)"
    [[ -n "$v" ]] || v="$(uncle_config_get "$stage")"
    if [[ -z "$v" && "$(uncle_stage_side "$stage")" == "reviewer" ]]; then
        v="$(uncle_config_get reviewer)"
    fi
    [[ -n "$v" ]] || v="$(uncle_config_get model)"
    if [[ -z "$v" ]]; then
        # No model configured: the default depends on how the stage is paid
        # for, because the two billings are two different model catalogues.
        if [[ "$(uncle_stage_billing "$stage")" == "cline-usage" ]]; then
            v="$UNCLE_DEFAULT_CLINE_USAGE_MODEL"
        else
            v="$UNCLE_DEFAULT_CLINE_MODEL"
        fi
    fi
    printf '%s' "$v"
}

# How a cline stage is paid for: clinepass | cline-usage. Default clinepass.
#
# Not a flag: within cline's default provider the modelType prefix decides, so
# `cline-pass/kimi-k3` spends the subscription and a vendor-prefixed `kimi-k3`
# spends usage billing. An explicit model therefore settles this on its own,
# and it wins over the setting -- the id is what cline actually receives, and a
# setting that disagreed with it would describe a run that never happened.
uncle_stage_billing() {
    local stage v model
    stage="$(uncle_config_stage "$1")"
    case "$stage" in implementation-step-*) stage=implementation ;; esac
    model="$(uncle_stage_key "$stage" model)"
    [[ -n "$model" ]] || model="$(uncle_config_get "$stage")"
    if [[ -n "$model" ]]; then
        # A free model is not evidence either way: it runs under both.
        case " $UNCLE_CLINE_FREE_MODELS " in
            *" $model "*) model="" ;;
        esac
    fi
    if [[ -n "$model" ]]; then
        case "$model" in
            cline-pass/*) printf 'clinepass' ;;
            *)            printf 'cline-usage' ;;
        esac
        return 0
    fi
    v="$(uncle_stage_key "$stage" billing)"
    [[ -n "$v" ]] || v="$(uncle_config_get billing)"
    case "$(printf '%s' "${v:-clinepass}" | tr '[:upper:]' '[:lower:]')" in
        cline-usage|usage|usage-based|cline_usage) printf 'cline-usage' ;;
        *)                                        printf 'clinepass' ;;
    esac
}

uncle_stage_cmd() {
    local stage="$1" side runner
    side="$(uncle_stage_side "$stage")"
    runner="${2-$(uncle_stage_runner "$stage")}"
    [[ -n "$runner" ]] || { uncle_no_runner; return 1; }
    uncle_runner_cmd "$runner" "$side"
}

# True when the project has a config file at all. Without one there is nothing
# to re-read; runner selection still uses PATH discovery.
uncle_has_config() {
    [[ -s "$(uncle_config_file)" ]]
}

# Shared execution precedence: explicit stage environment, config, medium.
uncle_effective_stage_effort() {
    local stage="$1" var value
    var="WORKFLOW_EFFORT_$(printf '%s' "$stage" | tr '[:lower:]-.' '[:upper:]__')"
    value="${!var:-}"
    if [[ -z "$value" && "$stage" == implementation-step-* ]]; then
        value="${WORKFLOW_EFFORT_IMPLEMENTATION:-}"
    fi
    [[ -n "$value" ]] || value="$(uncle_stage_effort "$stage")"
    printf '%s' "$value"
}

# Whether a stage's sandbox may reach the network. Default false.
#
# codex's workspace-write sandbox denies network access unless its config says
# otherwise, and that denial includes binding a loopback port. A checklist
# stage that has to serve the site it is verifying cannot start that server, so
# every row depending on the running page records BLOCKED -- and records it
# again on every repair, because no amount of retrying grants a socket. That is
# a prerequisite, not a failure, so it is a setting rather than a retry.
#
# It stays opt-in per stage because the boundary is the product: an agent that
# writes code and can also open a socket is a different proposition from one
# that cannot, and that trade belongs to the operator, not to a default.
uncle_stage_network() {
    local stage v
    stage="$(uncle_config_stage "$1")"
    case "$stage" in implementation-step-*) stage=implementation ;; esac
    v="$(uncle_stage_key "$stage" network)"
    [[ -n "$v" ]] || v="$(uncle_config_get network)"
    case "$(printf '%s' "${v:-false}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) printf 'true' ;;
        *)             printf 'false' ;;
    esac
}
