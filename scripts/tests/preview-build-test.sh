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

# The preview may start before planning completes, but when planning artifacts
# exist it must consume their canonical JSON rather than a rendered Markdown
# approval view.
check "preview prompt names canonical interpretation JSON" grep -qF '.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json' "$ROOT/prompts/preview-build.md"
check "preview prompt names canonical plan JSON" grep -qF '.uncle/workflow/documents/PROJECT_PLAN.json' "$ROOT/prompts/preview-build.md"
check "preview prompt does not read rendered plan markdown" bash -c '! grep -qF ".uncle/docs/PROJECT_PLAN.md, if it exists" "$1"' _ "$ROOT/prompts/preview-build.md"

# A stand-in for preview_vendor.py: records the order of fetch and rewrite, never touches the network.
cat > "$TMP/vendor-stub.py" <<'STUB'
import sys, time
with open('.uncle/workflow/vendor-calls', 'a') as log:
    log.write(sys.argv[1] + '\n')
if sys.argv[1] == 'fetch':
    time.sleep(0.3)
STUB

# case <name> <files...>: a fresh project with the named fixtures, the lib
# sourced with a stub runner, one start attempt, then the background job joined.
run_case() {
    local name="$1"; shift
    local dir="$TMP/$name"
    mkdir -p "$dir/.uncle/workflow/logs"
    while [[ $# -gt 0 ]]; do
        mkdir -p "$(dirname "$dir/$1")"
        printf '%s\n' "$2" > "$dir/$1"
        shift 2
    done
    (
        cd "$dir"
        ROOT="$ROOT" STATE_DIR=".uncle/workflow" LOG_DIR=".uncle/workflow/logs"
        WORKFLOW_PREVIEW_OPEN_BROWSER=0
        PREVIEW_VENDOR_PY="$TMP/vendor-stub.py"
        PROJECT_ROOT="$PWD" UNCLE_CONFIG="$PWD/.uncle/config"
        . "$ROOT/scripts/lib/stage-config.sh"
        run_claude() {
            printf '%s\n' "$*" > "$STATE_DIR/ran"
            printf '%s\n' "${WORKFLOW_MODEL_PREVIEW_BUILD:-}" > "$STATE_DIR/model"
            printf '%s\n' "${WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS:-unset}" > "$STATE_DIR/cap"
            [[ -z "${STUB_LAUNCH:-}" ]] || printf '%s' "$STUB_LAUNCH" > .uncle/launch.json
            if [[ -n "${STUB_STAGE_PAGE:-}" ]]; then
                mkdir -p .uncle/workflow/preview; printf '%s' "$STUB_STAGE_PAGE" > .uncle/workflow/preview/index.html
            fi
            [[ -z "${STUB_FAIL:-}" ]] || return 1
        }
        if [[ -n "${STUB_SHARED:-}" ]]; then
            stage_uses_self_hosted() { [[ "$1" == preview-build || "$1" == project-plan ]]; }
            uncle_stage_model() { if [[ "$1" == preview-build ]]; then printf '%s' "${STUB_PREVIEW_MODEL:-m}"; else printf m; fi; }
        fi
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

# Contention: a preview on the planning model's own server waits for the plan.
STUB_SHARED=1 WORKFLOW_PREVIEW_BUILD_DEFER=auto run_case shared-brief REQUIREMENTS.md "$WEB_BRIEF"
check "shared server: preview waits without a plan"   test "$(cat "$TMP/shared-brief/.uncle/workflow/started")" == 0
check "shared server: says why it waits"              grep -q "waits for the plan" "$TMP/shared-brief/.uncle/workflow/out"
check "shared server: nothing was launched"           test ! -e "$TMP/shared-brief/.uncle/workflow/ran"
STUB_SHARED=1 WORKFLOW_PREVIEW_BUILD_DEFER=auto run_case shared-plan REQUIREMENTS.md "$WEB_BRIEF" PROJECT_PLAN.md "$PLAN"
check "shared server: starts once the plan exists"    test "$(cat "$TMP/shared-plan/.uncle/workflow/started")" == 1
STUB_SHARED=1 STUB_PREVIEW_MODEL=fast WORKFLOW_PREVIEW_BUILD_DEFER=auto run_case other-model REQUIREMENTS.md "$WEB_BRIEF"
check "different model: starts without waiting"       test "$(cat "$TMP/other-model/.uncle/workflow/started")" == 1
STUB_SHARED=1 run_case default-shared REQUIREMENTS.md "$WEB_BRIEF"
check "default: a shared server does not delay the preview" test "$(cat "$TMP/default-shared/.uncle/workflow/started")" == 1
STUB_SHARED=1 WORKFLOW_PREVIEW_BUILD_DEFER=0 run_case no-defer REQUIREMENTS.md "$WEB_BRIEF"
check "defer=0: never waits"                          test "$(cat "$TMP/no-defer/.uncle/workflow/started")" == 1
WORKFLOW_PREVIEW_BUILD_DEFER=1 run_case force-defer REQUIREMENTS.md "$WEB_BRIEF"
check "defer=1: waits for the plan on any runner"     test "$(cat "$TMP/force-defer/.uncle/workflow/started")" == 0


# Speed: the preview is one small hand-written file, so it is told so, given only the tools to write
# it, a short turn limit, and an output cap that makes a runaway cost seconds.
check "preview prompt sets a size budget"          grep -qF 'Size budget (binding)' "$ROOT/prompts/preview-build.md"
check "preview prompt forbids bundlers and CDN links" grep -qF 'No bundler, no `npm`, no build step, no CDN' "$ROOT/prompts/preview-build.md"
check "preview prompt loads React from the local vendor copies" grep -qF '.uncle/vendor/react.production.min.js' "$ROOT/prompts/preview-build.md"
check "preview gets only Read and Write"           grep -qF 'preview-build|preview-build-part-*) fallback="Read,Write"' "$ROOT/scripts/stagegate.sh"
check "preview gets a short turn limit"            grep -qF 'preview-build|preview-build-part-*) fallback=8' "$ROOT/scripts/stagegate.sh"
check "preview opens its generated page through the live reload server" grep -qF 'preview_server.py" start "$PWD" "$STATE_DIR"' "$ROOT/scripts/lib/preview-build.sh"
run_case capped REQUIREMENTS.md "$WEB_BRIEF"
check "preview output is capped by default"        test "$(cat "$TMP/capped/.uncle/workflow/cap")" == 8000
WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS=1234 run_case operator-cap REQUIREMENTS.md "$WEB_BRIEF"
check "an operator's own output limit still wins"  test "$(cat "$TMP/operator-cap/.uncle/workflow/cap")" == 1234

run_case vendor REQUIREMENTS.md "$WEB_BRIEF"
check "libraries are fetched beside the model, then rewritten after it" test "$(tr '\n' ' ' < "$TMP/vendor/.uncle/workflow/vendor-calls")" == "fetch rewrite "


# Publishing: the placeholder is on screen at once, and the staged page replaces it in one step.
STUB_STAGE_PAGE='<!doctype html><title>real</title><body>the real page</body>' run_case published REQUIREMENTS.md "$WEB_BRIEF"
check "the staged page replaces the placeholder"   grep -q 'the real page' "$TMP/published/index.html"
check "the styled preview fallback is snapshotted"  grep -q 'the real page' "$TMP/published/.uncle/workflow/preview/static-index.html"
check "the placeholder text is gone"               bash -c '! grep -q "Building the first look" "$1"' _ "$TMP/published/index.html"
check "no half-published file is left"             test ! -e "$TMP/published/index.html.publishing"
STUB_FAIL=1 run_case failed-preview REQUIREMENTS.md "$WEB_BRIEF"
check "a failed preview leaves no placeholder"     test ! -e "$TMP/failed-preview/index.html"
run_case lone-placeholder REQUIREMENTS.md "$WEB_BRIEF"
check "a stage that wrote nothing keeps the placeholder it was started with" test -e "$TMP/lone-placeholder/index.html"

run_case generated-brief .uncle/docs/REQUIREMENTS.md "$WEB_BRIEF"
check "starts from a generated brief"          test "$(cat "$TMP/generated-brief/.uncle/workflow/started")" == 1

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

# An existing project (a git history with real tracked files) never gets a preview written into its root.
LIB="$ROOT/scripts/lib/preview-build.sh"
probe() { ( cd "$1" && PREVIEW_LIB_DIR="$ROOT/scripts/lib" bash -c ". '$LIB'; preview_existing_project" ) >/dev/null 2>&1; }
mkrepo() {   # name tracked-file-count
    mkdir -p "$TMP/$1"
    ( cd "$TMP/$1" && git init -q && for i in $(seq 1 "$2"); do echo "x$i" > "src$i.js"; done && echo r > README.md \
        && git add . && git -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q --no-gpg-sign -m c )
}
mkrepo existing-big 12; mkrepo existing-small 2
mkdir -p "$TMP/fresh" "$TMP/nogit"; ( cd "$TMP/fresh" && git init -q )
probe "$TMP/existing-big";   big=$?
probe "$TMP/existing-small"; small=$?
probe "$TMP/fresh";          fresh=$?
probe "$TMP/nogit";          nogit=$?
check "twelve tracked source files make an existing project" test "$big" == 0
check "a README and two files do not"                        test "$small" == 1
check "a repository with no commits is a new project"        test "$fresh" == 1
check "a directory outside git is a new project"             test "$nogit" == 1
WORKFLOW_PREVIEW_EXISTING_PROJECT=1 probe "$TMP/existing-big"; forced=$?
check "the override lets a preview run anyway"               test "$forced" == 1
check "start checks it before anything else"                 bash -c 'awk "/^preview_build_start\\(\\)/,/^}/" "$1" | grep -q preview_existing_project' _ "$LIB"

if [[ "$fails" -gt 0 ]]; then echo "preview-build-test.sh: $fails failure(s)"; exit 1; fi
echo "preview-build-test.sh: all checks passed"
