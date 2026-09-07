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
#   <stage>.runner | <stage>.effort | <stage>.model VALUE
#
# The older global keys (runner / model / effort / reviewer, and a bare
# "<stage> <model>" line) are still honored as the fallback for a stage the
# file does not configure, so a config written before the per-stage format
# keeps working until it is next saved.

UNCLE_REVIEWER_STAGES=" adversarial-review manual-checklist final-audit "
UNCLE_DEFAULT_RUNNER="cline"
UNCLE_DEFAULT_EFFORT="medium"
UNCLE_DEFAULT_CLINE_MODEL="cline-pass/deepseek-v4-pro"

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
    v="$(uncle_config_get "$stage.effort")"
    [[ -n "$v" ]] || v="$(uncle_config_get effort)"
    printf '%s' "$v"
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
    printf '%s' "${v:-$UNCLE_DEFAULT_CLINE_MODEL}"
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
