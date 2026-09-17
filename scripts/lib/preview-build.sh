#!/usr/bin/env bash
# Build something viewable from the approved PROJECT_PLAN.md, while the
# adversarial review and the updated plan are still being written.
#
# The operator asked to see the application before the review stages finish,
# accepting that it is paid for twice. That is the trade: wall clock is never
# worse -- the real implementation still starts where it always did -- and the
# tokens spent here buy an early look, not a shortcut.
#
# Nothing here is evidence. The preview build writes no test report, claims no
# check, and is never the implementation of record: the approved plan is
# implemented afterwards by the stage that always did it. When the review turns
# out not to have changed anything the code depends on, that stage finds the
# work already done and says so.
#
# On by default. WORKFLOW_PREVIEW_BUILD=0 turns it off.
#
# It costs an implementation that is usually thrown away: on the two runs
# measured, the review changed the plan the preview was built from both
# times. What it buys is a working application on screen while the review
# stages run, minutes before the first one would otherwise exist. Wall clock
# is never worse -- the real implementation still starts where it always
# did -- so the whole price is tokens.

# plan_material_hash lives here and is not otherwise sourced by the greenfield
# driver. Without it the survival check silently fails -- safe (it rebuilds) but
# the feature never works.
if ! declare -f plan_material_hash > /dev/null 2>&1; then
    . "${PREVIEW_LIB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}/plan-scope.sh"
fi

PREVIEW_BUILD="${WORKFLOW_PREVIEW_BUILD:-1}"
PREVIEW_PID=""
PREVIEW_STARTED=0

# preview_build_start — launch it, detached, and return immediately.
preview_build_start() {
    [[ "$PREVIEW_BUILD" == "1" ]] || return 0
    [[ "$PREVIEW_STARTED" == 0 ]] || return 0
    [[ -s PROJECT_PLAN.md ]] || return 0

    # Only a web application or a command line tool has anything to show this
    # early. A library, an API or a daemon would spend an implementation's worth
    # of tokens producing nothing the operator can look at, which is the entire
    # justification for this stage.
    local kind
    kind="$(python3 -B "$ROOT/scripts/lib/preview_kind.py" . 2>/dev/null)" || kind=none
    if [[ "$kind" != webpage && "$kind" != command ]]; then
        echo "No preview build: the plan does not describe a web or command line"
        echo "application, so there would be nothing to show."
        return 0
    fi

    PREVIEW_STARTED=1
    # Taken before the preview writes anything. Otherwise the baseline is
    # captured after it, every preview file reads as something that was already
    # sitting in the directory, and the scope checks stop seeing it as output of
    # this build -- which is exactly what they exist to catch.
    if [[ -n "${UNTRACKED_BASELINE:-}" && ! -e "$UNTRACKED_BASELINE" ]] \
       && declare -f snapshot_untracked > /dev/null 2>&1; then
        snapshot_untracked "$UNTRACKED_BASELINE"
    fi
    # The plan this was built from, so the later stage can tell whether the
    # review changed anything the code depends on.
    plan_material_hash PROJECT_PLAN.md > "$STATE_DIR/preview-build.plan" 2>/dev/null || true
    echo
    echo "Building a $kind preview from the approved plan while the review runs."
    echo "It is a first look, not the implementation: the approved plan is"
    echo "implemented properly afterwards, and this is rebuilt if the review"
    echo "changes anything it depends on."
    # Two arguments only: the greenfield driver resolves model, effort, turns
    # and budget from the stage name itself. Passing them the way the change
    # driver does referenced variables that do not exist here, and the preview
    # died on an unbound variable before it wrote anything.
    (
        UNCLE_PREVIEW_BUILD=true \
            run_claude prompts/preview-build.md preview-build
    ) > "$LOG_DIR/preview-build.log" 2>&1 < /dev/null &
    PREVIEW_PID=$!
}

# preview_build_wait — join it before anything reads the tree. Never fatal: a
# failed preview is a preview nobody got, not a failed run.
preview_build_wait() {
    [[ -n "$PREVIEW_PID" ]] || return 0
    local status=0 pid="$PREVIEW_PID"
    PREVIEW_PID=""
    echo
    echo "Waiting for the preview build to finish before implementation..."
    wait "$pid" || status=$?
    if [[ "$status" -ne 0 ]]; then
        echo "Preview build did not complete (status $status); continuing."
        echo "Log: $LOG_DIR/preview-build.log"
    fi
    return 0
}

# preview_build_cancel — from the EXIT trap. A preview must not outlive its run.
preview_build_cancel() {
    if [[ -n "$PREVIEW_PID" ]] && kill -0 "$PREVIEW_PID" 2>/dev/null; then
        echo "Cancelling the preview build..."
        kill "$PREVIEW_PID" 2>/dev/null || true
        wait "$PREVIEW_PID" 2>/dev/null || true
    fi
    PREVIEW_PID=""
    return 0
}

# preview_build_survived — 0 when the review left every section the code depends
# on untouched, so the tree already holds work built to the approved design.
preview_build_survived() {
    local recorded
    [[ "$PREVIEW_STARTED" == 1 ]] || return 1
    [[ -s "$STATE_DIR/preview-build.plan" ]] || return 1
    [[ -s UPDATED_PROJECT_PLAN.md ]] || return 1
    recorded="$(cat "$STATE_DIR/preview-build.plan")"
    [[ "$recorded" == "$(plan_material_hash UPDATED_PROJECT_PLAN.md)" ]]
}
