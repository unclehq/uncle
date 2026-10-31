#!/usr/bin/env bash
# The module-interfaces stage is off by default for a new application build and on for a change request;
# WORKFLOW_MODULE_INTERFACES=1 turns it back on in the new-application driver. Real derive function, stubbed agent.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

line="$(grep -E '^WORKFLOW_MODULE_INTERFACES="\$\{WORKFLOW_MODULE_INTERFACES:-0\}"$' "$ROOT/scripts/stagegate.sh")"
check "stagegate.sh sets the new-application default to off" test -n "$line"
value() { env -i bash --norc --noprofile -c "$(printf '%s\n' "$@" "$line" 'echo "$WORKFLOW_MODULE_INTERFACES"')"; }
check "default: off" test "$(value)" == 0
check "an explicit 1 turns it on" test "$(value 'WORKFLOW_MODULE_INTERFACES=1')" == 1
check "an explicit 0 stays off" test "$(value 'WORKFLOW_MODULE_INTERFACES=0')" == 0

# The real derive function: with the driver's default it never calls the agent; the shared library's own default is unchanged.
mkdir -p "$TMP/p/.uncle/docs" "$TMP/p/.uncle/workflow/logs"
printf '# plan\n' > "$TMP/p/.uncle/docs/UPDATED_PROJECT_PLAN.md"
calls() {   # env assignments... -> number of agent calls the derive function made
    ( cd "$TMP/p" || exit 1
      rm -f "$TMP/agent-calls"
      env -i bash --norc --noprofile -c "$(printf '%s\n' "$@")
          ROOT='$ROOT'; STATE_DIR='$TMP/p/.uncle/workflow'; LOG_DIR='$TMP/p/.uncle/workflow/logs'
          . '$ROOT/scripts/lib/module-interfaces-stage.sh'
          hash_file() { echo hash; }
          run_claude() { echo x >> '$TMP/agent-calls'; return 1; }
          derive_module_interfaces .uncle/docs/UPDATED_PROJECT_PLAN.md > /dev/null 2>&1 || true"
      [[ -e "$TMP/agent-calls" ]] && wc -l < "$TMP/agent-calls" | tr -d ' ' || echo 0 )
}
check "new application default: the stage makes no agent call" test "$(calls "$line")" == 0
check "new application, opted in: the stage runs" test "$(calls "$line" 'WORKFLOW_MODULE_INTERFACES=1')" == 1
check "the shared library still defaults to on (the change-request driver)" test "$(calls)" == 1
check "change-workflow.sh does not turn it off" bash -c '! grep -q "WORKFLOW_MODULE_INTERFACES" "$1"' _ "$ROOT/scripts/change-workflow.sh"

[[ "$fails" == 0 ]] && echo "module-interfaces-default-test.sh: all checks passed" || { echo "module-interfaces-default-test.sh: $fails failure(s)"; exit 1; }
