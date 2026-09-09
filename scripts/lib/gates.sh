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
# This file's own directory, for helpers shipped beside it. $ROOT is the
# installed uncle root, which is not the same place in a dev checkout.
GATES_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    case "$log_name" in implementation-step-*) is_doc=1 ;; esac
    case "$DOC_STAGES" in
        *" $log_name "*) is_doc=1 ;;
    esac

    local gates rules
    gates=""
    rules=""
    [[ "$is_plan" == "1" ]] && gates="$(gates_file)"
    [[ "$is_doc" == "1" ]] && rules="$(output_rules_file)"

    if [[ "$is_doc" == "0" && -z "$gates" && -z "$rules" ]]; then
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
            document_budget_prompt "$log_name" || return 1
        fi
        if [[ "$role" == "reviewer" ]]; then
            printf '\n\n---\n\n# Reviewer output (binding)\n\nYou run read-only: you cannot write files, so Rule 0 above cannot apply to\nyou. The document the stage asked for is your final assistant message:\nreturn it in full as that message — not a path, not a summary, not a note\nabout a file you could not write.\n'
        fi
    } > "$combined"
    [[ -n "$rules" ]] && echo "Output rules: $(output_rules_source) ($rules)" >&2
    [[ -n "$gates" ]] && echo "Output gates: $(gates_source) ($gates)" >&2
    printf '%s\n' "$combined"
}

# One artifact registry supplies both prompt limits and post-stage enforcement.
# Limits apply to authored documents, never source code or raw execution logs.
stage_documents() {
    case "$1" in
        requirements) echo REQUIREMENTS_INTERPRETATION.md ;;
        project-plan) echo PROJECT_PLAN.md ;;
        updated-plan) echo UPDATED_PROJECT_PLAN.md ;;
        baseline) echo BASELINE_REPORT.md ;;
        change-spec) echo CHANGE_SPEC.md ;;
        change-plan|updated-change-plan) echo CHANGE_PLAN.md ;;
        adversarial-review) echo ADVERSARIAL_REVIEW.md ;;
        preflight) echo PREFLIGHT_REPORT.md ;;
        implementation|implementation-step-*)
            printf '%s\n' IMPLEMENTATION_NOTES.md AUTOMATED_TEST_REPORT.md CHANGE_TEST_REPORT.md ;;
        test-review) echo TEST_REVIEW.md ;;
        manual-checklist|manual-checklist-delta) echo MANUAL_CHECKLIST.md ;;
        manual-checklist-base) echo MANUAL_CHECKLIST.base.md ;;
        execute-checklist) printf '%s\n' VERIFICATION_REPORT.md DEFECTS.md ;;
        final-audit) echo FINAL_AUDIT.md ;;
    esac
}

# basename -> byte floor, ceiling, source multiplier, line floor, ceiling.
# Only authoritative input sets defaults; generated plans never compound budgets.
# One rule for every generated document: twice the brief it came from.
#
# These used to be six different bands, and the per-document ceilings quietly
# won -- a preflight report was capped at 8000 while twice its brief was 10956,
# so the number the agent was given had little to do with the document it was
# asked to write. Worse, the tight ones produced the failure they were meant to
# prevent: an interpretation held to its brief's own length sent the agent into
# rounds of self-trimming until the stage died with the work unsaved.
#
# So the size of the brief is the only input. A run whose REQUIREMENTS.md or
# CHANGE_REQUEST.md is short gets short documents; one that arrives with a long
# GitHub issue gets room to answer it. The floor keeps a one-line brief from
# implying a one-line plan, and the ceiling is a backstop against a brief
# pasted in from something enormous, not a per-document opinion.
DOCUMENT_BUDGET_RULE='4000 40000 2 120 1000'

document_budget_defaults() {
    case "${1##*/}" in
        REQUIREMENTS_INTERPRETATION.md|CHANGE_SPEC.md) echo "$DOCUMENT_BUDGET_RULE" ;;
        PROJECT_PLAN.md|UPDATED_PROJECT_PLAN.md|CHANGE_PLAN.md|UPDATED_CHANGE_PLAN.md)
            echo "$DOCUMENT_BUDGET_RULE" ;;
        BASELINE_REPORT.md|MANUAL_CHECKLIST.md|MANUAL_CHECKLIST.base.md|AUTOMATED_TEST_REPORT.md|CHANGE_TEST_REPORT.md|VERIFICATION_REPORT.md)
            echo "$DOCUMENT_BUDGET_RULE" ;;
        ADVERSARIAL_REVIEW.md|TEST_REVIEW.md|FINAL_AUDIT.md) echo "$DOCUMENT_BUDGET_RULE" ;;
        IMPLEMENTATION_NOTES.md|PREFLIGHT_REPORT.md|DEFECTS.md) echo "$DOCUMENT_BUDGET_RULE" ;;
        *) return 1 ;;
    esac
}

document_budget_source() {
    case "${1##*/}" in
        REQUIREMENTS_INTERPRETATION.md|PROJECT_PLAN.md|UPDATED_PROJECT_PLAN.md)
            echo REQUIREMENTS.md ;;
        CHANGE_SPEC.md|CHANGE_PLAN.md|UPDATED_CHANGE_PLAN.md|BASELINE_REPORT.md|CHANGE_TEST_REPORT.md)
            echo CHANGE_REQUEST.md ;;
        *) echo "${DOCUMENT_BUDGET_SOURCE:-REQUIREMENTS.md}" ;;
    esac
}

# Scope approved increases to this source document, never to another project brief.
document_budget_override_path() {
    local source fingerprint key
    source="$(document_budget_source "$1")"
    fingerprint="$(cksum 2>/dev/null < "$source" | awk '{print $1 "-" $2}')" || fingerprint=missing
    [[ -n "$fingerprint" ]] || fingerprint=missing
    key=$(printf '%s' "${1##*/}" | tr -c 'A-Za-z0-9._-' '_')
    printf '%s/document-budgets/%s-%s\n' "${STATE_DIR:-.uncle/workflow}" "$fingerprint" "$key"
}

# Artifact-specific override wins over the global override, then defaults.
# Bash 3.2 indirect expansion avoids eval of operator-provided values.
document_budget() {
    local file="${1##*/}" defaults max_bytes max_lines source key byte_key line_key
    local floor ceiling multiplier line_floor line_ceiling source_bytes=0
    defaults="$(document_budget_defaults "$file")" || return 1
    read -r floor ceiling multiplier line_floor line_ceiling <<< "$defaults"
    source="$(document_budget_source "$file")"
    if [[ -s "$source" ]]; then
        source_bytes=$(wc -c < "$source")
    fi
    read -r max_bytes max_lines <<< "$(awk -v n="$source_bytes" -v m="$multiplier" \
        -v lo="$floor" -v hi="$ceiling" -v ll="$line_floor" -v lh="$line_ceiling" '
        BEGIN {
            b=n*m; if(b<lo)b=lo; if(b>hi)b=hi;
            l=int((b*ll+lo-1)/lo); if(l>lh)l=lh;
            printf "%.0f %.0f\n", b, l;
        }')"
    key=$(printf '%s' "${file%.md}" | tr '[:lower:].-' '[:upper:]__')
    byte_key="WORKFLOW_DOC_MAX_BYTES_$key"
    line_key="WORKFLOW_DOC_MAX_LINES_$key"
    max_bytes="${!byte_key:-${WORKFLOW_DOC_MAX_BYTES:-$max_bytes}}"
    max_lines="${!line_key:-${WORKFLOW_DOC_MAX_LINES:-$max_lines}}"
    case "$max_bytes$max_lines" in
        *[!0-9]*|"") echo "Document budgets for $file must be positive integers." >&2; return 1 ;;
    esac
    if ! awk -v b="$max_bytes" -v l="$max_lines" 'BEGIN {exit !(b>0 && l>0)}'; then
        echo "Document budgets for $file must be positive integers." >&2; return 1
    fi
    local saved_path saved_bytes saved_lines
    saved_path="$(document_budget_override_path "$file")"
    if [[ -s "$saved_path" ]]; then
        read -r saved_bytes saved_lines < "$saved_path" || return 1
        if ! [[ "$saved_bytes $saved_lines" =~ ^[0-9]+[[:space:]][0-9]+$ ]]; then
            echo "Invalid saved document budget: $saved_path" >&2
            return 1
        fi
        read -r max_bytes max_lines <<< "$(awk -v b="$max_bytes" -v l="$max_lines" -v sb="$saved_bytes" -v sl="$saved_lines" 'BEGIN {printf "%.0f %.0f", (b>sb?b:sb), (l>sl?l:sl)}')"
    fi
    printf '%s %s\n' "$max_bytes" "$max_lines"
}

requirements_document_max_bytes() {
    local limits
    limits="$(document_budget REQUIREMENTS_INTERPRETATION.md)" || return 1
    printf '%s\n' "${limits%% *}"
}

document_budget_prompt() {
    local stage="$1" file limits bytes lines target
    printf '\n\n# Compact output budgets (binding)\n\n'
    while IFS= read -r file; do
        limits="$(document_budget "$file")" || return 1
        read -r bytes lines <<< "$limits"
        target=$(awk -v b="$bytes" 'BEGIN {printf "%.0f", int(b * 0.85)}')
        printf -- '- %s: at most %s UTF-8 bytes and %s lines. Draft toward %s bytes to leave revision room.\n' "$file" "$bytes" "$lines" "$target"
    done < <(stage_documents "$stage")
    cat <<'BUDGET'

These numeric limits supersede any fixed byte target in earlier instructions.
The drafting target is advisory; preserving mandatory content takes precedence.
These are per-file ceilings, not targets. Apply only to files the stage asks
for; this list does not authorize extra outputs. The driver checks new documents
before advancing, including reviewer output, repair reports, and step handoffs.

Reference unchanged upstream requirements and evidence by file plus ID or
section. Do not rebuild their catalogs or repeat background. Write only this
stage's decisions, changes, findings, results, and unresolved prerequisites.
Keep required headings; use a short reference or "None" for settled sections.
Consolidate shared causes, and cross-reference details instead of repeating them.
In revisions and repairs, update current rows in place; do not append narratives
of each attempt. Retain finding IDs, dispositions, and evidence references.

Preserve every required acceptance row, status, assertion, threshold, failure
behavior, exact command, and protected path. Execution plans must retain their
complete executable contract. Reports cite existing raw logs instead of copying
transcripts; never drop checks or evidence needed to assess their results.
Do not create summary sidecars or move obligations out to evade these limits.
If mandatory content alone cannot fit, preserve it: the driver keeps the artifact
and pauses for an explicit budget adjustment. Never truncate required content.
BUDGET
}

# Check newly authored stage artifacts; never rewrite approved inputs.
check_document_budget() {
    local file="$1" bytes lines limits max_bytes max_lines key answer proposed_bytes proposed_lines saved_path temporary
    document_budget_defaults "$file" > /dev/null || return 0
    limits="$(document_budget "$file")" || return 1
    read -r max_bytes max_lines <<< "$limits"
    [[ -s "$file" ]] || { echo "Required document is missing or empty: $file" >&2; return 1; }
    bytes=$(wc -c < "$file")
    lines=$(awk 'END {print NR+0}' "$file")
    if ! awk -v b="$bytes" -v l="$lines" -v mb="$max_bytes" -v ml="$max_lines" 'BEGIN {exit !(b<=mb && l<=ml)}'; then
        key=$(printf '%s' "${file##*/}" | sed 's/\.md$//' | tr '[:lower:].-' '[:upper:]__')
        echo "Document budget exceeded: $file ($bytes bytes, $lines lines; limits $max_bytes bytes, $max_lines lines)." >&2
        echo "Artifact preserved. Shorten repeated prose, never mandatory rows or commands." >&2
        echo "If mandatory content needs more room, set WORKFLOW_DOC_MAX_BYTES_$key / WORKFLOW_DOC_MAX_LINES_$key (or global WORKFLOW_DOC_MAX_BYTES / WORKFLOW_DOC_MAX_LINES)." >&2
        # A probe is asking the size question and nothing else, so it still
        # gets a straight answer.
        [[ "${2:-}" != probe ]] || return 1
        # The budget is a target the agent is given, not a gate the run dies
        # on. Enforcing it cost more documents than it ever shortened: a plan
        # that had already been written was thrown away for being 3KB long, and
        # an interpretation inside its limit was trimmed until the stage failed
        # with the work unsaved. The number still reaches the agent through the
        # prompt, which is where a length target does its work; here it is a
        # remark on the way past. Set WORKFLOW_DOC_BUDGET_ENFORCE=1 to make it
        # blocking again.
        if [[ "${WORKFLOW_DOC_BUDGET_ENFORCE:-0}" != 1 ]]; then
            echo "Continuing: the budget is advisory (WORKFLOW_DOC_BUDGET_ENFORCE=1 makes it blocking)." >&2
            return 0
        fi
        if [[ -t 0 || -n "${UNCLE_STATUS_FILE:-}" || "${WORKFLOW_BUDGET_PROMPT:-0}" == 1 ]]; then
            read -r proposed_bytes proposed_lines <<< "$(awk -v b="$bytes" -v l="$lines" -v mb="$max_bytes" -v ml="$max_lines" 'BEGIN {printf "%.0f %.0f", (b>mb?int((b*1.1+999)/1000)*1000:mb), (l>ml?int((l*1.1+9)/10)*10:ml)}')"
            printf 'Document budget exceeded: %s. Increase limits from %s bytes / %s lines to %s bytes / %s lines and continue with the preserved document? [Y/N]' "$file" "$max_bytes" "$max_lines" "$proposed_bytes" "$proposed_lines" >&2
            if IFS= read -r answer; then
                case "$answer" in
                    y|Y)
                        saved_path="$(document_budget_override_path "$file")"
                        mkdir -p "$(dirname "$saved_path")" || return 1
                        temporary="$(mktemp "${saved_path}.XXXXXX")" || return 1
                        printf '%s %s\n' "$proposed_bytes" "$proposed_lines" > "$temporary"
                        mv "$temporary" "$saved_path" || return 1
                        echo "Document budget increase saved for $file." >&2
                        return 0
                        ;;
                esac
            fi
            echo 'No budget increase authorized; workflow remains pending.' >&2
        fi
        return 1
    fi
}

# Reviewers return documents rather than editing files. Give an oversized result
# one bounded editorial pass, using the same reviewer and its read-only contract.
finish_review_budget() {
    local file="$1" cmd="$2" model="$3" effort="$4" stage="$5"
    local limits bytes lines status=0 started="$SECONDS" log
    local -a flags=(exec --ephemeral --skip-git-repo-check --sandbox read-only)
    limits="$(document_budget "$file")" || return 1
    [[ -s "$file" ]] || { check_document_budget "$file"; return 1; }
    check_document_budget "$file" probe 2>/dev/null && return 0
    if [[ "${WORKFLOW_REVIEW_COMPACT:-1}" == 0 ]]; then
        check_document_budget "$file"
        return $?
    fi
    read -r bytes lines <<< "$limits"
    [[ -z "$model" ]] || flags+=(-m "$model")
    [[ -z "$effort" ]] || flags+=(-c "model_reasoning_effort=$effort")
    log="$LOG_DIR/${stage}.compact.log"
    python3 "$ROOT/scripts/lib/compact-review.py" --output "$file" --log "$log" \
        --max-bytes "$bytes" --max-lines "$lines" \
        --seconds "${WORKFLOW_REVIEW_COMPACT_SECONDS:-120}" \
        -- "$cmd" "${flags[@]}" || status=$?
    if declare -F perf_record > /dev/null; then
        perf_record reviewer "${stage}-compact" "$((SECONDS-started))" "$status" \
            "$log" "$cmd" "$model" "$effort"
    fi
    check_document_budget "$file"
    # The size verdict is advisory; the compaction result is not. This used to
    # return the size check alone, so a candidate rejected for dropping a
    # finding id or flipping a status was reported as a failure only because
    # the document it refused to replace happened to still be too long. With
    # length no longer fatal that coincidence disappears, and the rejection has
    # to speak for itself.
    return "$status"
}

# Cache only plan reviews; later execution/audit stages still gather fresh evidence.
review_input_key() {
    local output="$1" prompt="$2" cmd="$3" model="$4" effort="$5" stage="$6"
    [[ "$stage" == adversarial-review && "${WORKFLOW_REVIEW_CACHE:-1}" != 0 ]] || return 0
    python3 "$ROOT/scripts/lib/review-cache.py" key --output "$output" \
        --prompt "$prompt" --runner "$cmd" --model "$model" --effort "$effort" || true
}

restore_plan_review() {
    [[ -n "$2" ]] || return 1
    python3 "$ROOT/scripts/lib/review-cache.py" restore --output "$1" --key "$2" \
        --cache-dir "$LOG_DIR/../review-cache" || return 1
    echo "Reusing completed plan review: local inputs and reviewer settings are unchanged."
}

save_plan_review() {
    [[ -n "$2" ]] || return 0
    python3 "$ROOT/scripts/lib/review-cache.py" save --output "$1" --key "$2" \
        --cache-dir "$LOG_DIR/../review-cache"
}

# What this machine was proved able to do, published for the stages that write
# checks against it.
#
# PREFLIGHT_REPORT.md already records one row per prerequisite, with evidence.
# The driver used to read it as a single verdict and throw the rows away -- so
# the stage that writes the checklist had no list of proven capabilities to
# check its rows against, and could author a check nothing in this environment
# can perform. That is how a required row demanding a real 320px browser
# window gets written on a machine whose browser will not go below 500.
#
# Publishing the rows does not make the checklist obey them. The checklist
# prompt does that, by requiring each row that needs a capability to cite the
# id that proved it.
snapshot_preflight_capabilities() {
    local directory="$STATE_DIR/preflight-capabilities"
    local report="${1:-PREFLIGHT_REPORT.md}"
    mkdir -p "$directory"
    rm -f "$directory/capabilities.tsv"
    if [[ -s "$report" ]]; then
        awk -F '|' '
            function trim(s) { sub(/^[ \t\r]+/, "", s); sub(/[ \t\r]+$/, "", s); return s }
            /^## Acceptance gate[ \t\r]*$/ { active=1; next }
            active && NF == 6 {
                id=trim($2); required=trim($3); status=trim($4); evidence=trim($5)
                if (id == "ID" || id ~ /^:?-{3,}:?$/) next
                if (id == "") next
                printf "%s\t%s\t%s\t%s\n", id, required, status, evidence
            }
        ' "$report" > "$directory/capabilities.tsv"
    fi
    {
        echo '# Capabilities proved before implementation'
        echo
        if [[ ! -s "$directory/capabilities.tsv" ]]; then
            echo "NOT DECLARED: $report has no acceptance-gate rows."
            echo 'Nothing was proved about this environment, so a check that needs a'
            echo 'capability has no evidence behind it. Do not assume one is available.'
        else
            printf 'From %s, one row per prerequisite:\n\n' "$report"
            echo '```'
            awk -F '\t' '{ printf "%-16s %-4s %-20s %s\n", $1, $2, $3, $4 }' \
                "$directory/capabilities.tsv"
            echo '```'
            echo
            echo 'PASS means it was exercised here and the output was recorded. Any'
            echo 'other status means it was not: a check that needs it cannot pass,'
            echo 'and writing one as though it could is how a run ends on a check'
            echo 'nobody can perform.'
            echo
            echo 'Cite the id in any check that needs the capability. If its status'
            echo 'is not PASS, give the check the matching status:'
            echo '  BLOCKED-SETUP       one action would make it available'
            echo '  BLOCKED-HUMAN       it waits on a person'
            echo '  BLOCKED-IMPOSSIBLE  this environment cannot do it at all'
        fi
    } > "$directory/README.md"
    if [[ -s "$directory/capabilities.tsv" ]]; then
        echo "Preflight capabilities: $(wc -l < "$directory/capabilities.tsv" | tr -d ' ') prerequisite row(s) published for the checklist."
    fi
}

# The checklist's own parallel-execution plan, derived from the reviewer's
# per-check declarations immediately before the stage that follows them.
#
# The executing agent is told to overlap independent checks. Deciding which
# checks are independent is a judgment about ports, fixtures, and shared
# accounts, and it belongs to the reviewer who wrote the checks -- not to the
# agent whose results change depending on the answer. This turns those
# declarations into an ordered plan the agent follows.
#
# Never fatal. A checklist with no declarations, or with declarations that do
# not parse, produces a README saying NOT DECLARED and no groups file, and the
# stage runs one check at a time exactly as it did before this existed.
snapshot_checklist_groups() {
    local directory="$STATE_DIR/checklist-groups"
    mkdir -p "$directory"
    rm -f "$directory/groups.txt"
    if ! command -v python3 > /dev/null 2>&1 \
        || [[ ! -f "$GATES_LIB_DIR/checklist_groups.py" ]]; then
        {
            echo '# Parallel execution groups for checklist execution'
            echo
            echo 'NOT DECLARED: python3 is unavailable, so no grouping was derived.'
            echo 'Run the checklist one check at a time, in document order.'
        } > "$directory/README.md"
        return 0
    fi
    python3 -B "$GATES_LIB_DIR/checklist_groups.py" \
        --checklist MANUAL_CHECKLIST.md --out-dir "$directory" > /dev/null || true
    if [[ -s "$directory/groups.txt" ]]; then
        echo "Checklist grouping: $(wc -l < "$directory/groups.txt" | tr -d ' ') group(s) from the reviewer's declarations."
    else
        echo "Checklist grouping: none declared; the checklist runs one check at a time."
    fi
}

# Snapshot only checks executed immediately before checklist verification.
# Disabled/missing commands must never expose earlier successful logs as fresh.
snapshot_checklist_checks() {
    local directory="$STATE_DIR/checklist-driver-checks"
    mkdir -p "$directory"
    rm -f "$directory/output.log" "$directory/results.tsv"
    {
        echo '# Driver checks for checklist execution'
        printf '\nRecorded: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        if [[ "${GREEN_CHECK:-0}" == 1 && -s "$GREEN_CMDS" && -f "$GREEN_CUR" ]]; then
            cp "$GREEN_CUR" "$directory/results.tsv"
            cp "$LOG_DIR/green-check.log" "$directory/output.log"
            echo
            echo 'The driver executed the approved commands immediately before this stage.'
            echo 'Use results.tsv for command exit codes and output.log for assertion evidence.'
            echo 'A nonzero exit is a failure, not a sandbox blocker or a pass.'
        else
            echo
            echo 'NOT RUN: driver verification is disabled or no approved commands are available.'
        fi
        echo 'This evidence covers only the commands and assertions actually executed.'
        echo 'It does not establish manual browser checks or human acceptance.'
    } > "$directory/README.md"
}
