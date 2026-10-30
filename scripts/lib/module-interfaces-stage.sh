#!/usr/bin/env bash
# Derive a shared, binding module-interfaces contract from an approved plan,
# before parallel implementation steps -- each written in isolation, unable
# to see each other's files -- start guessing independently at the shape of
# whatever they import from a sibling step.
#
# Shared by the new-application driver (UPDATED_PROJECT_PLAN.md) and the
# change-workflow driver (CHANGE_PLAN.md), which runs the identical
# parallel_groups/parallel_run_group fan-out against its own plan and has
# exactly the same cross-file-interface-guessing risk. The caller names
# which plan is approved; it defaults to the new-application one so
# stagegate.sh's existing call site needed no change.
#
# Needs from the caller: ROOT, STATE_DIR, LOG_DIR, hash_file (scripts/lib/sha256.sh),
# run_claude.
derive_module_interfaces() {
    local plan="${1:-.uncle/docs/UPDATED_PROJECT_PLAN.md}"
    [[ "${WORKFLOW_MODULE_INTERFACES:-1}" == 1 ]] || return 1
    local canonical="$STATE_DIR/documents/MODULE_INTERFACES.json"
    local hash_file_path="$STATE_DIR/module-interfaces-plan.sha256" plan_hash
    [[ -s "$plan" ]] || return 1
    plan_hash="$(hash_file "$plan")"
    if [[ -s "$canonical" && -s "$hash_file_path" && "$(cat "$hash_file_path")" == "$plan_hash" ]] \
            && python3 -B "$ROOT/scripts/lib/module_interfaces.py" --validate-json "$canonical" >/dev/null 2>&1; then
        return 0
    fi
    local directory="$STATE_DIR/module-interfaces" prompt canonical_abs
    rm -rf "$directory"; mkdir -p "$directory" "$(dirname "$canonical")"
    canonical_abs="$(cd "$(dirname "$canonical")" && pwd)/$(basename "$canonical")"
    prompt="$directory/prompt.md"
    sed "s#{{CANONICAL_PATH}}#$canonical_abs#" "$ROOT/prompts/module-interfaces.md" > "$prompt"
    cat "$plan" >> "$prompt"
    rm -f "$canonical"
    # A subshell: run_claude exits the whole process on a failure it judges
    # unrecoverable (a crashed agent, turns exhausted after its own retry).
    # This stage is explicitly optional and must never take the run down
    # with it -- only the validity check below decides whether it worked.
    ( UNCLE_WORKER_PACKET_PATH="$canonical" run_claude "$prompt" module-interfaces ) \
        > "$LOG_DIR/module-interfaces.log" 2>&1 || true
    if [[ ! -s "$canonical" ]] \
            || ! python3 -B "$ROOT/scripts/lib/module_interfaces.py" --validate-json "$canonical" 2>"$directory/error.txt"; then
        echo "Module interfaces could not be derived; parallel steps will run without a shared contract. See $LOG_DIR/module-interfaces.log." >&2
        rm -f "$canonical" "$hash_file_path"
        return 1
    fi
    printf '%s' "$plan_hash" > "$hash_file_path"
    echo "Module interfaces derived: parallel steps share one exact contract for cross-file exports."
    return 0
}
