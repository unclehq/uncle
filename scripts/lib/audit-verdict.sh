# Pure classifier for either the canonical final-audit JSON or its Markdown
# presentation.  Drivers pass JSON; Markdown support is a legacy UI helper.
#
# Sourcing this file defines functions and nothing else, so both
# change-workflow.sh and scripts/tests/audit-verdict-test.sh can use it. Not
# executable on its own.
#
# classify_audit_verdict <file> prints exactly one of:
#   READY | READY_WITH_NON_BLOCKING_ISSUES | NOT_READY | UNKNOWN
#
# It fails closed. Only the last non-blank line of the file is considered, and
# that line must match one of the three verdict phrases from
# prompts/change/final-audit.md exactly, case-sensitively, once surrounding
# whitespace and markdown emphasis or heading markers are stripped. Trailing
# prose, a phrase embedded in a sentence, or two phrases on one line all
# classify as UNKNOWN.

classify_audit_verdict() {
    local file="${1:-}"

    if [[ -z "$file" || ! -s "$file" ]]; then
        printf '%s\n' UNKNOWN
        return 0
    fi

    if [[ "$file" == *.json ]]; then
        local verdict
        verdict="$(python3 - "$file" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1])).get('verdict', ''))
except Exception:
    pass
PY
)"
        case "$verdict" in
            "READY") printf '%s\n' READY ;;
            "READY WITH NON-BLOCKING ISSUES") printf '%s\n' READY_WITH_NON_BLOCKING_ISSUES ;;
            "NOT READY") printf '%s\n' NOT_READY ;;
            *) printf '%s\n' UNKNOWN ;;
        esac
        return 0
    fi

    local line
    line="$(tr -d '\r' < "$file" | awk 'NF { last = $0 } END { print last }')"
    line="$(printf '%s' "$line" \
        | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
              -e 's/^[#*_[:space:]]*//' -e 's/[*_[:space:]]*$//' \
              -e 's/^Conclusion:[[:space:]]*//' \
              -e 's/^[*_[:space:]]*//' -e 's/[*_[:space:]]*$//')"

    case "$line" in
        "READY")                          printf '%s\n' READY ;;
        "READY WITH NON-BLOCKING ISSUES") printf '%s\n' READY_WITH_NON_BLOCKING_ISSUES ;;
        "NOT READY")                      printf '%s\n' NOT_READY ;;
        *)                                printf '%s\n' UNKNOWN ;;
    esac
}

# verdict_file_field <file> <audit_class|hash> -- version-tolerant VERDICT_FILE
# reader shared by both drivers. Before this, each driver hardcoded its own
# column position (stagegate.sh: 2 columns [audit_class, hash]; change-
# workflow.sh: 3 columns [run_id, audit_class, hash], added later for its own
# bookkeeping). Standardizing on 3 columns (stagegate.sh now writes "-" for
# run_id) would otherwise misparse a VERDICT_FILE an in-flight app-family run
# wrote in the old 2-column format before this change landed -- this counts
# the actual tab-separated fields on the line and picks the right column for
# whichever format is really on disk, rather than assuming the file was
# written by the current code.
verdict_file_field() {
    local file="$1" field="$2" line fields
    line="$(awk -F'\t' 'NR == 1 { print; exit }' "$file" 2>/dev/null)"
    fields="$(awk -F'\t' '{ print NF }' <<< "$line")"
    case "$fields" in
        3)
            case "$field" in
                audit_class) awk -F'\t' '{ print $2 }' <<< "$line" ;;
                hash)        awk -F'\t' '{ print $3 }' <<< "$line" ;;
            esac
            ;;
        *)
            # 2 columns (the historical app-family format), or anything else
            # unexpected: fall back to the original 2-column positions rather
            # than guessing further.
            case "$field" in
                audit_class) awk -F'\t' '{ print $1 }' <<< "$line" ;;
                hash)        awk -F'\t' '{ print $2 }' <<< "$line" ;;
            esac
            ;;
    esac
}

# final_audit_validate <check_fn> <run_id> -- the shared VALIDATE_AUDIT body:
# ingest a legacy Markdown .../FINAL_AUDIT.md into canonical JSON with one
# format-only retry, validate it, fail closed against the driver's own green
# check, downgrade a plain READY that hides a waived failure, and write
# VERDICT_FILE. Leaves the computed class in $FINAL_AUDIT_CLASS for the
# caller.
#
# <check_fn> is the name of whichever require_artifact/require_file-shaped
# function the caller wants to call against .uncle/docs/FINAL_AUDIT.md
# (stagegate.sh uses require_artifact's tool-denial-oriented message;
# change-workflow.sh uses its own require_file) -- both resolve to the same
# canonical $STATE_DIR/documents/FINAL_AUDIT.json path via
# canonical_artifact_path, so this is cosmetic, not behavioral, and stays a
# parameter rather than picking one for both.
#
# <run_id> is the literal first column VERDICT_FILE is written with ("-" for
# stagegate.sh, change-workflow.sh's own $STAGEGATE_RUN_ID).
#
# Needs from the caller: ROOT, STATE_DIR, VERDICT_FILE, GREEN_CHECK, GREEN_CMDS,
# GREEN_CLASS, GREEN_MD, green_regressions, set_state, hash_file.
#
# Returns 0 when a verdict was computed (caller should call
# final_audit_route_verdict next); returns 2 when a malformed audit's one-shot
# retry was spent and FINAL_AUDIT was reopened (this function already called
# set_state FINAL_AUDIT -- the caller's case arm need only `continue`).
final_audit_validate() {
    local check_fn="$1" run_id="$2"
    local final_audit_ingest_error final_audit_validation_error

    if [[ -s .uncle/docs/FINAL_AUDIT.md ]] \
            && ! python3 -B "$ROOT/scripts/lib/final-audit-context.py" --validate-json . >/dev/null 2>&1; then
        final_audit_ingest_error="$(python3 -B "$ROOT/scripts/lib/final-audit-context.py" --validate .uncle/docs/FINAL_AUDIT.md 2>&1)" || {
            if [[ ! -s "$STATE_DIR/final-audit-format-retry.md" ]]; then
                printf '%s\n' "$final_audit_ingest_error" > "$STATE_DIR/final-audit-format-retry.md"
                echo "Retrying final-audit once with the format diagnostic."
                set_state FINAL_AUDIT
                return 2
            fi
            echo 'Final audit was malformed; recording a blocking driver-owned audit without retrying the reviewer.'
            python3 -B "$ROOT/scripts/lib/final-audit-context.py" --fallback .uncle/docs/FINAL_AUDIT.md "$final_audit_ingest_error"
        }
    fi
    "$check_fn" .uncle/docs/FINAL_AUDIT.md

    final_audit_validation_error="$(python3 -B "$ROOT/scripts/lib/final-audit-context.py" --validate-json . 2>&1)" || {
        echo 'Final audit was malformed; recording a blocking driver-owned audit without retrying the reviewer.'
        python3 -B "$ROOT/scripts/lib/final-audit-context.py" --fallback .uncle/docs/FINAL_AUDIT.md "$final_audit_validation_error"
    }
    FINAL_AUDIT_CLASS="$(classify_audit_verdict "$STATE_DIR/documents/FINAL_AUDIT.json")"

    if [[ "$FINAL_AUDIT_CLASS" == READY || "$FINAL_AUDIT_CLASS" == READY_WITH_NON_BLOCKING_ISSUES ]] \
            && [[ "$GREEN_CHECK" == "1" && -s "$GREEN_CMDS" ]]; then
        if [[ ! -s "$GREEN_CLASS" ]]; then
            echo "No driver verification result on record ($GREEN_CLASS is missing or empty) despite WORKFLOW_GREEN_CHECK=1."
            echo "Overriding the verdict to NOT_READY; it cannot be silently approved without that evidence."
            FINAL_AUDIT_CLASS=NOT_READY
        elif [[ "$(green_regressions "$GREEN_CLASS")" -gt 0 ]]; then
            echo "Audit verdict $FINAL_AUDIT_CLASS contradicts the driver's own verification: $(green_regressions "$GREEN_CLASS") command(s) regressed."
            echo "$GREEN_MD lists them. Overriding the verdict to NOT_READY; it cannot be silently approved."
            FINAL_AUDIT_CLASS=NOT_READY
        fi
    fi
    if [[ "$FINAL_AUDIT_CLASS" == READY && -s "$STATE_DIR/nonblocking-test-failures.tsv" ]]; then
        echo "Audit verdict READY, but $STATE_DIR/nonblocking-test-failures.tsv records at least one deliberately-waived failure."
        echo "Downgrading the verdict to READY_WITH_NON_BLOCKING_ISSUES; it is not reported as a clean pass."
        FINAL_AUDIT_CLASS=READY_WITH_NON_BLOCKING_ISSUES
    fi
    printf '%s\t%s\t%s\n' "$run_id" "$FINAL_AUDIT_CLASS" "$(hash_file "$STATE_DIR/documents/FINAL_AUDIT.json")" \
        > "$VERDICT_FILE"
    return 0
}

# final_audit_route_verdict <audit_class> -- the shared post-verdict routing,
# identical in both drivers: READY/READY_WITH_NON_BLOCKING_ISSUES completes
# the run; anything else goes to WAIT_AUDIT_OVERRIDE unless AUDIT_GATE=0.
# Needs from the caller: AUDIT_GATE, set_state.
final_audit_route_verdict() {
    local audit_class="$1"
    echo "Audit verdict: $audit_class"
    case "$audit_class" in
        READY|READY_WITH_NON_BLOCKING_ISSUES)
            set_state COMPLETE
            ;;
        *)
            if [[ "$AUDIT_GATE" == "1" ]]; then
                set_state WAIT_AUDIT_OVERRIDE
            else
                echo "Audit gate disabled (WORKFLOW_AUDIT_GATE=0);" \
                     "completing on a $audit_class verdict."
                set_state COMPLETE
            fi
            ;;
    esac
}

# final_audit_override_gate <audit_class> <gate_fn> <rerun_hint> <kind> --
# the shared tail of WAIT_AUDIT_OVERRIDE's non-READY, non-recoverable-NOT_READY
# branch: print the verdict banner and the two ways forward, then record an
# override through whichever human-approval gate function the caller uses.
#
# <gate_fn> is "review_and_approve" (stagegate.sh) or "human_gate"
# (change-workflow.sh) -- confirmed not interchangeable (different arity,
# different approval metadata change-workflow.sh's envelope system reads), so
# this stays a parameter rather than a shared implementation; each driver's
# own gate function keeps doing exactly what it always did.
#
# <rerun_hint> is the exact re-run command block each driver prints (its own
# script name), printed verbatim.
#
# <kind> is "build" (stagegate.sh) or "change" (change-workflow.sh) -- the one
# noun that differs in "The independent auditor says this ... is not ready."
# and in whether the override note mentions "never closes the originating
# issue" (change-workflow.sh only, since only it has an issue to close).
#
# Needs from the caller: AUDIT_OVERRIDE_FILE, hash_file; <gate_fn> itself
# must already be in scope.
final_audit_override_gate() {
    local audit_class="$1" gate_fn="$2" rerun_hint="$3" kind="${4:-build}"
    echo
    echo "=================================================="
    echo "FINAL AUDIT: $audit_class"
    echo "=================================================="
    echo

    if [[ "$audit_class" == "NOT_READY" ]]; then
        echo "The independent auditor says this $kind is not ready."
    else
        echo ".uncle/docs/FINAL_AUDIT.md does not end in one of the three verdict"
        echo "phrases, so the auditor's conclusion could not be read."
        echo "An unreadable verdict is not a pass."
    fi

    echo
    echo "This run does not finish on that by itself. Either fix what"
    echo "the audit found and re-run the implementation stage:"
    echo
    printf '%s\n' "$rerun_hint"
    echo
    if [[ "$kind" == change ]]; then
        echo "or record an explicit decision to finish anyway. An override"
        echo "is written to $AUDIT_OVERRIDE_FILE, reported at COMPLETE, and"
        echo "never closes the originating issue."
    else
        echo "or record an explicit decision to finish anyway. An override"
        echo "is written to $AUDIT_OVERRIDE_FILE and reported at COMPLETE."
    fi

    if [[ "$gate_fn" == human_gate ]]; then
        human_gate OVERRIDE .uncle/docs/FINAL_AUDIT.md FINAL_AUDIT_OVERRIDE
    else
        "$gate_fn" .uncle/docs/FINAL_AUDIT.md FINAL_AUDIT_OVERRIDE override
    fi

    printf '%s\t%s\t%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "$audit_class" \
        "$(hash_file .uncle/docs/FINAL_AUDIT.md)" \
        > "$AUDIT_OVERRIDE_FILE"

    set_state COMPLETE
}

# final_audit_override_recovery <audit_class> <run_id> <enable_unattended_repair_route> --
# the shared head of WAIT_AUDIT_OVERRIDE: recover a READY verdict saved just
# before an interruption, or walk a NOT_READY verdict through the unattended
# waiver ledger (audit-findings.py), writing it back as a recovered READY.
# Hard failures (the verdict changed since it was recorded) still `exit 1`
# directly, matching both drivers' original behavior.
#
# <run_id> is VERDICT_FILE's first column, same convention as
# final_audit_validate.
#
# <enable_unattended_repair_route> ("1" or "0") preserves a real, existing
# difference rather than silently adding or removing it: stagegate.sh routes
# an unattended NOT_READY with a driver-observed verification failure back to
# REPAIR once (bounded by WORKFLOW_AUTO_REPAIR_ATTEMPTS) before any unreviewed
# waiver; change-workflow.sh's original had no such route at all. This may be
# worth closing as a real gap, but that is a separate decision -- not
# something this extraction should decide by picking one behavior for both.
#
# Returns 0 when it fully handled the verdict (COMPLETE or REPAIR was already
# set; caller should `continue`), or 1 when the caller should fall through to
# final_audit_override_gate (a NOT_READY not routed to repair, or an
# unreadable verdict).
final_audit_override_recovery() {
    local audit_class="$1" run_id="$2" enable_unattended_repair_route="$3"
    local audit_hash

    if [[ "$audit_class" == READY ]]; then
        [[ "$(verdict_file_field "$VERDICT_FILE" hash)" == "$(hash_file "$STATE_DIR/documents/FINAL_AUDIT.json")" ]] || exit 1
        python3 "$ROOT/scripts/lib/audit-findings.py" "$STATE_DIR/documents/FINAL_AUDIT.json" "$STATE_DIR" --check $([[ "${UNATTENDED:-0}" == 1 ]] && printf %s --unattended) || exit 1
        set_state COMPLETE
        return 0
    fi

    if [[ "$audit_class" == NOT_READY ]]; then
        audit_hash="$(hash_file "$STATE_DIR/documents/FINAL_AUDIT.json")"
        if [[ "$(classify_audit_verdict "$STATE_DIR/documents/FINAL_AUDIT.json")" != NOT_READY ]] \
            || [[ "$(verdict_file_field "$VERDICT_FILE" hash)" != "$audit_hash" ]]; then
            echo "The audit changed since its verdict was recorded; rerun FINAL_AUDIT."
            exit 1
        fi
        if [[ "$enable_unattended_repair_route" == 1 ]] \
                && [[ "${UNATTENDED:-0}" == 1 ]] && [[ "${WORKFLOW_AUTO_REPAIR:-1}" == 1 ]] \
                && [[ "$(cat "$STATE_DIR/repair-count" 2>/dev/null || printf 0)" -lt "${WORKFLOW_AUTO_REPAIR_ATTEMPTS:-2}" ]] \
                && [[ "${GREEN_CHECK:-1}" == 1 && -s "${GREEN_CLASS:-}" ]] \
                && [[ "$(green_regressions "$GREEN_CLASS")" -gt 0 ]]; then
            echo 'Unattended final audit is NOT READY with a driver-observed verification failure; repairing once before any unreviewed waiver.'
            printf '%s\n' .uncle/docs/FINAL_AUDIT.md > "$STATE_DIR/repair-source"
            set_state REPAIR
            return 0
        fi
        if [[ "${UNATTENDED:-0}" == 1 ]]; then
            python3 "$ROOT/scripts/lib/audit-findings.py" "$STATE_DIR/documents/FINAL_AUDIT.json" "$STATE_DIR" --unattended --ledger "$UNATTENDED_FILE" </dev/null || exit 1
        else
            python3 "$ROOT/scripts/lib/audit-findings.py" "$STATE_DIR/documents/FINAL_AUDIT.json" "$STATE_DIR" || exit 1
        fi
        [[ "$(hash_file "$STATE_DIR/documents/FINAL_AUDIT.json")" == "$audit_hash" ]] || exit 1
        cp "$VERDICT_FILE" "$STATE_DIR/audit-verdict.original"
        printf '%s\t%s\t%s\n' "$run_id" "READY" "$audit_hash" > "$VERDICT_FILE"
        if [[ -f "$AUDIT_OVERRIDE_FILE" ]]; then
            mv "$AUDIT_OVERRIDE_FILE" "$AUDIT_OVERRIDE_FILE.previous"
        fi
        set_state COMPLETE
        return 0
    fi

    return 1
}
