#!/usr/bin/env bash
# preview_build_start gating: the preview starts from an approved brief alone,
# records the plan hash only when a plan exists, and stays off for projects
# with nothing to show.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

# case <name> <files...>: a fresh project with the named fixtures, the lib
# sourced with a stub runner, one start attempt, then the background job joined.
run_case() {
    local name="$1"; shift
    local dir="$TMP/$name"
    mkdir -p "$dir/.uncle/workflow/logs"
    while [[ $# -gt 0 ]]; do printf '%s\n' "$2" > "$dir/$1"; shift 2; done
    (
        cd "$dir"
        ROOT="$ROOT" STATE_DIR=".uncle/workflow" LOG_DIR=".uncle/workflow/logs"
        PROJECT_ROOT="$PWD" UNCLE_CONFIG="$PWD/.uncle/config"
        . "$ROOT/scripts/lib/stage-config.sh"
        run_claude() {
            printf '%s\n' "$*" > "$STATE_DIR/ran"
            printf '%s\n' "${WORKFLOW_MODEL_PREVIEW_BUILD:-}" > "$STATE_DIR/model"
            [[ -z "${STUB_LAUNCH:-}" ]] || printf '%s' "$STUB_LAUNCH" > .uncle/launch.json
        }
        . "$ROOT/scripts/lib/preview-build.sh"
        preview_build_start > "$STATE_DIR/out" 2>&1
        [[ -n "$PREVIEW_PID" ]] && wait "$PREVIEW_PID"
        printf '%s\n' "$PREVIEW_STARTED" > "$STATE_DIR/started"
        preview_build_survived; printf '%s\n' "$?" > "$STATE_DIR/survived"
    )
}

WEB_BRIEF='# Calculator
A single page web app: index.html with buttons rendered in the browser.'
API_BRIEF='# Ledger service
A REST API daemon with no user interface.'
PLAN='# Plan
## Architecture
A static index.html and one script; runs in the browser.
## Implementation sequence
1. Page'

run_case brief-only REQUIREMENTS.md "$WEB_BRIEF"
check "starts from the brief alone"            test "$(cat "$TMP/brief-only/.uncle/workflow/started")" == 1
check "runner was invoked for preview-build"   grep -q "preview-build" "$TMP/brief-only/.uncle/workflow/ran"
check "no plan hash without a plan"            test ! -e "$TMP/brief-only/.uncle/workflow/preview-build.plan"
check "brief-only preview never survives"      test "$(cat "$TMP/brief-only/.uncle/workflow/survived")" != 0
check "says it builds from the brief"          grep -q "preview from the brief" "$TMP/brief-only/.uncle/workflow/out"

run_case with-plan REQUIREMENTS.md "$WEB_BRIEF" PROJECT_PLAN.md "$PLAN"
check "starts with a plan"                     test "$(cat "$TMP/with-plan/.uncle/workflow/started")" == 1
check "records the plan hash"                  test -s "$TMP/with-plan/.uncle/workflow/preview-build.plan"
check "says it builds from the plan"           grep -q "preview from the plan" "$TMP/with-plan/.uncle/workflow/out"

CONFIG_MODELS=$'project-plan.model cline-pass/kimi-k3\nimplementation.model anthropic/claude-opus-5'
run_case configured-model REQUIREMENTS.md "$WEB_BRIEF" .uncle/config "$CONFIG_MODELS"
check "preview uses the first configured model" test "$(cat "$TMP/configured-model/.uncle/workflow/model")" == cline-pass/kimi-k3

SELF_HOSTED_MODEL=$'derive-brief.runner self-hosted\nderive-brief.model local/deepseek-v4-flash'
run_case self-hosted-model REQUIREMENTS.md "$WEB_BRIEF" .uncle/config "$SELF_HOSTED_MODEL"
check "preview preserves a self-hosted first model" test "$(cat "$TMP/self-hosted-model/.uncle/workflow/model")" == local/deepseek-v4-flash

# A preview may inherit its runner/model from a reviewer-configured stage, but
# it still writes the early application. It must therefore use the agent shim,
# which supplies the required prompt and positive turn limit to self-hosted.
REVIEWER_MODEL=$'adversarial-review.runner self-hosted\nadversarial-review.model local/deepseek-v4-flash'
run_case reviewer-model REQUIREMENTS.md "$WEB_BRIEF" .uncle/config "$REVIEWER_MODEL"
check "preview remains an agent when inheriting a reviewer model" bash -c '
    ROOT="$1" PROJECT_ROOT="$2" UNCLE_CONFIG="$2/.uncle/config"
    . "$ROOT/scripts/lib/stage-config.sh"
    test "$(uncle_stage_side preview-build)" = agent
' _ "$ROOT" "$TMP/reviewer-model"

WORKFLOW_MODEL_PREVIEW_BUILD=anthropic/claude-haiku-4-5 run_case overridden-model REQUIREMENTS.md "$WEB_BRIEF" .uncle/config "$CONFIG_MODELS"
check "preview model override wins" test "$(cat "$TMP/overridden-model/.uncle/workflow/model")" == anthropic/claude-haiku-4-5

run_case nothing
check "nothing to build from: stays off"       test "$(cat "$TMP/nothing/.uncle/workflow/started")" == 0
check "runner not invoked"                     test ! -e "$TMP/nothing/.uncle/workflow/ran"

run_case headless REQUIREMENTS.md "$API_BRIEF"
check "headless brief: stays off"              test "$(cat "$TMP/headless/.uncle/workflow/started")" == 0
check "headless brief: explains why"           grep -q "nothing to show" "$TMP/headless/.uncle/workflow/out"

# The appended gates make the preview agent record a launch method; nothing it
# wrote was verified, so it must not outlive the preview build.
STUB_LAUNCH='{"kind":"webpage","path":"index.html"}' run_case claims-launch REQUIREMENTS.md "$WEB_BRIEF"
check "preview's launch.json is removed after it finishes" test ! -e "$TMP/claims-launch/.uncle/launch.json"
STUB_LAUNCH='{"kind":"webpage","path":"index.html"}' run_case keeps-launch REQUIREMENTS.md "$WEB_BRIEF" .uncle/launch.json '{"kind":"command","command":["./run"]}'
check "a pre-existing launch.json is restored"      grep -qF '"command"' "$TMP/keeps-launch/.uncle/launch.json"

run_case disabled REQUIREMENTS.md "$WEB_BRIEF"
WORKFLOW_PREVIEW_BUILD=0 run_case disabled2 REQUIREMENTS.md "$WEB_BRIEF"
check "WORKFLOW_PREVIEW_BUILD=0 stays off"     test "$(cat "$TMP/disabled2/.uncle/workflow/started")" == 0

if [[ "$fails" -gt 0 ]]; then echo "preview-build-test.sh: $fails failure(s)"; exit 1; fi
echo "preview-build-test.sh: all checks passed"
