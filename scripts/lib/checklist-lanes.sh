#!/usr/bin/env bash
# Run a checklist as lanes: every batch of checks in its own worker, all at once, no barriers.
# The batches come from checklist_lanes.py (checks that share a resource or a dependency are one lane,
# run in order inside one worker; everything else is pooled into small batches).
#
# The caller supplies, as dynamic scope: `packet_names` (an array this appends to), `failed` (set to 1
# when a worker does not finish), LOG_DIR and ROOT, and a function
#   checklist_run_worker <prompt-file> <label> <check-count> <packet-path>
# that runs one worker session with its driver's own model, effort and budget arguments.

# checklist_lane_batches <manual-checklist.json> <output-file> — batches on stdout of python, count returned.
checklist_lane_batches() {
    local checklist="$1" output="$2" size max
    # An agent session's prompt/cache load is much larger than a handful of
    # independent checklist rows. Give each free row its own worker by
    # default, capped at sixteen workers. Checklist checks frequently spend most
    # of their time waiting on a browser, service, or command, so pooling
    # independent observations merely serializes that wait. Resource- or
    # dependency-linked rows
    # still occupy one ordered lane and are never coalesced with another lane.
    # This applies equally to browser, service, CLI, and filesystem checks.
    size="${WORKFLOW_EXECUTE_CHECKLIST_COMPACT_BATCH_SIZE:-1}"
    [[ "$size" =~ ^[1-9][0-9]*$ ]] || size=1
    max="${WORKFLOW_EXECUTE_CHECKLIST_MAX_WORKERS:-16}"
    [[ "$max" =~ ^[1-9][0-9]*$ ]] || max=16
    python3 -B "$ROOT/scripts/lib/checklist_lanes.py" "$checklist" "$size" "$max" > "$output" 2>/dev/null || return 1
    wc -l < "$output" | tr -d ' '
}

# checklist_run_lanes <worker-directory> <batches-file> <worker-prompt-template>
checklist_run_lanes() {
    local directory="$1" batches_file="$2" template="$3"
    local line id label prompt packet n index=0 pid
    local -a lane_pids=() lane_labels=() lane_sizes=()
    mkdir -p "$directory/prompts"
    # Every prompt exists before the first worker starts: some runner adapters clean transient state as
    # they begin, and preparing siblings lazily made that cleanup race these writes.
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -n "$line" ]] || continue
        index=$((index + 1))
        label="group-1-batch-$index"
        prompt="$directory/prompts/$label.md"
        cp "$template" "$prompt"
        printf '\n## Assigned checks\n\n' >> "$prompt"
        n=0
        for id in $line; do
            printf -- '- Execute `%s`.\n' "$id" >> "$prompt"
            n=$((n + 1))
        done
        if [[ "$n" -gt 1 ]]; then
            printf '\nRun them in the order listed, one after another: they share a resource or depend on each other, so they must not overlap.\n' >> "$prompt"
        fi
        printf '\n## Required result packet\n\nWrite the complete JSON packet to the private delivery path supplied by the driver. Chat text is diagnostics only.\n' >> "$prompt"
        packet_names+=("$label")
        lane_labels+=("$label"); lane_sizes+=("$n")
    done < "$batches_file"

    echo "Checklist lanes: ${#lane_labels[@]} worker(s) running at once."
    for index in "${!lane_labels[@]}"; do
        label="${lane_labels[$index]}"
        prompt="$directory/prompts/$label.md"
        packet="$directory/$label.json"
        ( checklist_run_worker "$prompt" "$label" "${lane_sizes[$index]}" "$packet" ) \
            > "$LOG_DIR/execute-checklist-worker-$label.log" 2>&1 &
        lane_pids+=("$!")
    done
    for index in "${!lane_pids[@]}"; do
        label="${lane_labels[$index]}"
        if ! wait "${lane_pids[$index]}"; then
            echo "Worker $label did not complete; reconciliation will run its assigned rows." >&2
            failed=1
        fi
        if [[ ! -s "$directory/$label.json" ]]; then
            echo "Worker $label did not write its required canonical result packet." >&2
            failed=1
        fi
    done
}
