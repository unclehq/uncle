#!/usr/bin/env bash
# Schema-checked answers for read-only review lenses on hosted runners.
#
# A lens that only reads and returns one packet (adversarial, manual-checklist, test-review, final-audit, updated-plan review) is asked
# for that packet through the runner's own structured output (Claude --json-schema, Codex outputSchema), instead of writing it with a
# Write tool to a delivery file and being validated, and retried, afterwards. The packet is valid by construction, and the reviewer
# stays strictly read-only. Self-hosted lenses are handled by the HTTP loop (http_agent.py), not here.
#
# Needs from the caller: ROOT, STATE_DIR. Sourcing this file defines a function and nothing else.

# review_schema_setup <prompt_file> <log_name> <output_file> <native: 1|0>
# Sets REVIEW_SCHEMA_FILE to the schema file, or to "" when this call gets none: WORKFLOW_REVIEW_SCHEMA=0, an output that is not
# canonical JSON, a call that is not a panel lens, a runner other than claude or codex, a prompt that names no allowlisted packet
# kind, or (Codex) a call that is not going through native_stage.py (the direct `codex exec` path is left alone).
review_schema_setup() {
    local prompt="$1" log_name="$2" output="$3" native="${4:-0}" dir
    REVIEW_SCHEMA_FILE=""
    [[ "${WORKFLOW_REVIEW_SCHEMA:-1}" != 0 ]] || return 0
    [[ "$output" == *.json && "$log_name" == *-worker-* ]] || return 0
    case "${UNCLE_RESOLVED_RUNNER:-}" in
        claude) ;;
        codex) [[ "$native" == 1 ]] || return 0
               python3 -B "$ROOT/scripts/lib/runner_schema.py" enabled "$log_name" || return 0 ;;
        *) return 0 ;;
    esac
    dir="$STATE_DIR/review-schemas"
    mkdir -p "$dir" || return 0
    if python3 -B "$ROOT/scripts/lib/review_schema.py" prepare "$prompt" "$dir/$log_name.json" 2>/dev/null; then
        REVIEW_SCHEMA_FILE="$dir/$log_name.json"
        rm -f "$REVIEW_SCHEMA_FILE.out"
    else
        rm -f "$dir/$log_name.json"
    fi
    return 0
}
