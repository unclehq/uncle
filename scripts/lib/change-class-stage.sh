#!/usr/bin/env bash
# The CLASSIFY stage: a small, separately timed judgment call that decides how much review a plan needs, for both drivers.
#
# The plan is classified once it exists and before anything reviews it (change-workflow: PLAN -> CLASSIFY ->
# ADVERSARIAL_REVIEW; stagegate: PROJECT_PLAN -> CLASSIFY -> WAIT_PLAN_APPROVAL, ahead of the speculative review). The
# driver computes cheap features, a model proposes a class and review profile, and scripts/lib/change_class.py clamps the
# proposal to a safety floor, so the result can only ever change how many optional lenses run and how finely the review
# findings are split across edit writers -- never drop a lens the plan's risk requires.
#
# It runs on the supervisor's runner and model by default (supervision.runner/model/effort in .uncle/config), or on
# classify-change.runner/model/effort when those are set. When the supervisor's runner is not installed it uses the stage that
# planned the build, so a Codex-only, Kimi-only or self-hosted setup classifies too. The answer is read from a delivery
# file or from the runner's final text, so no runner needs a special protocol.
#
# Fail-open by design: a runner that fails, answers badly, or is disabled yields the deterministic profile and the build goes
# on. WORKFLOW_CLASSIFY=0 turns the stage off (every lens runs, as before); WORKFLOW_CHANGE_CLASS=<class> forces a class.
#
# Needs from the caller: ROOT, STATE_DIR, LOG_DIR, run_claude.

CHANGE_CLASS_PY="${CHANGE_CLASS_PY:-$ROOT/scripts/lib/change_class.py}"

# classify_change_stage <change|app> <plan.md>
classify_change_stage() {
    local family="$1" plan="$2" directory="$STATE_DIR/change-class" prompt delivery summary
    if [[ "${WORKFLOW_CLASSIFY:-1}" == 0 ]]; then
        rm -f "$STATE_DIR/change-class.json"
        echo "Build classification is off (WORKFLOW_CLASSIFY=0); every review lens runs."
        return 0
    fi
    [[ -s "$plan" ]] || { echo "No plan to classify yet; every review lens runs."; return 0; }
    if [[ -z "${WORKFLOW_CHANGE_CLASS:-}" ]] && python3 -B "$CHANGE_CLASS_PY" current "$family" . "$plan"; then
        echo "Build class unchanged for this plan: $(python3 -B "$CHANGE_CLASS_PY" get . class)."
        return 0
    fi
    if [[ -n "${WORKFLOW_CHANGE_CLASS:-}" ]]; then
        python3 -B "$CHANGE_CLASS_PY" force "$family" . "$plan" "$WORKFLOW_CHANGE_CLASS" \
            && echo "Build class forced by WORKFLOW_CHANGE_CLASS." || return 0
        change_class_decide_test_scope "$family" "$plan" || true
        return 0
    fi
    rm -rf "$directory"; mkdir -p "$directory"
    prompt="$directory/prompt.md"
    delivery="$directory/answer.json"
    python3 -B "$CHANGE_CLASS_PY" prompt "$family" . "$plan" "$prompt" "$ROOT/prompts/classify-change.md" \
        || { summary="$(python3 -B "$CHANGE_CLASS_PY" fallback "$family" . "$plan")"; echo "Build class: $summary"; return 0; }
    # The supervisor's defaults (the stage config alias supplies a configured runner and model; these supply what it leaves out).
    if [[ "$(UNCLE_CLASSIFY_FALLBACK_STAGE=x uncle_config_stage classify-change)" == supervision ]]; then
        export WORKFLOW_MODEL_CLASSIFY_CHANGE="${WORKFLOW_MODEL_CLASSIFY_CHANGE-$(uncle_config_get supervision.model || true)}"
        [[ -n "$WORKFLOW_MODEL_CLASSIFY_CHANGE" ]] || export WORKFLOW_MODEL_CLASSIFY_CHANGE=sonnet
        export WORKFLOW_EFFORT_CLASSIFY_CHANGE="${WORKFLOW_EFFORT_CLASSIFY_CHANGE-$(uncle_config_get supervision.effort || true)}"
        [[ -n "$WORKFLOW_EFFORT_CLASSIFY_CHANGE" ]] || export WORKFLOW_EFFORT_CLASSIFY_CHANGE=low
    fi
    # A subshell: run_claude exits the whole process on a failure it judges unrecoverable. This stage must never take the
    # run down; only the validation below decides what it produced.
    ( UNCLE_WORKER_PACKET_PATH="$delivery" UNCLE_CLASSIFY_FALLBACK_STAGE="$([[ "$family" == change ]] && echo change-plan || echo project-plan)" \
        run_claude "$prompt" classify-change "" "" 12 ) > "$LOG_DIR/classify-change.log" 2>&1 || true
    summary="$(python3 -B "$CHANGE_CLASS_PY" finish "$family" . "$plan" "$delivery" "$LOG_DIR/classify-change.jsonl")" \
        || summary="$(python3 -B "$CHANGE_CLASS_PY" fallback "$family" . "$plan" 2>/dev/null)"
    echo "Build class: ${summary:-unavailable; every review lens runs}"
    change_class_decide_test_scope "$family" "$plan" || true
    return 0
}

# change_class_decide_test_scope <family> <plan.md> -- settle how much of the suite the final check runs, once, here, while
# the operator is at the keyboard. docs, test-only and small changes use impacted tests; large and risky changes and every
# new application use the full suite; a standard change asks. Unattended runs never ask and use the full suite, and so does
# a plan whose impact cannot be mapped with confidence (test_scope.py explains why). The answer is a file, so a resumed
# driver does not ask again.
change_class_decide_test_scope() {
    local family="$1" plan="$2" scope decision="$STATE_DIR/test-scope-decision" files impacted total sure answer question
    rm -f "$decision"
    scope="$(python3 -B "$CHANGE_CLASS_PY" get . test_scope full)"
    [[ "$scope" == ask ]] || return 0
    [[ "$family" == change ]] || { echo full > "$decision"; return 0; }
    if [[ "${WORKFLOW_TEST_SCOPE:-auto}" != auto ]]; then return 0; fi
    # shellcheck disable=SC2046
    read -r impacted total sure <<< "$(python3 -B "$ROOT/scripts/lib/test_scope.py" preview . \
        $(python3 -B "$CHANGE_CLASS_PY" owned "$family" . "$plan" | grep -v '^\.uncle/' | tr '\n' ' ') 2>/dev/null || echo '0 0 unsure')"
    if [[ "${sure:-unsure}" != confident ]]; then
        echo "Test scope: the plan's impact on the suites cannot be mapped with confidence; the final check runs the full suite."
        echo full > "$decision"; return 0
    fi
    if [[ "${UNATTENDED:-0}" == 1 ]] \
        || ! { [[ -t 0 ]] || { [[ -n "${UNCLE_STATUS_FILE:-}" && "${UNCLE_SUPERVISION_HOST:-}" != headless ]]; }; }; then
        echo "Test scope: standard change; an unattended run uses the full suite for the final check."
        echo full > "$decision"; return 0
    fi
    question="Standard change: verify with only the ${impacted} test suites it can affect (of ${total}) instead of the full suite? The rest are reported NOT RUN. [Y/N] "
    if declare -f supervision_gate_open > /dev/null; then supervision_gate_open "$question"; fi
    printf '%s' "$question" >&2
    answer=""
    read -r answer || answer=""
    case "$answer" in
        [Yy]|[Yy][Ee][Ss]) echo impacted > "$decision"; echo "Test scope: impacted suites only (${impacted} of ${total}); the rest are reported NOT RUN." ;;
        *) echo full > "$decision"; echo "Test scope: the full suite." ;;
    esac
    return 0
}

# change_class_test_scope -- impacted | full, for the final check. WORKFLOW_TEST_SCOPE=full|impacted wins; auto follows the class.
change_class_test_scope() {
    local forced="${WORKFLOW_TEST_SCOPE:-auto}" scope
    case "$forced" in full|impacted) printf '%s' "$forced"; return 0 ;; esac
    scope="$(python3 -B "$CHANGE_CLASS_PY" get . test_scope full 2>/dev/null)" || scope=full
    case "$scope" in
        impacted) printf impacted ;;
        ask) [[ "$(cat "$STATE_DIR/test-scope-decision" 2>/dev/null)" == impacted ]] && printf impacted || printf full ;;
        *) printf full ;;
    esac
}

# change_class_lenses <default list> -- the adversarial review lenses to run; WORKFLOW_ADVERSARIAL_LENSES wins.
change_class_lenses() {
    local explicit="${WORKFLOW_ADVERSARIAL_LENSES:-}" classified
    if [[ -n "$explicit" ]]; then printf '%s' "$explicit"; return 0; fi
    classified="$(python3 -B "$CHANGE_CLASS_PY" get . lenses 2>/dev/null)" || classified=""
    printf '%s' "${classified:-$1}"
}

# change_class_edit_slice <default> [explicit] -- findings per updated-plan edit writer; an explicit value wins.
change_class_edit_slice() {
    local explicit="${2:-}" classified
    if [[ -n "$explicit" ]]; then printf '%s' "$explicit"; return 0; fi
    classified="$(python3 -B "$CHANGE_CLASS_PY" get . edit_slice 2>/dev/null)" || classified=""
    printf '%s' "${classified:-$1}"
}
