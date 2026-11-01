#!/usr/bin/env bash
# Build something viewable from the brief, while the plan, the adversarial
# review and the updated plan are still being written.
#
# It starts as soon as the brief is approved, at the repository root where the
# implementation of record later rewrites it in place -- so the tab opened on
# the first look is the tab that shows the real application. It never runs at
# the same time as implementation (IMPLEMENT joins it first); it does run beside
# planning, whose prompts say what an unexplained page at the root is.
# .uncle/docs/PROJECT_PLAN.md and .uncle/docs/REQUIREMENTS_INTERPRETATION.md are used when they already
# exist and skipped when they do not.
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

# preview_open_page — serve the generated root page and open its loopback URL.
# PreviewServer adds a reload snippet on the wire, so publishing the finished
# index.html refreshes the tab that initially displayed the placeholder.
preview_open_page() {
    [[ "${WORKFLOW_PREVIEW_OPEN_BROWSER:-1}" == 1 ]] || return 0
    [[ -s index.html ]] || return 0
    if [[ -s "$STATE_DIR/preview-server.pid" ]] \
        && kill -0 "$(cat "$STATE_DIR/preview-server.pid" 2>/dev/null)" 2>/dev/null; then
        return 0
    fi
    python3 -B "$ROOT/scripts/lib/preview_server.py" start "$PWD" "$STATE_DIR" \
        > "$LOG_DIR/preview-server.log" 2>&1 < /dev/null &
}

# Keep a standalone, browser-ready fallback. Implementation can replace the
# root index with a Vite source entrypoint before dependencies have arrived;
# preview_server serves this snapshot until it can safely hand the tab to Vite.
preview_snapshot_static() {
    [[ -s index.html ]] || return 0
    mkdir -p "$STATE_DIR/preview"
    cp index.html "$STATE_DIR/preview/static-index.html.publishing" \
        && mv -f "$STATE_DIR/preview/static-index.html.publishing" \
            "$STATE_DIR/preview/static-index.html"
}

# preview_build_model — use the selected preview stage model. `preview-build`
# resolves to the first configured model stage in stage-config.sh, so its
# runner and model stay paired (e.g. an OpenCode `local/...` model runs through
# OpenCode rather than being handed to another runner). A dedicated environment override
# remains useful for one-off preview experiments.
preview_build_model() {
    if [[ -n "${WORKFLOW_MODEL_PREVIEW_BUILD:-}" ]]; then
        printf '%s' "$WORKFLOW_MODEL_PREVIEW_BUILD"
        return 0
    fi

    if declare -f uncle_has_config > /dev/null 2>&1 && uncle_has_config \
            && declare -f uncle_stage_model > /dev/null 2>&1 \
            && declare -f uncle_stage_runner > /dev/null 2>&1; then
        local runner model
        runner="$(uncle_stage_runner preview-build)"
        model="$(uncle_stage_model preview-build "$runner")"
        if [[ -n "$model" ]]; then
            printf '%s' "$model"
            return 0
        fi
    fi
    # `haiku` is a Claude CLI alias, not a portable cheap-preview model.  A
    # configured Codex/Kimi preview with no explicit model must invoke
    # its runner without --model and let that runner select its own default.
    # Passing haiku to Codex fails before preview generation begins.
    if declare -f uncle_stage_runner > /dev/null 2>&1 \
       && [[ "$(uncle_stage_runner preview-build)" != "claude" ]]; then
        return 0
    fi
    printf '%s' haiku
}

# preview_build_defer — 0 while the preview should wait for the plan.
#
# Planning is a single decode stream, and the preview is a second one on the
# same model server: measured on a local model, the preview's 160-360 s of
# generation ran beside project-plan and slowed both.  When the two stages use the
# same self-hosted model they share a server, so the preview waits until the plan
# exists and starts beside the review panel instead -- a parallel fan-out the server
# can batch -- and is built from the plan rather than the brief alone.  A preview
# on a different model, or on a hosted runner, has no such contention and starts
# as soon as the brief is approved.
#
# Off by default: the operator asked for the application on screen while planning runs,
# and waiting for the plan trades that away.  WORKFLOW_PREVIEW_BUILD_DEFER=auto defers
# only on a shared self-hosted server, =1 always defers until the plan exists, =0 (the
# default) never does.
PREVIEW_DEFER_NOTED=0
preview_build_defer() {
    local mode="${WORKFLOW_PREVIEW_BUILD_DEFER:-0}"
    [[ "$mode" != 0 ]] || return 1
    [[ -s .uncle/docs/PROJECT_PLAN.md || -s PROJECT_PLAN.md ]] && return 1
    if [[ "$mode" != 1 ]]; then
        declare -f stage_uses_self_hosted > /dev/null 2>&1 \
            && declare -f uncle_stage_model > /dev/null 2>&1 || return 1
        [[ -z "${WORKFLOW_MODEL_PREVIEW_BUILD:-}" ]] || return 1
        stage_uses_self_hosted preview-build AGENT && stage_uses_self_hosted project-plan AGENT || return 1
        [[ "$(uncle_stage_model preview-build self-hosted)" == "$(uncle_stage_model project-plan self-hosted)" ]] || return 1
    fi
    if [[ "$PREVIEW_DEFER_NOTED" == 0 ]]; then
        PREVIEW_DEFER_NOTED=1
        echo "Preview build waits for the plan: it shares a model server with planning."
    fi
    return 0
}

# preview_existing_project — 0 when the directory already holds a project of its own: tracked files in a git
# history.  The preview writes at the repository root (index.html, assets) for the implementation to rewrite, which
# is right for a new application and wrong for an existing codebase, where it drops a stray page into the repo.
# (An issue run on Uncle's own repository got an index.html in its root.)  A brand-new project has no commits, and
# a few tracked files such as a README or LICENSE do not make an existing project.
preview_existing_project() {
    [[ "${WORKFLOW_PREVIEW_EXISTING_PROJECT:-0}" != 1 ]] || return 1
    git rev-parse --verify -q HEAD > /dev/null 2>&1 || return 1
    local tracked
    tracked="$(git ls-files 2>/dev/null | grep -v -E '^(README|LICENSE|\.gitignore|\.uncle/)' | head -n "${PREVIEW_EXISTING_FILES:-8}" | wc -l | tr -d ' ')"
    [[ "${tracked:-0}" -ge "${PREVIEW_EXISTING_FILES:-8}" ]]
}

# preview_build_start — launch it, detached, and return immediately.
preview_build_start() {
    [[ "$PREVIEW_BUILD" == "1" ]] || return 0
    [[ "$PREVIEW_STARTED" == 0 ]] || return 0
    if preview_existing_project; then
        echo "No preview build: this directory already holds a project, and a preview would write into its root."
        return 0
    fi
    if preview_build_defer; then return 0; fi
    [[ -s .uncle/docs/PROJECT_PLAN.md || -s PROJECT_PLAN.md || -s "${DOCUMENT_BUDGET_SOURCE:-.uncle/docs/REQUIREMENTS.md}" || -s .uncle/docs/REQUIREMENTS.md || -s REQUIREMENTS.md ]] || return 0

    # Only a web application or a command line tool has anything to show this
    # early. A library, an API or a daemon would spend an implementation's worth
    # of tokens producing nothing the operator can look at, which is the entire
    # justification for this stage.
    local kind
    kind="$(python3 -B "$ROOT/scripts/lib/preview_kind.py" . 2>/dev/null)" || kind=none
    if [[ "$kind" != webpage && "$kind" != command ]]; then
        echo "No preview build: the brief does not describe a web or command line"
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
    # An instant first look, painted from the brief with no model: the tab opens now, and the
    # model's page replaces this one when it lands (preview_placeholder.py).  Only for a web page.
    mkdir -p .uncle/workflow/preview
    rm -f .uncle/workflow/preview/index.html
    if [[ "$kind" == webpage ]]; then
        python3 -B "${PREVIEW_PLACEHOLDER_PY:-$ROOT/scripts/lib/preview_placeholder.py}" . > /dev/null 2>&1 || true
        preview_snapshot_static
        preview_open_page
    fi
    # The plan this was built from, so the later stage can tell whether the
    # review changed anything the code depends on. A preview built from the
    # brief alone records nothing, and is never taken as built to the plan.
    rm -f "$STATE_DIR/preview-build.plan"
    if [[ -s .uncle/docs/PROJECT_PLAN.md || -s PROJECT_PLAN.md ]]; then
        local plan_file=.uncle/docs/PROJECT_PLAN.md
        [[ -s "$plan_file" ]] || plan_file=PROJECT_PLAN.md
        plan_material_hash "$plan_file" > "$STATE_DIR/preview-build.plan" 2>/dev/null || true
    fi
    echo
    if [[ -s .uncle/docs/PROJECT_PLAN.md || -s PROJECT_PLAN.md ]]; then
        echo "Building a $kind preview from the plan while the review runs."
    else
        echo "Building a $kind preview from the brief while planning runs."
    fi
    echo "It is a first look, not the implementation: the approved plan is"
    echo "implemented properly afterwards, and this is rebuilt if the review"
    echo "changes anything it depends on."
    # Two arguments only: the greenfield driver resolves model, effort, turns
    # and budget from the stage name itself. Passing them the way the change
    # driver does referenced variables that do not exist here, and the preview
    # died on an unbound variable before it wrote anything.
    (
        # The gates appended to every implementation prompt ask the agent to
        # record its launch method in .uncle/launch.json, and the preview agent
        # obliges. Nothing it wrote has been verified, and the implementation
        # of record writes the real one; whatever the preview leaves there is
        # put back the way it was.
        launch_before=""
        [[ -f .uncle/launch.json ]] && launch_before="$(cat .uncle/launch.json)"
        status=0
        # React, ReactDOM and Babel download beside the model, not after it: the page it writes
        # loads them from .uncle/vendor/, so a React preview costs no CDN round trip and no tokens.
        python3 -B "${PREVIEW_VENDOR_PY:-$ROOT/scripts/lib/preview_vendor.py}" fetch . &
        vendor_pid=$!
        # A throwaway first look does not need the top tier deliberating over
        # it: the last one spent 124s and ~11,900 output tokens to produce a
        # 2 KB page. Speed is the whole product of this stage.
        # A page is about 2k tokens.  Cap the output so a runaway costs seconds, not the minutes a
        # 32k-token default allows; an operator's own limit still wins.
        [[ -n "${WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS:-}" ]] \
            || export WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS="${WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS_PREVIEW_BUILD:-8000}"
        # Exported for the whole subshell: the single-pass stage and every part worker read them.
        export UNCLE_PREVIEW_BUILD=true
        export WORKFLOW_MODEL_PREVIEW_BUILD="$(preview_build_model)"
        export WORKFLOW_EFFORT_PREVIEW_BUILD="${WORKFLOW_EFFORT_PREVIEW_BUILD:-low}"
        if preview_build_use_parts && preview_build_parallel; then
            echo "Preview built in parallel parts."
        elif preview_build_use_oneshot && preview_build_oneshot; then
            echo "Preview built in one call."
        else
            run_claude prompts/preview-build.md preview-build || status=$?
        fi
        wait "$vendor_pid" 2>/dev/null || true
        # Publish the staged page over the placeholder in one step, so the tab swaps pages once.
        if [[ -s .uncle/workflow/preview/index.html ]]; then
            cp .uncle/workflow/preview/index.html index.html.publishing \
                && mv -f index.html.publishing index.html
        elif [[ "$status" != 0 && "$(grep -c "Building the first look" index.html 2>/dev/null)" -gt 0 ]]; then
            rm -f index.html      # the stage failed and only the placeholder exists: not a preview
        fi
        python3 -B "${PREVIEW_VENDOR_PY:-$ROOT/scripts/lib/preview_vendor.py}" rewrite . || true
        preview_snapshot_static
        if [[ -n "$launch_before" ]]; then
            printf '%s' "$launch_before" > .uncle/launch.json
        else
            rm -f .uncle/launch.json
        fi
        exit "$status"
    ) > "$LOG_DIR/preview-build.log" 2>&1 < /dev/null &
    PREVIEW_PID=$!
}

# preview_build_use_oneshot — whether to ask for the whole page in a single tool-free call.
#
# The tool-based preview makes several API round trips (read the brief, write the file, report), each
# over a large cached prompt.  One call that embeds the inputs and answers with the page removes them
# all.  For a self-hosted model the parts path wins instead (decode is the cost there), so the default
# is one call for every other runner.  WORKFLOW_PREVIEW_BUILD_ONESHOT=1 forces it, =0 forbids it.
preview_build_use_oneshot() {
    case "${WORKFLOW_PREVIEW_BUILD_ONESHOT:-auto}" in
        1) return 0 ;;
        0) return 1 ;;
    esac
    declare -f stage_uses_self_hosted > /dev/null 2>&1 || return 0
    ! stage_uses_self_hosted preview-build AGENT
}

# preview_build_oneshot — one model call, no tools: the prompt carries the brief, the interpretation and
# the plan, the reply is the page, and the driver pulls it out and stages it for publishing.  Nonzero
# when the reply holds no usable page, and the caller runs the tool-based preview.
preview_build_oneshot() {
    local state helper="$ROOT/scripts/lib/preview_oneshot.py" prompt
    case "$STATE_DIR" in /*) state="$STATE_DIR" ;; *) state="$PWD/$STATE_DIR" ;; esac
    prompt="$state/preview-oneshot-prompt.md"
    mkdir -p "$state/preview"
    python3 -B "$helper" prompt . > "$prompt" || return 1
    # Read is only a harmless allow-list entry: the prompt says no tools, and one retry turn is the limit.
    WORKFLOW_TOOLS_PREVIEW_BUILD=Read WORKFLOW_TURNS_PREVIEW_BUILD=2 \
        run_claude "$prompt" preview-build || return 1
    python3 -B "$helper" extract "$LOG_DIR/preview-build.jsonl" "$state/preview/index.html"
}

# preview_build_use_parts — whether to write the page in parallel parts.
#
# Parts pay off where decoding is slow: a local model writes a page at about thirty tokens a second, so
# three short parts side by side beat one long one.  A fast hosted model writes the whole page in 15
# seconds, and the parts only add a serial contract step and a second and third session -- measured on
# haiku, 14-17 s single-pass against about 65 s in parts.  So the default is parts for a self-hosted
# preview and one pass for everything else.  WORKFLOW_PREVIEW_BUILD_PARALLEL=1 forces parts, =0 forbids them.
preview_build_use_parts() {
    case "${WORKFLOW_PREVIEW_BUILD_PARALLEL:-auto}" in
        1) return 0 ;;
        0) return 1 ;;
    esac
    declare -f stage_uses_self_hosted > /dev/null 2>&1 || return 1
    stage_uses_self_hosted preview-build AGENT
}

# preview_build_parallel — the page in parts (preview_build_parts.py): a short contract, then markup,
# styles and script written side by side, assembled into one index.html by the driver.  Nonzero, with
# no index.html written, on any failure; the caller then runs the single-pass preview.
preview_build_parallel() {
    local directory="$STATE_DIR/preview-parts" helper="$ROOT/scripts/lib/preview_build_parts.py"
    local phase name prompt pid failed watcher="" created=0
    local -a pids names
    rm -rf "$directory"; mkdir -p "$directory/prompts"
    # Show the page as it grows: a placeholder within a second, then each part as it lands.  The tab
    # opens on the first sighting and reloads on every change, so a person watches it fill in.
    # Only when there is no page yet: an earlier first look is not replaced by a placeholder.
    if [[ ! -e index.html ]]; then
        created=1
        python3 -B "$helper" watch "$directory" index.html "$directory/stop" > /dev/null 2>&1 &
        watcher=$!
    fi
    preview_build_parts_finish() {   # status
        : > "$directory/stop"
        [[ -z "$watcher" ]] || wait "$watcher" 2>/dev/null || true
        # A page this function made and could not finish is not a preview; the single pass starts clean.
        if [[ "$1" != 0 && "$created" == 1 ]]; then rm -f index.html; fi
        return "$1"
    }
    for phase in 1 2; do
        pids=(); names=()
        for name in $(python3 -B "$helper" names "$directory" "$phase"); do
            prompt="$directory/prompts/$name.md"
            python3 -B "$helper" prompt "$name" "$directory" "$ROOT/prompts/preview-build.md" "$prompt" || { preview_build_parts_finish 1; return 1; }
            ( SESSION_REUSE=0 UNCLE_RUNNER_REUSE=0 PROGRESS_TOTAL=0 \
                run_claude "$prompt" "preview-build-part-$name" ) > "$LOG_DIR/preview-build-part-$name.log" 2>&1 &
            pids+=("$!"); names+=("$name")
        done
        failed=0
        for pid in "${!pids[@]}"; do
            wait "${pids[$pid]}" || failed=1
        done
        [[ "$failed" == 0 ]] || { preview_build_parts_finish 1; return 1; }
    done
    # Stop the preview writer first: the strict page replaces the partial one, never the other way round.
    : > "$directory/stop"; [[ -z "$watcher" ]] || wait "$watcher" 2>/dev/null || true
    python3 -B "$helper" assemble "$directory" index.html || { preview_build_parts_finish 1; return 1; }
    return 0
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
    [[ -s .uncle/docs/UPDATED_PROJECT_PLAN.md ]] || return 1
    recorded="$(cat "$STATE_DIR/preview-build.plan")"
    [[ "$recorded" == "$(plan_material_hash .uncle/docs/UPDATED_PROJECT_PLAN.md)" ]]
}
