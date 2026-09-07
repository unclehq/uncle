# Gate resolution: local project gates first, installed uncle gates second.
#
# Gates are the output rules a plan-producing stage must satisfy (see
# lib/gates/GATES.md). A project can override the installed gates by dropping
# its own GATES.md at the project root or under .uncle/gates/; the resolver
# picks the most specific one that exists and reports which was chosen.
#
#   gates_file              -> absolute path of the gates file to use (empty if none)
#   gates_source            -> one of: override, local-root, local-uncle, installed, none
#   load_gates              -> echo the gates content, prefixed with its source banner

GATES_BASENAME="GATES.md"

gates_file() {
    local f
    # 1. Explicit override wins (tests and scripted use).
    if [[ -n "${UNCLE_GATES:-}" && -s "$UNCLE_GATES" ]]; then
        printf '%s\n' "$UNCLE_GATES"
        return 0
    fi
    # 2. Local gates in the project being worked on.
    for f in "$PWD/$GATES_BASENAME" "$PWD/.uncle/gates/$GATES_BASENAME"; do
        if [[ -s "$f" ]]; then
            printf '%s\n' "$f"
            return 0
        fi
    done
    # 3. Installed gates shipped with uncle.
    if [[ -n "${ROOT:-}" && -s "$ROOT/lib/gates/$GATES_BASENAME" ]]; then
        printf '%s\n' "$ROOT/lib/gates/$GATES_BASENAME"
        return 0
    fi
    return 0
}

gates_source() {
    local f
    f="$(gates_file)"
    if [[ -z "$f" ]]; then
        printf 'none\n'
    elif [[ -n "${UNCLE_GATES:-}" && "$f" == "$UNCLE_GATES" ]]; then
        printf 'override\n'
    elif [[ "$f" == "$PWD/$GATES_BASENAME" || "$f" == "$PWD/.uncle/gates/$GATES_BASENAME" ]]; then
        printf 'local\n'
    else
        printf 'installed\n'
    fi
}

# Print the gates content with a one-line provenance banner. The banner tells
# the operator (and the audit record) whether the plan was gated by the
# project's own gates or by the gates installed with uncle.
load_gates() {
    local f
    f="$(gates_file)"
    [[ -n "$f" ]] || return 0
    printf '# Output gates: %s (%s)\n\n' "$f" "$(gates_source)"
    cat "$f"
}

# Stages that write a plan must satisfy the output gates. The gates file is
# resolved local-first (project GATES.md, then .uncle/gates/GATES.md) and
# falls back to the gates installed with uncle (lib/gates/GATES.md). The
# gates content is appended to the prompt sent to the agent, never to the
# prompt file on disk. Requires LOG_DIR (set by the calling driver).
PLAN_STAGES=" project-plan updated-plan change-plan updated-change-plan "

# Echo the prompt path the stage should read: the original prompt file for
# non-plan stages, or a temp copy with the gates appended for plan stages.
gated_prompt() {
    local prompt_file="$1"
    local log_name="$2"
    case "$PLAN_STAGES" in
        *" $log_name "*) ;;
        *) printf '%s\n' "$prompt_file"; return 0 ;;
    esac
    local gates
    gates="$(gates_file)"
    if [[ -z "$gates" ]]; then
        printf '%s\n' "$prompt_file"
        return 0
    fi
    local combined="$LOG_DIR/${log_name}.gated-prompt.md"
    {
        cat "$prompt_file"
        printf '\n\n---\n\n# Output gates (binding)\n\nThe plan you write must pass every gate below. Resolve the gates in this\norder: a project-local GATES.md or .uncle/gates/GATES.md wins; otherwise the\ngates installed with uncle apply.\n\n'
        load_gates
    } > "$combined"
    echo "Output gates: $(gates_source) ($(gates_file))" >&2
    printf '%s\n' "$combined"
}
