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
UNCLE_DEFAULT_RUNNER="cline"
UNCLE_DEFAULT_EFFORT="medium"
UNCLE_DEFAULT_CLINE_MODEL="cline-pass/deepseek-v4-pro"
UNCLE_DEFAULT_CLINE_USAGE_MODEL="deepseek/deepseek-v4-flash"
# Free models cost nothing under either billing, so they are offered in both
# lists and say nothing about which purse a stage spends. Kept in step with
# uncle_tui.py's MODEL_CATALOG_FREE by tui-config-test.sh.
UNCLE_CLINE_FREE_MODELS="deepseek/deepseek-v4-flash z-ai/glm-5.3-flash meituan/longcat-2.0 poolside/laguna-s-2.1"

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

uncle_stage_side() {
    case "$UNCLE_REVIEWER_STAGES" in
        *" $1 "*) printf 'reviewer' ;;
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
            kimi)   printf '%s' "$root/scripts/reviewer-kimi.sh" ;;
            codex)  printf 'codex' ;;
            claude) printf '%s' "$root/scripts/reviewer-claude.sh" ;;
            *)      printf '%s' "$root/scripts/reviewer-cline.sh" ;;
        esac
        return 0
    fi
    case "$runner" in
        claude) printf 'claude' ;;
        kimi)   printf '%s' "$root/scripts/agent-kimi.sh" ;;
        codex)  printf '%s' "$root/scripts/agent-codex.sh" ;;
        *)      printf '%s' "$root/scripts/agent-cline.sh" ;;
    esac
}

uncle_stage_runner() {
    local stage="$1" v
    v="$(uncle_config_get "$stage.runner")"
    [[ -n "$v" ]] || v="$(uncle_config_get runner)"
    printf '%s' "${v:-$UNCLE_DEFAULT_RUNNER}"
}

uncle_stage_effort() {
    local stage="$1" v
    case "$stage" in implementation-step-*) stage=implementation ;; esac
    v="$(uncle_config_get "$stage.effort")"
    [[ -n "$v" ]] || v="$(uncle_config_get effort)"
    printf '%s' "${v:-$UNCLE_DEFAULT_EFFORT}"
}

# Only cline is passed a model: claude, kimi, and codex have their own default,
# and a model uncle picked for them would be wrong more often than right.
uncle_stage_model() {
    local stage="$1" v
    [[ "$(uncle_stage_runner "$stage")" == "cline" ]] || return 0
    v="$(uncle_config_get "$stage.model")"
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
    local stage="$1" v model
    case "$stage" in implementation-step-*) stage=implementation ;; esac
    model="$(uncle_config_get "$stage.model")"
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
    v="$(uncle_config_get "$stage.billing")"
    [[ -n "$v" ]] || v="$(uncle_config_get billing)"
    case "$(printf '%s' "${v:-clinepass}" | tr '[:upper:]' '[:lower:]')" in
        cline-usage|usage|usage-based|cline_usage) printf 'cline-usage' ;;
        *)                                        printf 'clinepass' ;;
    esac
}

uncle_stage_cmd() {
    local stage="$1" side
    side="$(uncle_stage_side "$stage")"
    uncle_runner_cmd "$(uncle_stage_runner "$stage")" "$side"
}

# True when the project has a config file at all. Without one there is nothing
# to re-read, and the drivers keep their own built-in defaults.
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
    local stage="$1" v
    case "$stage" in implementation-step-*) stage=implementation ;; esac
    v="$(uncle_config_get "$stage.network")"
    [[ -n "$v" ]] || v="$(uncle_config_get network)"
    case "$(printf '%s' "${v:-false}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) printf 'true' ;;
        *)             printf 'false' ;;
    esac
}
