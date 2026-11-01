#!/usr/bin/env bash
set -euo pipefail
# Start-of-run runner validation: a saved cline/unknown runner (including a
# reviewer stage) is rejected with the D1 message before any agent runs.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }
printf '#!/usr/bin/env bash\necho invoked >> "%s/invoked"\nexit 0\n' "$TMP" > "$TMP/stub"; chmod +x "$TMP/stub"

run_driver() { # driver config-text
    local d="$1"; mkdir -p "$TMP/p/.uncle"; printf '%s\n' "$2" > "$TMP/p/.uncle/config"
    rm -f "$TMP/invoked"; cp "$TMP/p/.uncle/config" "$TMP/before"
    set +e
    OUT="$(cd "$TMP/p" && env -u UNCLE_RUNTIME_ROOT -u UNCLE_LIB_DIR UNCLE_PROJECT_ROOT="$TMP/p" UNCLE_CONFIG="$TMP/p/.uncle/config" PROJECT_ROOT="$TMP/p" \
        WORKFLOW_AGENT_CMD="$TMP/stub" WORKFLOW_REVIEWER_CMD="$TMP/stub" WORKFLOW_CLAUDE_CMD="$TMP/stub" \
        bash "$ROOT/scripts/$d" 2>&1 </dev/null)"
    RC=$?; set -e
}
expect() { # name needle
    [[ "$RC" -ne 0 ]] || fail "$1: exit 0"
    case "$OUT" in *"$2"*) ;; *) fail "$1: missing '$2' in: $OUT" ;; esac
    [[ ! -e "$TMP/invoked" ]] || fail "$1: an agent was invoked"
    cmp -s "$TMP/before" "$TMP/p/.uncle/config" || fail "$1: config rewritten"
    [[ ! -e "$TMP/p/.uncle/docs/REQUIREMENTS_INTERPRETATION.md" ]] || fail "$1: stage artifact written"
}
for d in stagegate.sh change-workflow.sh; do
    run_driver "$d" $'runner claude\nadversarial-review.runner cline'
    expect "$d reviewer=cline" "Cline support was removed"
    run_driver "$d" $'implementation.runner Cline'
    expect "$d agent=Cline" "Cline support was removed"
    run_driver "$d" $'requirements.runner bogus'
    expect "$d unknown" "runner 'bogus' is not supported (Cline support was removed). Set it to claude, codex, kimi or self-hosted with 'uncle' -> Configure."
    run_driver "$d" $'runner claude\nsupervision.runner cline'
    expect "$d supervisor=cline" "runner 'cline' is not supported"
done
[[ "$FAILED" -eq 0 ]] && echo "runner-validation-test: all passed" || exit 1
