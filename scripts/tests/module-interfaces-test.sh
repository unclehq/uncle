#!/usr/bin/env bash
# derive_module_interfaces: a shared, binding export contract derived once
# from the approved plan, before parallel implementation steps -- each
# written in isolation, unable to read each other's files -- start guessing
# independently at the shape of whatever they import from a sibling step.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
check() { if [[ "$2" == "$3" ]]; then ok; else bad "$1" "expected [$2] got [$3]"; fi; }

sed -n '/^derive_module_interfaces() {/,/^run_parallel_application_implementation() {/p' "$ROOT/scripts/stagegate.sh" \
    | sed '$d' > "$temp/fn.sh"
grep -q '^derive_module_interfaces() {' "$temp/fn.sh" || { echo 'FATAL: could not extract derive_module_interfaces'; exit 2; }

STATE_DIR="$temp/state"
LOG_DIR="$temp/logs"
mkdir -p "$STATE_DIR/documents" "$LOG_DIR" "$temp/.uncle/docs"
cd "$temp"
. "$ROOT/scripts/lib/sha256.sh"
printf '# Project plan\n\n## 1. File ownership\n\n| C-1 | `src/engine.js` | reduce, initialState |\n' > .uncle/docs/UPDATED_PROJECT_PLAN.md

VALID_JSON='{"schema":"uncle.artifact/v1","kind":"module-interfaces","modules":[{"file":"src/engine.js","exports":[{"name":"reduce","kind":"function","signature":"reduce(state, action): State"}]}]}'

# derive_module_interfaces calls run_claude inside a subshell (deliberately,
# so a run_claude exit cannot take the whole run down with it), so a plain
# shell variable this stub increments is lost when that subshell exits. A
# counter file survives it.
calls_file="$temp/calls"
: > "$calls_file"
calls() { wc -l < "$calls_file" | tr -d ' '; }
run_claude() {
    echo x >> "$calls_file"
    [[ "$2" == module-interfaces ]] || { echo "unexpected log_name: $2" >&2; return 1; }
    printf '%s' "$VALID_JSON" > "$UNCLE_WORKER_PACKET_PATH"
}
# shellcheck disable=SC1090
source "$temp/fn.sh"

derive_module_interfaces
check "first call derives the contract" "0" "$?"
check "run_claude was actually called" "1" "$(calls)"
[[ -s "$STATE_DIR/documents/MODULE_INTERFACES.json" ]] || { bad "canonical-written" "no canonical file"; }
[[ -s "$STATE_DIR/module-interfaces-plan.sha256" ]] || { bad "hash-recorded" "no plan hash recorded"; }
check "the prompt states the literal absolute write path, not a placeholder" "yes" \
    "$(grep -Fq "$STATE_DIR/documents/MODULE_INTERFACES.json" "$STATE_DIR/module-interfaces/prompt.md" && echo yes || echo no)"
check "no unresolved placeholder is left in the prompt" "no" \
    "$(grep -Fq '{{CANONICAL_PATH}}' "$STATE_DIR/module-interfaces/prompt.md" && echo yes || echo no)"

derive_module_interfaces
check "second call on the same plan is a cache hit" "0" "$?"
check "cache hit does not call run_claude again" "1" "$(calls)"

printf '# Project plan\n\n## 1. File ownership\n\n| C-1 | `src/engine.js` | reduce, initialState, format |\n' > .uncle/docs/UPDATED_PROJECT_PLAN.md
derive_module_interfaces
check "a changed plan re-derives the contract" "0" "$?"
check "a changed plan calls run_claude again" "2" "$(calls)"

section="$(python3 -B "$ROOT/scripts/lib/module_interfaces.py" --render-section "$STATE_DIR/documents/MODULE_INTERFACES.json")"
case "$section" in
    *'## Fixed module interfaces (binding)'*'`src/engine.js`'*'reduce'*) ok ;;
    *) bad "section-renders" "rendered section missing expected content: $section" ;;
esac

printf '# Project plan\n\n## 1. File ownership\n\n| C-1 | `src/engine.js` | reduce, initialState, format, round |\n' > .uncle/docs/UPDATED_PROJECT_PLAN.md
run_claude() { echo x >> "$calls_file"; :; }  # writes nothing: a failed/empty response
status=0
derive_module_interfaces || status=$?
check "an empty response is non-fatal (returns 1, does not exit the run)" "1" "$status"
[[ ! -e "$STATE_DIR/documents/MODULE_INTERFACES.json" ]] || { bad "failed-canonical-cleared" "stale canonical left behind after a failed derivation"; }

printf '# Project plan\n\n## 1. File ownership\n\n| C-1 | `src/engine.js` | reduce, initialState, format, round, clamp |\n' > .uncle/docs/UPDATED_PROJECT_PLAN.md
run_claude() { echo x >> "$calls_file"; printf '%s' 'not json' > "$UNCLE_WORKER_PACKET_PATH"; }
status=0
derive_module_interfaces || status=$?
check "an invalid response is non-fatal" "1" "$status"

WORKFLOW_MODULE_INTERFACES=0
status=0
derive_module_interfaces || status=$?
check "WORKFLOW_MODULE_INTERFACES=0 disables it outright" "1" "$status"
unset WORKFLOW_MODULE_INTERFACES

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "module-interfaces-test.sh: $FAIL of $((PASS + FAIL)) checks failed"
    exit 1
fi
echo "module-interfaces-test.sh: $PASS checks passed"
