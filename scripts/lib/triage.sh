#!/usr/bin/env bash
# Build the failure bundle a triage master reads: .uncle/workflow/TRIAGE.md.
#
# Generated from the tree, never agent-written, and bounded, so the operator
# can hand it to a model without assembling the same context by hand after
# every stage failure. The drivers call triage_on_exit from their EXIT trap;
# the TUI calls `bash scripts/lib/triage.sh --write` to rebuild it on request.
#
# bash 3.2 compatible: no associative arrays, no ${var^^}.

if ! declare -f state_read > /dev/null 2>&1; then
    . "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/state.sh"
fi

TRIAGE_LOG_TAIL="${TRIAGE_LOG_TAIL:-200}"
TRIAGE_FILE_CAP="${TRIAGE_FILE_CAP:-16384}"
TRIAGE_ROW_CAP="${TRIAGE_ROW_CAP:-60}"
TRIAGE_TOTAL_CAP="${TRIAGE_TOTAL_CAP:-98304}"
TRIAGE_ID_PREFIXES='AC|B|I|R|S|D|MC|AR|X|INV'
TRIAGE_PLAN_FILES='CHANGE_PLAN.md UPDATED_PROJECT_PLAN.md CHANGE_SPEC.md PROJECT_PLAN.md'

# triage_stop_reason <state_dir> <reason> -- record why the driver is about to
# stop. `human` means a person chose to stop, which is not a failure and must
# not open triage on its own.
triage_stop_reason() {
    mkdir -p "$1" 2>/dev/null || return 0
    printf '%s\n' "$2" > "$1/stop-reason" 2>/dev/null || true
}

# triage_failing_stage <state_dir> -- the stage log name that was running:
# the driver exports UNCLE_STATUS_STAGE when a stage starts, and the newest
# log is the fallback for a failure the drivers did not attribute.
triage_failing_stage() {
    local state_dir="$1" newest
    if [[ -n "${UNCLE_STATUS_STAGE:-}" ]]; then
        printf '%s' "$UNCLE_STATUS_STAGE"
        return 0
    fi
    [[ -d "$state_dir/logs" ]] || return 0
    # Agent stages write <stage>.jsonl; reviewer stages write <stage>.log. Only
    # looking at .jsonl made every reviewer failure look like it had no log at
    # all, so triage reported the stage log MISSING and had no trace to cite.
    newest="$(ls -t "$state_dir/logs"/*.jsonl "$state_dir/logs"/*.log 2>/dev/null | head -n 1)"
    [[ -n "$newest" ]] || return 0
    newest="${newest##*/}"
    newest="${newest%.jsonl}"
    printf '%s' "${newest%.log}"
}

# The log a stage actually wrote, whichever side it ran on.
triage_stage_log() {
    local state_dir="$1" stage="$2" candidate
    for candidate in "$state_dir/logs/$stage.jsonl" "$state_dir/logs/$stage.log"; do
        if [[ -s "$candidate" ]]; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    # Neither exists: name the one the stage would have written, so the bundle
    # reports a real path rather than inventing an extension.
    printf '%s' "$state_dir/logs/$stage.jsonl"
}

# triage_stage_reports <stage> -- the reports the failing stage writes or
# reads, one per line. A static table: the alternative is a hook at every
# exit site, and there are more than ninety of those.
triage_stage_reports() {
    case "$1" in
        derive-brief) printf '%s\n' CHANGE_REQUEST.md REQUIREMENTS.md ;;
        requirements) printf '%s\n' REQUIREMENTS_INTERPRETATION.md ;;
        baseline) printf '%s\n' BASELINE_REPORT.md ;;
        project-plan) printf '%s\n' PROJECT_PLAN.md ;;
        change-plan|change-spec) printf '%s\n' CHANGE_SPEC.md CHANGE_PLAN.md ;;
        adversarial-review|plan-executability) printf '%s\n' ADVERSARIAL_REVIEW.md ;;
        updated-plan|plan-recovery) printf '%s\n' UPDATED_PROJECT_PLAN.md ;;
        updated-change-plan) printf '%s\n' CHANGE_PLAN.md ;;
        preflight) printf '%s\n' PREFLIGHT_REPORT.md ;;
        implementation*) printf '%s\n' IMPLEMENTATION_NOTES.md AUTOMATED_TEST_REPORT.md CHANGE_TEST_REPORT.md ;;
        repair*) printf '%s\n' IMPLEMENTATION_NOTES.md ;;
        test-review) printf '%s\n' TEST_REVIEW.md ;;
        manual-checklist*) printf '%s\n' MANUAL_CHECKLIST.md ;;
        execute-checklist) printf '%s\n' VERIFICATION_REPORT.md DEFECTS.md ;;
        final-audit) printf '%s\n' FINAL_AUDIT.md ;;
        *) ;;
    esac
}

# triage_embed_file <path> [label] -- one section: the file, or MISSING.
# Files over the cap are cut and say so; a bundle is not a copy of the tree.
triage_embed_file() {
    local path="$1" label="${2:-$1}" size
    echo
    echo "## $label"
    echo
    if [[ ! -s "$path" ]]; then
        echo "MISSING: $path"
        return 0
    fi
    size="$(wc -c < "$path" | tr -d ' ')"
    echo '```text'
    if [[ "$size" -gt "$TRIAGE_FILE_CAP" ]]; then
        head -c "$TRIAGE_FILE_CAP" "$path"
        echo
        echo "[TRUNCATED: $path is $size bytes; first $TRIAGE_FILE_CAP shown]"
    else
        cat "$path"
        [[ "$(tail -c 1 "$path" | wc -l | tr -d ' ')" == 1 ]] || echo
    fi
    echo '```'
}

# triage_embed_tail <path> <label> -- the last TRIAGE_LOG_TAIL lines, read
# with tail so a 10 MiB log costs what its tail costs.
triage_embed_tail() {
    local path="$1" label="$2" lines
    echo
    echo "## $label"
    echo
    if [[ ! -s "$path" ]]; then
        echo "MISSING: $path"
        return 0
    fi
    lines="$(wc -l < "$path" | tr -d ' ')"
    echo '```text'
    if [[ "$lines" -gt "$TRIAGE_LOG_TAIL" ]]; then
        echo "[TRUNCATED: $path has $lines lines; last $TRIAGE_LOG_TAIL shown]"
    fi
    tail -n "$TRIAGE_LOG_TAIL" "$path" | cut -c 1-2000
    echo '```'
}

# triage_cited_ids <file...> -- every <PREFIX>-<n> identifier the given
# files mention, one per line, sorted, prefixes limited to the plan tables.
# Two passes: pull whole tokens first, then keep the exact ids, so "SAC-1"
# and "AC-12x" are not read as citations.
triage_cited_ids() {
    local f
    for f in "$@"; do
        [[ -s "$f" ]] || continue
        grep -oE "[A-Za-z0-9_]*($TRIAGE_ID_PREFIXES)-[0-9]+[A-Za-z0-9_]*" "$f" 2>/dev/null || true
    done | grep -E "^($TRIAGE_ID_PREFIXES)-[0-9]+$" | sort -u
}

# triage_cited_rows <report...> -- the plan/spec table rows whose first cell
# is an id cited by the reports, capped at TRIAGE_ROW_CAP.
triage_cited_rows() {
    local ids id plan count=0 row
    ids="$(triage_cited_ids "$@")"
    echo
    echo "## Cited plan rows"
    echo
    if [[ -z "$ids" ]]; then
        echo "MISSING: no plan ids cited by the failing reports"
        return 0
    fi
    for plan in $TRIAGE_PLAN_FILES; do
        [[ -s "$plan" ]] || continue
        while IFS= read -r id; do
            [[ -n "$id" ]] || continue
            while IFS= read -r row; do
                [[ -n "$row" ]] || continue
                if [[ "$count" -ge "$TRIAGE_ROW_CAP" ]]; then
                    echo
                    echo "[TRUNCATED: more than $TRIAGE_ROW_CAP cited rows]"
                    return 0
                fi
                printf '%s: %s\n' "$plan" "$row"
                count=$((count + 1))
            done < <(grep -E "^\| *\`?$id\`? *\|" "$plan" 2>/dev/null || true)
        done <<< "$ids"
    done
    [[ "$count" -gt 0 ]] || echo "MISSING: cited ids ($(printf '%s' "$ids" | tr '\n' ' ')) match no row in $TRIAGE_PLAN_FILES"
}

# write_triage <state_dir> <out> -- rebuild the bundle from the tree.
write_triage() {
    local state_dir="$1" out="$2" stage reports report tmp size
    local -a report_files=()
    stage="$(triage_failing_stage "$state_dir")"
    tmp="$(mktemp "${TMPDIR:-/tmp}/triage.XXXXXX")" || return 1
    reports="$(triage_stage_reports "$stage")"
    while IFS= read -r report; do
        [[ -n "$report" ]] || continue
        report_files+=("$report")
    done <<< "$reports"
    if [[ -s "$state_dir/repair-source" ]]; then
        report="$(head -n 1 "$state_dir/repair-source")"
        [[ -z "$report" ]] || report_files+=("$report")
    fi
    {
        echo "# Triage bundle"
        echo
        echo "Generated by uncle from the working tree. Do not edit."
        echo
        echo "## Run"
        echo
        echo "- state: $(state_read "$state_dir/state" MISSING)"
        echo "- exit status: ${TRIAGE_EXIT_STATUS:-MISSING}"
        echo "- failing stage: ${stage:-MISSING}"
        echo "- stop reason: $(cat "$state_dir/stop-reason" 2>/dev/null || printf MISSING)"
        echo "- repair-count: $(cat "$state_dir/repair-count" 2>/dev/null || printf MISSING)"
        echo "- repair-source: $(cat "$state_dir/repair-source" 2>/dev/null || printf MISSING)"
        echo "- generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        if [[ -s "$state_dir/validation-error.txt" ]]; then
            triage_embed_tail "$state_dir/validation-error.txt" "Driver validation error"
        fi
        if [[ -n "$stage" ]]; then
            triage_embed_tail "$(triage_stage_log "$state_dir" "$stage")" "Stage log tail: $stage"
        else
            echo
            echo "## Stage log tail"
            echo
            echo "MISSING: no stage log under $state_dir/logs"
        fi
        echo
        echo "## Failing stage reports"
        if [[ "${#report_files[@]}" -eq 0 ]]; then
            echo
            echo "MISSING: no report is mapped to stage '${stage:-unknown}'"
        else
            for report in "${report_files[@]}"; do
                triage_embed_file "$report"
            done
        fi
        case " ${report_files[*]-} " in
            *" IMPLEMENTATION_NOTES.md "*) ;;
            *) triage_embed_file IMPLEMENTATION_NOTES.md ;;
        esac
        triage_embed_file "$state_dir/green-check.md" "green-check.md"
        if [[ "${#report_files[@]}" -gt 0 ]]; then
            triage_cited_rows "${report_files[@]}"
        else
            triage_cited_rows /dev/null
        fi
    } > "$tmp" || { rm -f "$tmp"; return 1; }
    size="$(wc -c < "$tmp" | tr -d ' ')"
    if [[ "$size" -gt "$TRIAGE_TOTAL_CAP" ]]; then
        local marker
        marker="[TRUNCATED: bundle was $size bytes; cap $TRIAGE_TOTAL_CAP]"
        head -c "$((TRIAGE_TOTAL_CAP - ${#marker} - 2))" "$tmp" > "$tmp.cut" || { rm -f "$tmp" "$tmp.cut"; return 1; }
        printf '\n%s\n' "$marker" >> "$tmp.cut"
        mv "$tmp.cut" "$tmp"
    fi
    mkdir -p "$(dirname "$out")" && mv "$tmp" "$out" || { rm -f "$tmp"; return 1; }
}

# triage_on_exit <rc> -- the driver's EXIT hook. A gate decline (0), a
# cancel (130/143), a kill (137), or a stop a person chose is not a failure
# and writes nothing. Anything else gets a bundle. The exit status is never
# changed here: a bundle that could not be written is one stderr line.
triage_on_exit() {
    local rc="${1:-0}" state_dir="${STATE_DIR:-.uncle/workflow}"
    case "$rc" in 0|130|143|137) return 0 ;; esac
    if [[ -s "$state_dir/stop-reason" ]] && [[ "$(head -n 1 "$state_dir/stop-reason")" == human ]]; then
        return 0
    fi
    [[ -d "$state_dir" ]] || return 0
    if ! TRIAGE_EXIT_STATUS="$rc" write_triage "$state_dir" "$state_dir/TRIAGE.md" 2>/dev/null; then
        echo "triage: could not write $state_dir/TRIAGE.md" >&2
    fi
    return 0
}

# triage_print_actions <state_dir> -- the action ledger, printed at COMPLETE
# beside waivers and overrides. Every row, including NO_EDIT and FAILED: an
# action the operator selected is part of the record whether or not it wrote.
triage_print_actions() {
    local tsv="$1/triage-actions.tsv"
    [[ -s "$tsv" ]] || return 0
    echo
    echo "Triage actions ($tsv):"
    sed 's/^/  /' "$tsv"
}

# CLI: bash scripts/lib/triage.sh --write [--state-dir DIR] [--out FILE]
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    set -euo pipefail
    mode="" state_dir=".uncle/workflow" out=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --write) mode=write; shift ;;
            --state-dir) [[ $# -ge 2 ]] || exit 2; state_dir="$2"; shift 2 ;;
            --out) [[ $# -ge 2 ]] || exit 2; out="$2"; shift 2 ;;
            *) echo "usage: triage.sh --write [--state-dir DIR] [--out FILE]" >&2; exit 2 ;;
        esac
    done
    [[ "$mode" == write ]] || { echo "usage: triage.sh --write [--state-dir DIR] [--out FILE]" >&2; exit 2; }
    write_triage "$state_dir" "${out:-$state_dir/TRIAGE.md}"
    printf '%s\n' "${out:-$state_dir/TRIAGE.md}"
fi
