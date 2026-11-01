#!/usr/bin/env bash
# review_schema_setup decides whether a review lens gets the runner's schema, the direct claude shim passes it, and both drivers use it.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }
printf 'Review.\n\nReturn {"schema":"uncle.artifact/v1","kind":"final-audit-worker-packet","findings":[]}\n' > "$work/lens.md"
printf 'Run the checks.\n\nReturn {"schema":"uncle.artifact/v1","kind":"checklist-execution-worker-packet","results":[]}\n' > "$work/exec.md"

setup() {   # <runner> <log_name> <output> <native> [prompt] [ENV=...]
    env -i PATH="$PATH" HOME="$HOME" UNCLE_CONFIG="$work/config" ${6:+"$6"} bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='$work/state'; UNCLE_RESOLVED_RUNNER='$1'
        . '$ROOT/scripts/lib/review-schema.sh'
        review_schema_setup '${5:-$work/lens.md}' '$2' '$3' '$4'
        printf '%s' \"\$REVIEW_SCHEMA_FILE\""
}
LENS=final-audit-review-worker-verification
got="$(setup claude "$LENS" "$work/o.json" 0)"
eq "claude gets a schema on the direct path" "$got" "$work/state/review-schemas/$LENS.json"
[[ -s "$work/state/review-schemas/$LENS.json" ]] || bad "no schema file was written"
python3 -c "import json;assert json.load(open('$work/state/review-schemas/$LENS.json'))['properties']['kind']" 2>/dev/null || bad "the schema file is not the packet schema"
eq "claude gets a schema through native_stage" "$(setup claude "$LENS" "$work/o.json" 1)" "$work/state/review-schemas/$LENS.json"
eq "codex gets one through native_stage" "$(setup codex "$LENS" "$work/o.json" 1)" "$work/state/review-schemas/$LENS.json"
eq "codex on the direct exec path is left alone" "$(setup codex "$LENS" "$work/o.json" 0)" ""
eq "a self-hosted lens is not handled here" "$(setup self-hosted "$LENS" "$work/o.json" 1)" ""
eq "kimi is not handled here" "$(setup kimi "$LENS" "$work/o.json" 1)" ""
eq "a stage that is not a panel lens gets none" "$(setup claude final-audit "$work/o.json" 1)" ""
eq "a Markdown output gets none" "$(setup claude "$LENS" "$work/o.md" 1)" ""
eq "a worker that needs its tools gets none" "$(setup claude execute-checklist-worker-1 "$work/o.json" 1 "$work/exec.md")" ""
eq "a prompt naming no packet gets none" "$(setup claude "$LENS" "$work/o.json" 1 "$ROOT/README.md")" ""
eq "WORKFLOW_REVIEW_SCHEMA=0 turns it off" "$(setup claude "$LENS" "$work/o.json" 1 '' WORKFLOW_REVIEW_SCHEMA=0)" ""
eq "codex honours the runner's own schema switch" "$(setup codex "$LENS" "$work/o.json" 1 '' WORKFLOW_RUNNER_SCHEMA_ENFORCE=0)" ""
[[ ! -e "$work/state/review-schemas/execute-checklist-worker-1.json" ]] || bad "a schema file was left for a worker that gets none"

# --- the direct claude shim ---------------------------------------------------------------------------------------------------------
cat > "$work/claude" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$ARGV_LOG"
cat > /dev/null
printf '%s\n' '{"type":"result","is_error":false,"result":"{\"schema\":\"uncle.artifact/v1\",\"kind\":\"final-audit-worker-packet\",\"findings\":[]}","usage":{"input_tokens":1,"output_tokens":1}}'
FAKE
chmod +x "$work/claude"
shim() {   # <output> [ENV...]
    local out="$1"; shift
    env -i PATH="$PATH" HOME="$HOME" WORKFLOW_REVIEWER_CLAUDE_CMD="$work/claude" ARGV_LOG="$work/argv" "$@" \
        bash "$ROOT/scripts/reviewer-claude.sh" exec --ephemeral --sandbox read-only --output-last-message "$out" 'Review it.' > /dev/null 2>&1
}
echo '{"type":"object"}' > "$work/s.json"
shim "$work/shim-out.json" UNCLE_OUTPUT_SCHEMA_FILE="$work/s.json" UNCLE_ARTIFACT_DELIVERY=
grep -qx -- '--json-schema' "$work/argv" || bad "the shim did not pass --json-schema"
grep -qx 'Read,Glob,Grep' "$work/argv" || bad "the shim lens is not read-only under a schema"
grep -q '"kind": *"final-audit-worker-packet"' "$work/shim-out.json" || bad "the shim did not write the packet as the output"
shim "$work/shim-out2.json"
grep -qx -- '--json-schema' "$work/argv" && bad "the shim passed a schema nobody asked for"
echo '{}' > "$work/delivery.json"
shim "$work/shim-out3.json" UNCLE_OUTPUT_SCHEMA_FILE="$work/s.json" UNCLE_ARTIFACT_DELIVERY="$work/delivery.json"
grep -qx -- '--json-schema' "$work/argv" && bad "the shim mixed a schema with a delivery file"

# --- both drivers use it ------------------------------------------------------------------------------------------------------------
for driver in stagegate.sh change-workflow.sh; do
    f="$ROOT/scripts/$driver"
    grep -q 'review-schema.sh' "$f" || bad "$driver does not source review-schema.sh"
    grep -q 'review_schema_setup "\$prompt_file" "\$log_name" "\$output_file"' "$f" || bad "$driver does not set the schema up"
    grep -q 'if \[\[ "\$output_file" == \*.json && -z "\$review_schema" \]\]' "$f" || bad "$driver still asks a schema lens to write a delivery file"
    grep -q 'UNCLE_OUTPUT_SCHEMA_FILE="\$review_schema"' "$f" || bad "$driver does not pass the schema to the runner"
    grep -q 'cp "\$review_schema.out" "\$output_file"' "$f" || bad "$driver ignores the restored structured output"
done
[[ "$(grep -c 'if \[\[ "\$output_file" == \*.json && -z "\$review_schema" \]\]' "$ROOT/scripts/change-workflow.sh")" == 2 ]] \
    || bad "change-workflow.sh must skip both the delivery request and the tail delivery check"
[[ $fail == 0 ]] && echo "review-schema-setup-test.sh: ok"
exit $fail
