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

# Stop a worker and everything it started.
checklist_kill_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2>/dev/null); do checklist_kill_tree "$child"; done
    kill "$pid" 2>/dev/null || true
}

# Hedging. A worker is mostly one long model turn, and now and then one takes ten times as long as its siblings (run -10: 253 s
# against 20-33 s), which makes the whole checklist wait for it. Once half the workers have delivered, a single-check worker still
# running after max(WORKFLOW_EXECUTE_CHECKLIST_HEDGE_SECONDS, twice the median delivery time) gets an identical twin; whichever
# delivers a valid packet first is used and the other is stopped. Only single-check lanes are hedged: a lane of several checks
# shares a resource or a dependency, and running it twice at once would break the order it exists to keep.
# WORKFLOW_EXECUTE_CHECKLIST_HEDGE_SECONDS=0 turns it off (default 45).

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
    local hedge_min="${WORKFLOW_EXECUTE_CHECKLIST_HEDGE_SECONDS:-45}" total="${#lane_pids[@]}" finished=0 delivered=0
    local durations="" median hedge_after pstate tstate twin tlabel tpacket status elapsed
    [[ "$hedge_min" =~ ^[0-9]+$ ]] || hedge_min=45
    local -a lane_start=() lane_pstate=() lane_tstate=() lane_twin=() lane_complete=()
    for index in "${!lane_pids[@]}"; do
        lane_start[$index]="$SECONDS"; lane_pstate[$index]=running; lane_tstate[$index]=none; lane_twin[$index]=""; lane_complete[$index]=0
    done
    while (( finished < total )); do
        for index in "${!lane_pids[@]}"; do
            [[ "${lane_complete[$index]}" == 0 ]] || continue
            label="${lane_labels[$index]}"; pid="${lane_pids[$index]}"; twin="${lane_twin[$index]}"
            pstate="${lane_pstate[$index]}"; tstate="${lane_tstate[$index]}"; tlabel="${label}h"; tpacket="$directory/${label}h.json"
            if [[ "$pstate" == running ]] && ! kill -0 "$pid" 2>/dev/null; then
                status=0; wait "$pid" || status=$?
                if [[ "$status" == 0 && -s "$directory/$label.json" ]]; then pstate=ok; else pstate=failed; fi
                lane_pstate[$index]="$pstate"
            fi
            if [[ "$tstate" == running ]] && ! kill -0 "$twin" 2>/dev/null; then
                status=0; wait "$twin" || status=$?
                if [[ "$status" == 0 && -s "$tpacket" ]]; then tstate=ok; else tstate=failed; fi
                lane_tstate[$index]="$tstate"
            fi
            if [[ "$pstate" == ok ]]; then
                if [[ "$tstate" == running ]]; then checklist_kill_tree "$twin"; wait "$twin" 2>/dev/null || true; fi
                lane_complete[$index]=1
            elif [[ "$tstate" == ok ]]; then
                echo "Worker $label: its twin delivered first."
                cp "$tpacket" "$directory/$label.json"
                if [[ "$pstate" == running ]]; then checklist_kill_tree "$pid"; wait "$pid" 2>/dev/null || true; fi
                lane_complete[$index]=1
            elif [[ "$pstate" == failed && "$tstate" != running ]]; then
                echo "Worker $label did not complete; reconciliation will run its assigned rows." >&2
                failed=1
                lane_complete[$index]=1
            elif [[ "$hedge_min" -gt 0 && "$pstate" == running && "$tstate" == none && "${lane_sizes[$index]}" == 1 && $((delivered * 2)) -ge "$total" ]]; then
                median="$(printf '%s\n' $durations | sort -n | awk '{ v[NR] = $1 } END { print (NR ? v[int((NR + 1) / 2)] : 0) }')"
                hedge_after=$(( ${median:-0} * 2 )); [[ "$hedge_after" -ge "$hedge_min" ]] || hedge_after="$hedge_min"
                elapsed=$(( SECONDS - ${lane_start[$index]} ))
                if (( elapsed >= hedge_after )); then
                    echo "Worker $label is slow (${elapsed}s; its siblings took about ${median:-0}s); starting a twin."
                    ( checklist_run_worker "${directory}/prompts/${label}.md" "$tlabel" "${lane_sizes[$index]}" "$tpacket" ) \
                        > "$LOG_DIR/execute-checklist-worker-$tlabel.log" 2>&1 &
                    lane_twin[$index]="$!"; lane_tstate[$index]=running
                fi
            fi
            if [[ "${lane_complete[$index]}" == 1 ]]; then
                finished=$((finished + 1))
                if [[ "${lane_pstate[$index]}" == ok || "${lane_tstate[$index]}" == ok ]]; then
                    delivered=$((delivered + 1)); durations="$durations $(( SECONDS - ${lane_start[$index]} ))"
                fi
            fi
        done
        (( finished >= total )) || sleep 0.5
    done
    for index in "${!lane_labels[@]}"; do
        label="${lane_labels[$index]}"
        if [[ ! -s "$directory/$label.json" ]]; then
            echo "Worker $label did not write its required canonical result packet." >&2
            failed=1
        fi
    done
}
