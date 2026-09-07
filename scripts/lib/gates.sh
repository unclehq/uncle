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

# Output rules: the shape every reviewed document must have.
#
# GATES.md below is the quality bar for plans, and it binds the plan stages
# only; the stage's prompt owns the target file and the section list.
# OUTPUT_RULES.md is broader — audience, checkable claims, marked assumptions,
# fixed structure, length, banned filler — and applies to every stage that
# writes a markdown document for a human to approve, the requirements
# interpretation included.
#
# Resolved the same way as the gates: an explicit override, then the project's
# own copy, then the copy that ships with uncle.
OUTPUT_RULES_BASENAME="OUTPUT_RULES.md"

output_rules_file() {
    local f
    if [[ -n "${UNCLE_OUTPUT_RULES:-}" && -s "$UNCLE_OUTPUT_RULES" ]]; then
        printf '%s\n' "$UNCLE_OUTPUT_RULES"
        return 0
    fi
    for f in "$PWD/$OUTPUT_RULES_BASENAME" \
             "$PWD/.uncle/$OUTPUT_RULES_BASENAME"; do
        if [[ -s "$f" ]]; then
            printf '%s\n' "$f"
            return 0
        fi
    done
    for f in "${ROOT:-}/lib/gates/$OUTPUT_RULES_BASENAME" \
             "${ROOT:-}/$OUTPUT_RULES_BASENAME"; do
        if [[ -n "${ROOT:-}" && -s "$f" ]]; then
            printf '%s\n' "$f"
            return 0
        fi
    done
    return 0
}

output_rules_source() {
    local f
    f="$(output_rules_file)"
    if [[ -z "$f" ]]; then
        printf 'none\n'
    elif [[ -n "${UNCLE_OUTPUT_RULES:-}" && "$f" == "$UNCLE_OUTPUT_RULES" ]]; then
        printf 'override\n'
    elif [[ "$f" == "$PWD/"* ]]; then
        printf 'local\n'
    else
        printf 'installed\n'
    fi
}

# Stages that write a markdown document for a human to read. Every one of them
# gets the output rules; the plan stages additionally get the plan template.
DOC_STAGES=" requirements project-plan updated-plan preflight implementation execute-checklist baseline change-spec change-plan updated-change-plan adversarial-review test-review manual-checklist manual-checklist-base manual-checklist-delta final-audit "

# Stages that write a plan must satisfy the output gates. The gates file is
# resolved local-first (project GATES.md, then .uncle/gates/GATES.md) and
# falls back to the gates installed with uncle (lib/gates/GATES.md). The
# gates content is appended to the prompt sent to the agent, never to the
# prompt file on disk. Requires LOG_DIR (set by the calling driver).
PLAN_STAGES=" project-plan updated-plan change-plan updated-change-plan "

# Echo the prompt path the stage should read: the original prompt file for
# stages with nothing to append, or a temp copy with the output rules (and the
# plan gates for plan stages) appended. A reviewer stage additionally gets a
# final note reconciling Rule 0 with the reviewer contract: the reviewer is
# read-only, so the document is its final message, not a file it cannot write.
gated_prompt() {
    local prompt_file="$1"
    local log_name="$2"
    local role="${3:-agent}"

    local is_plan=0 is_doc=0
    case "$PLAN_STAGES" in
        *" $log_name "*) is_plan=1 ;;
    esac
    case "$DOC_STAGES" in
        *" $log_name "*) is_doc=1 ;;
    esac

    local gates rules
    gates=""
    rules=""
    [[ "$is_plan" == "1" ]] && gates="$(gates_file)"
    [[ "$is_doc" == "1" ]] && rules="$(output_rules_file)"

    if [[ -z "$gates" && -z "$rules" ]]; then
        printf '%s\n' "$prompt_file"
        return 0
    fi

    local combined="$LOG_DIR/${log_name}.gated-prompt.md"
    {
        cat "$prompt_file"
        if [[ -n "$rules" ]]; then
            printf '\n\n---\n\n# Output rules (binding)\n\nThe document you write must satisfy every rule below. They govern its shape;\nthis stage'"'"'s instructions above govern its content. Where they disagree about\nshape, these rules win.\n\n'
            cat "$rules"
        fi
        if [[ -n "$gates" ]]; then
            printf '\n\n---\n\n# Output gates (binding)\n\nThe plan you write must pass every gate below. Resolve the gates in this\norder: a project-local GATES.md or .uncle/gates/GATES.md wins; otherwise the\ngates installed with uncle apply.\n\n'
            load_gates
        fi
        if [[ "$is_doc" == "1" ]]; then
            printf '\n\n# Compact output budget\n\nPlanning artifacts are checked by the driver: at most %s UTF-8 bytes and %s lines. Target 12,000 bytes where the complete contract fits. Preserve every required ID, assertion, threshold, failure behavior, disposition, command and protected path. Remove duplicated rationale and background. Cite existing evidence by file and section instead of copying it. Keep all normative content in the named document; do not create summary sidecars or move obligations into evidence files. If mandatory content cannot fit, preserve it in full; the driver will pause for an explicit budget adjustment.\n' "${WORKFLOW_DOC_MAX_BYTES:-20000}" "${WORKFLOW_DOC_MAX_LINES:-400}"
        fi
        if [[ "$role" == "reviewer" ]]; then
            printf '\n\n---\n\n# Reviewer output (binding)\n\nYou run read-only: you cannot write files, so Rule 0 above cannot apply to\nyou. The document the stage asked for is your final assistant message:\nreturn it in full as that message — not a path, not a summary, not a note\nabout a file you could not write.\n'
        fi
    } > "$combined"
    [[ -n "$rules" ]] && echo "Output rules: $(output_rules_source) ($rules)" >&2
    [[ -n "$gates" ]] && echo "Output gates: $(gates_source) ($gates)" >&2
    printf '%s\n' "$combined"
}

# Check newly produced planning artifacts only; never rewrite approved inputs.
check_document_budget() {
    local file="$1" bytes lines max_bytes="${WORKFLOW_DOC_MAX_BYTES:-20000}" max_lines="${WORKFLOW_DOC_MAX_LINES:-400}"
    case "${file##*/}" in
        REQUIREMENTS_INTERPRETATION.md|PROJECT_PLAN.md|UPDATED_PROJECT_PLAN.md|ADVERSARIAL_REVIEW.md|BASELINE_REPORT.md|CHANGE_SPEC.md|CHANGE_PLAN.md) ;;
        *) return 0 ;;
    esac
    [[ -s "$file" ]] || { echo "Required planning artifact is missing or empty: $file" >&2; return 1; }
    case "$max_bytes$max_lines" in
        *[!0-9]*|"") echo "Document budgets must be positive integers." >&2; return 1 ;;
    esac
    if ! awk -v b="$max_bytes" -v l="$max_lines" 'BEGIN {exit !(b>0 && l>0)}'; then
        echo "Document budgets must be positive integers." >&2; return 1
    fi
    bytes=$(wc -c < "$file")
    lines=$(awk 'END {print NR+0}' "$file")
    if ! awk -v b="$bytes" -v l="$lines" -v mb="$max_bytes" -v ml="$max_lines" 'BEGIN {exit !(b<=mb && l<=ml)}'; then
        echo "Document budget exceeded: $file ($bytes bytes, $lines lines; limits $max_bytes bytes, $max_lines lines)." >&2
        echo "Artifact preserved. Shorten repeated prose, never mandatory rows or commands. Re-run to resume." >&2
        echo "If the complete contract requires more space, explicitly raise WORKFLOW_DOC_MAX_BYTES / WORKFLOW_DOC_MAX_LINES before resuming." >&2
        return 1
    fi
}
