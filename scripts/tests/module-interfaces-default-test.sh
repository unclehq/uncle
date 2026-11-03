#!/usr/bin/env bash
# The module-interfaces stage is `auto` for a new application build (it runs only when the plan has a vertical module: a step that owns
# source and its own tests) and on for a change request; 1 runs it for every plan and 0 never. Real derive function, stubbed agent.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
check() { local what="$1"; shift; if "$@"; then :; else echo "FAIL: $what"; fails=$((fails + 1)); fi; }

line="$(grep -E '^WORKFLOW_MODULE_INTERFACES="\$\{WORKFLOW_MODULE_INTERFACES:-auto\}"$' "$ROOT/scripts/stagegate.sh")"
check "stagegate.sh sets the new-application default to auto" test -n "$line"
value() { env -i bash --norc --noprofile -c "$(printf '%s\n' "$@" "$line" 'echo "$WORKFLOW_MODULE_INTERFACES"')"; }
check "default: auto" test "$(value)" == auto
check "an explicit 1 turns it on" test "$(value 'WORKFLOW_MODULE_INTERFACES=1')" == 1
check "an explicit 0 stays off" test "$(value 'WORKFLOW_MODULE_INTERFACES=0')" == 0

# The real derive function. A plan with a module step (an engine and its unit tests in one step) and one without.
mkdir -p "$TMP/p/.uncle/docs" "$TMP/p/.uncle/workflow/logs"
cat > "$TMP/with-module.md" <<'PLAN'
# Plan

## 12. Implementation sequence

1. Scaffold. Owns: `package.json`, `.gitignore`
2. Engine. Owns: `src/calc.js`, `tests/calc.test.js`
3. View. Owns: `src/App.jsx`
PLAN
cat > "$TMP/no-module.md" <<'PLAN'
# Plan

## 12. Implementation sequence

1. Scaffold. Owns: `package.json`, `.gitignore`
2. Engine. Owns: `src/calc.js`
3. View. Owns: `src/App.jsx`
4. Unit tests. Owns: `tests/calc.test.js`
PLAN
calls() {   # plan env assignments... -> number of agent calls the derive function made
    local plan="$1"; shift
    ( cd "$TMP/p" || exit 1
      cp "$plan" .uncle/docs/UPDATED_PROJECT_PLAN.md
      rm -f "$TMP/agent-calls" .uncle/workflow/module-interfaces-plan.sha256 .uncle/workflow/documents/MODULE_INTERFACES.json
      env -i PATH="$PATH" bash --norc --noprofile -c "$(printf '%s\n' "$@")
          ROOT='$ROOT'; STATE_DIR='$TMP/p/.uncle/workflow'; LOG_DIR='$TMP/p/.uncle/workflow/logs'
          . '$ROOT/scripts/lib/module-interfaces-stage.sh'
          hash_file() { echo hash; }
          run_claude() { echo x >> '$TMP/agent-calls'; return 1; }
          derive_module_interfaces .uncle/docs/UPDATED_PROJECT_PLAN.md > /dev/null 2>&1 || true"
      [[ -e "$TMP/agent-calls" ]] && wc -l < "$TMP/agent-calls" | tr -d ' ' || echo 0 )
}
check "step_groups sees a module in the first plan" test "$(python3 -B "$ROOT/scripts/lib/step_groups.py" has-module "$TMP/with-module.md")" == 1
check "step_groups sees none in the second plan" test "$(python3 -B "$ROOT/scripts/lib/step_groups.py" has-module "$TMP/no-module.md")" == 0
check "new application, plan with a module: the stage runs" test "$(calls "$TMP/with-module.md" "$line")" == 1
check "new application, plan without one: the stage makes no agent call" test "$(calls "$TMP/no-module.md" "$line")" == 0
check "1 runs it for every plan" test "$(calls "$TMP/no-module.md" "$line" 'WORKFLOW_MODULE_INTERFACES=1')" == 1
check "0 never runs it, module or not" test "$(calls "$TMP/with-module.md" "$line" 'WORKFLOW_MODULE_INTERFACES=0')" == 0
check "an unknown value never runs it" test "$(calls "$TMP/with-module.md" "$line" 'WORKFLOW_MODULE_INTERFACES=sometimes')" == 0
check "the shared library still defaults to on (the change-request driver), module or not" test "$(calls "$TMP/no-module.md")" == 1
check "change-workflow.sh does not turn it off" bash -c '! grep -q "WORKFLOW_MODULE_INTERFACES" "$1"' _ "$ROOT/scripts/change-workflow.sh"

[[ "$fails" == 0 ]] && echo "module-interfaces-default-test.sh: all checks passed" || { echo "module-interfaces-default-test.sh: $fails failure(s)"; exit 1; }
