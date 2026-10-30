#!/usr/bin/env bash
# preview_build_parallel: contract first, then the parts side by side, assembled into index.html;
# any failure leaves no index.html so the single-pass preview can run.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

run_case() {   # name mode framework
    local name="$1" mode="$2" framework="${3:-vanilla}" dir="$TMP/$1"
    mkdir -p "$dir/.uncle/workflow/logs"
    (
        cd "$dir"
        ROOT="$ROOT"; STATE_DIR=".uncle/workflow"; LOG_DIR=".uncle/workflow/logs"
        PREVIEW_VENDOR_PY="$TMP/none.py"
        . "$ROOT/scripts/lib/stage-config.sh"
        run_claude() {   # prompt stage
            local part="${2#preview-build-part-}" parts="$STATE_DIR/preview-parts"
            echo "$part" >> "$STATE_DIR/order"
            case "$part" in
                markup|styles|script) [[ -s "$parts/contract.md" ]] || echo "$part before contract" >> "$STATE_DIR/violations" ;;
            esac
            [[ "$mode:$part" != fail:styles ]] || return 1
            case "$part" in
                contract) printf 'framework: %s\ntitle: T\n## Elements\n- #a\n' "$framework" > "$parts/contract.md" ;;
                markup)   printf '<p id="a">x</p>' > "$parts/markup.html" ;;
                styles)   printf '#a{color:red}' > "$parts/styles.css" ;;
                script)   printf 'var a=1' > "$parts/script.js" ;;
            esac
            [[ "$mode:$part" != empty:script ]] || : > "$parts/script.js"
        }
        . "$ROOT/scripts/lib/preview-build.sh"
        preview_build_parallel > "$STATE_DIR/out" 2>&1; echo $? > "$STATE_DIR/rc"
    )
}

run_case ok ok
check "success: returns 0"                       test "$(cat "$TMP/ok/.uncle/workflow/rc")" == 0
check "success: index.html assembled"            grep -q '<p id="a">x</p>' "$TMP/ok/index.html"
check "success: contract ran first"              test "$(head -n1 "$TMP/ok/.uncle/workflow/order")" == contract
check "success: all four parts ran"              test "$(wc -l < "$TMP/ok/.uncle/workflow/order" | tr -d ' ')" == 4
check "success: no part ran before the contract" test ! -e "$TMP/ok/.uncle/workflow/violations"

run_case react ok react
check "react: no markup worker"                  bash -c '! grep -qx markup "$1"' _ "$TMP/react/.uncle/workflow/order"
check "react: three parts ran"                   test "$(wc -l < "$TMP/react/.uncle/workflow/order" | tr -d ' ')" == 3
check "react: local libraries referenced"        grep -q '.uncle/vendor/react.production.min.js' "$TMP/react/index.html"

run_case failed fail
check "worker failure: nonzero"                  test "$(cat "$TMP/failed/.uncle/workflow/rc")" != 0
check "worker failure: no index.html written"    test ! -e "$TMP/failed/index.html"

run_case empty empty
check "empty part: nonzero"                      test "$(cat "$TMP/empty/.uncle/workflow/rc")" != 0
check "empty part: no index.html written"        test ! -e "$TMP/empty/index.html"

# The single-pass preview is still what runs when the parts cannot, and the parts are the default.
check "parts are chosen per runner by default"  grep -qF 'WORKFLOW_PREVIEW_BUILD_PARALLEL:-auto' "$ROOT/scripts/lib/preview-build.sh"
check "single pass is the fallback"              grep -qF 'run_claude prompts/preview-build.md preview-build' "$ROOT/scripts/lib/preview-build.sh"

# A part resolves exactly like the preview stage: runner, model, side.
mkdir -p "$TMP/cfg/.uncle"
printf 'project-plan.runner claude\nproject-plan.model sonnet\n' > "$TMP/cfg/.uncle/config"
resolved() {
    ( cd "$TMP/cfg"; ROOT="$ROOT"; PROJECT_ROOT="$PWD"; UNCLE_CONFIG="$PWD/.uncle/config"
      . "$ROOT/scripts/lib/stage-config.sh"
      uncle_resolve_stage_runner "$1" AGENT 2>/dev/null
      echo "$UNCLE_RESOLVED_RUNNER $(uncle_stage_model "$1" "$UNCLE_RESOLVED_RUNNER") $(uncle_stage_side "$1")" )
}
check "parts resolve like the preview stage"     test "$(resolved preview-build-part-script)" == "$(resolved preview-build)"
check "parts are agent-side"                     test "$(resolved preview-build-part-contract | awk '{print $3}')" == agent

# The page is visible while it is still being written, and a failed attempt leaves no placeholder behind.
progressive() {
    local dir="$TMP/progressive"; mkdir -p "$dir/.uncle/workflow/logs"
    (
        cd "$dir"
        ROOT="$ROOT"; STATE_DIR=".uncle/workflow"; LOG_DIR=".uncle/workflow/logs"
        PREVIEW_VENDOR_PY="$TMP/none.py"
        . "$ROOT/scripts/lib/stage-config.sh"
        run_claude() {
            local part="${2#preview-build-part-}" parts="$STATE_DIR/preview-parts"
            case "$part" in
                contract) printf 'framework: vanilla\ntitle: T\n' > "$parts/contract.md" ;;
                markup)   printf '<p id="a">x</p>' > "$parts/markup.html" ;;
                styles)   printf '#a{color:red}' > "$parts/styles.css" ;;
                script)   sleep 2.5; printf 'var a=1' > "$parts/script.js"
                          # the page seen by a person while the slowest part is still being written
                          cp index.html "$STATE_DIR/seen-mid.html" 2>/dev/null ;;
            esac
        }
        . "$ROOT/scripts/lib/preview-build.sh"
        preview_build_parallel > /dev/null 2>&1; echo $? > "$STATE_DIR/rc"
    )
}
progressive
check "progressive: a page existed while the script was still being written" test -s "$TMP/progressive/.uncle/workflow/seen-mid.html"
check "progressive: the early page already showed the styled markup"        grep -q 'color:red' "$TMP/progressive/.uncle/workflow/seen-mid.html"
check "progressive: the early page had no script yet"                       bash -c '! grep -q "var a=1" "$1"' _ "$TMP/progressive/.uncle/workflow/seen-mid.html"
check "progressive: the final page has everything"                          grep -q 'var a=1' "$TMP/progressive/index.html"
check "progressive: no watcher or temp file is left behind"                 bash -c 'test -z "$(ls "$1" | grep -F .tmp)"' _ "$TMP/progressive"
check "failure removes a placeholder this run created"                      test ! -e "$TMP/failed/index.html"

# An earlier first look is never replaced by a placeholder.
mkdir -p "$TMP/keep/.uncle/workflow/logs"; printf '<h1>first look</h1>' > "$TMP/keep/index.html"
(
    cd "$TMP/keep"; ROOT="$ROOT"; STATE_DIR=".uncle/workflow"; LOG_DIR=".uncle/workflow/logs"
    . "$ROOT/scripts/lib/stage-config.sh"
    run_claude() { return 1; }
    . "$ROOT/scripts/lib/preview-build.sh"
    preview_build_parallel > /dev/null 2>&1
)
check "an existing page survives a failed attempt"                          grep -q 'first look' "$TMP/keep/index.html"

# Which runners use parts.
gate() {
    ( ROOT="$ROOT"; . "$ROOT/scripts/lib/preview-build.sh"
      stage_uses_self_hosted() { [[ "$SELF" == 1 ]]; }
      preview_build_use_parts && echo yes || echo no )
}
check "default: self-hosted previews use parts"      test "$(SELF=1 gate)" == yes
check "default: hosted previews stay single-pass"    test "$(SELF=0 gate)" == no
check "=1 forces parts on a hosted runner"           test "$(WORKFLOW_PREVIEW_BUILD_PARALLEL=1 SELF=0 gate)" == yes
check "=0 forbids parts on a self-hosted runner"     test "$(WORKFLOW_PREVIEW_BUILD_PARALLEL=0 SELF=1 gate)" == no

# The rule against real configs (the driver's own stage_uses_self_hosted logic, not a stub): local models
# write the preview in parts, every other runner in one pass.
runner_gate() {   # config text
    local dir; dir="$(mktemp -d "$TMP/gate.XXXXXX")"; mkdir -p "$dir/.uncle"; printf '%b' "$1" > "$dir/.uncle/config"
    ( cd "$dir"; ROOT="$ROOT"; PROJECT_ROOT="$PWD"; UNCLE_CONFIG="$PWD/.uncle/config"
      . "$ROOT/scripts/tests/workflow_fixture.sh"
      workflow_fixture_source "$ROOT/scripts/lib/stage-config.sh" \
          "$ROOT/scripts/lib/stage-runtime.sh" "$ROOT/scripts/lib/stage-runtime-app.sh"
      . "$ROOT/scripts/lib/preview-build.sh"
      preview_build_use_parts && echo parts || echo single )
}
check "local model: preview in parts"      test "$(runner_gate 'project-plan.runner self-hosted\nproject-plan.model local/deepseek-v4-flash\n')" == parts
check "claude: single pass"                test "$(runner_gate 'project-plan.runner claude\nproject-plan.model sonnet\n')" == single
check "codex: single pass"                 test "$(runner_gate 'project-plan.runner codex\nproject-plan.model gpt\n')" == single
check "kimi: single pass"                  test "$(runner_gate 'project-plan.runner kimi\nproject-plan.model k\n')" == single
check "no configuration: single pass"      test "$(runner_gate '')" == single

[[ "$fails" == 0 ]] && echo "preview-build-parallel-test.sh: all checks passed" || exit 1
