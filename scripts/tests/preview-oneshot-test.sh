#!/usr/bin/env bash
# preview_build_oneshot: one tool-free call, the page pulled out of the reply and staged; and the rules
# that choose it (hosted runners) and that keep the generic gates out of the preview prompt.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

PAGE='<!doctype html><html><head><title>T</title></head><body>'"$(printf '<p>row</p>%.0s' $(seq 1 40))"'</body></html>'

run_case() {   # name reply-mode
    local name="$1" mode="$2" dir="$TMP/$1"
    mkdir -p "$dir/.uncle/workflow/logs"; printf 'a groovy calculator\n' > "$dir/REQUIREMENTS.md"
    (
        cd "$dir"
        ROOT="$ROOT"; STATE_DIR=".uncle/workflow"; LOG_DIR="$PWD/.uncle/workflow/logs"
        run_claude() {   # prompt stage
            printf '%s|%s|%s|%s\n' "$2" "${WORKFLOW_TOOLS_PREVIEW_BUILD:-}" "${WORKFLOW_TURNS_PREVIEW_BUILD:-}" "$(wc -c < "$1" | tr -d ' ')" >> "$PWD/.uncle/workflow/calls"
            cp "$1" "$PWD/.uncle/workflow/seen-prompt.md"
            case "$mode" in
                page)  python3 -c 'import json,sys; print(json.dumps({"type":"result","result":sys.argv[1]}))' "$PAGE" > "$LOG_DIR/$2.jsonl" ;;
                prose) python3 -c 'import json; print(json.dumps({"type":"result","result":"I could not."}))' > "$LOG_DIR/$2.jsonl" ;;
                crash) return 1 ;;
            esac
        }
        . "$ROOT/scripts/lib/preview-build.sh"
        preview_build_oneshot; echo $? > "$PWD/.uncle/workflow/rc"
    )
}

run_case ok page
check "success: returns 0"                      test "$(cat "$TMP/ok/.uncle/workflow/rc")" == 0
check "success: the page is staged"             grep -q '<body>' "$TMP/ok/.uncle/workflow/preview/index.html"
check "success: exactly one model call"         test "$(wc -l < "$TMP/ok/.uncle/workflow/calls" | tr -d ' ')" == 1
check "success: tools and turns are limited"    grep -q '^preview-build|Read|2|' "$TMP/ok/.uncle/workflow/calls"
check "success: the brief is in the prompt"     grep -q 'a groovy calculator' "$TMP/ok/.uncle/workflow/seen-prompt.md"
check "success: the prompt forbids tools"       grep -q 'Do not call any tool' "$TMP/ok/.uncle/workflow/seen-prompt.md"

run_case prose prose
check "prose reply: nonzero, nothing staged"    bash -c 'test "$(cat "$1/.uncle/workflow/rc")" != 0 && test ! -e "$1/.uncle/workflow/preview/index.html"' _ "$TMP/prose"
run_case crash crash
check "model failure: nonzero"                  test "$(cat "$TMP/crash/.uncle/workflow/rc")" != 0

# A failed one-shot falls back to the tool-based preview, and the driver publishes whichever page exists.
check "fallback to tools when one-shot fails"   grep -q 'elif preview_build_use_oneshot && preview_build_oneshot; then' "$ROOT/scripts/lib/preview-build.sh"
check "tool-based preview is the last resort"   grep -q 'run_claude prompts/preview-build.md preview-build' "$ROOT/scripts/lib/preview-build.sh"

# Which runners use it.
gate() {
    ( ROOT="$ROOT"; . "$ROOT/scripts/lib/preview-build.sh"
      stage_uses_self_hosted() { [[ "$SELF" == 1 ]]; }
      preview_build_use_oneshot && echo yes || echo no )
}
check "hosted: one call"                        test "$(SELF=0 gate)" == yes
check "self-hosted: not one call"               test "$(SELF=1 gate)" == no
check "=1 forces it"                            test "$(WORKFLOW_PREVIEW_BUILD_ONESHOT=1 SELF=1 gate)" == yes
check "=0 forbids it"                           test "$(WORKFLOW_PREVIEW_BUILD_ONESHOT=0 SELF=0 gate)" == no

# The generic gates stay out of the preview prompt: a bypass returns the prompt file untouched.
mkdir -p "$TMP/gates/.uncle/workflow/logs"; printf 'PREVIEW PROMPT ONLY\n' > "$TMP/gates/p.md"
out="$( cd "$TMP/gates"; ROOT="$ROOT"; LOG_DIR="$PWD/.uncle/workflow/logs"; STATE_DIR="$PWD/.uncle/workflow"
        . "$ROOT/scripts/lib/gates.sh" 2>/dev/null
        gated_prompt "$PWD/p.md" preview-build agent "" 2>/dev/null | tail -n 1 )"
check "gates bypassed for preview-build: prompt returned as is" test "$out" == "$TMP/gates/p.md"
part="$( cd "$TMP/gates"; ROOT="$ROOT"; LOG_DIR="$PWD/.uncle/workflow/logs"; STATE_DIR="$PWD/.uncle/workflow"
        . "$ROOT/scripts/lib/gates.sh" 2>/dev/null
        gated_prompt "$PWD/p.md" preview-build-part-script agent "" 2>/dev/null | tail -n 1 )"
check "gates bypassed for the preview parts too" test "$part" == "$TMP/gates/p.md"

[[ "$fails" == 0 ]] && echo "preview-oneshot-test.sh: all checks passed" || exit 1
