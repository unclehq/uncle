#!/usr/bin/env bash
# Start the baseline at the very beginning of the change-request flow, so IMPLEMENT does not wait for it.
#
# The approved command list comes from the planning model's BASELINE_REPORT, so the baseline used to start only at PLAN
# (after ANALYZE and its approval) and IMPLEMENT then waited on it ("Waiting for the baseline suite started during planning").
# Here the project's own test commands are detected from the repository (scripts/lib/early_baseline.py) and run in the
# background against the unmodified tree the moment the flow starts, niced so the planning model is not slowed.
#
# The results are only *reused*, never trusted blindly. capture_green_baseline asks early_baseline_reuse, which accepts them only
# when (1) the early run finished, (2) every approved command is one of the commands it ran, and (3) the tree is byte-identical
# to the one it started from. Otherwise they are discarded and the approved list runs exactly as before, so a wrong guess costs
# one background suite and nothing else. WORKFLOW_EARLY_BASELINE=0 turns this off.
#
# Needs from the caller: ROOT, STATE_DIR, LOG_DIR, GREEN_CHECK, GREEN_BASE, green_run (scripts/lib/green-check.sh).

# early_baseline_start -- once per run, before the first model stage; returns at once.
early_baseline_start() {
    local dir="$STATE_DIR/early-baseline" commands pid
    [[ "${WORKFLOW_EARLY_BASELINE:-1}" == 1 && "${GREEN_CHECK:-1}" == 1 ]] || return 0
    [[ "${WORKFLOW_BASELINE_BACKGROUND:-1}" == 1 ]] || return 0
    [[ ! -s "$GREEN_BASE" && ! -e "$dir/started" ]] || return 0
    commands="$(python3 -B "$ROOT/scripts/lib/early_baseline.py" detect "$PWD" 2>/dev/null)" || return 0
    [[ -n "$commands" ]] || return 0
    rm -rf "$dir"; mkdir -p "$dir"
    printf '%s\n' "$commands" > "$dir/commands"
    python3 -B "$ROOT/scripts/lib/tree_fingerprint.py" "$PWD" "$dir/commands" > "$dir/fingerprint" 2>/dev/null || return 0
    : > "$dir/started"
    echo
    echo "Starting the project's test baseline in the background now, before planning:"
    sed 's/^/  /' "$dir/commands"
    (
        status=0
        green_run "$dir/commands" "$dir/baseline.tsv" "$dir/baseline.log" "" "" || status=$?
        # The run itself must not have changed the tree it is meant to describe.
        python3 -B "$ROOT/scripts/lib/tree_fingerprint.py" "$PWD" "$dir/commands" > "$dir/fingerprint.after" 2>/dev/null || true
        printf '%s\n' "$status" > "$dir/done"
    ) > "$LOG_DIR/early-baseline.bg.log" 2>&1 < /dev/null &
    pid=$!
    printf '%s\n' "$pid" > "$dir/pid"
    # Lowered priority only, from here (a subshell's own $$ is still the parent's): the suite competes with a planning stage
    # that is waiting on a model, and children forked after this inherit it.
    renice -n "${WORKFLOW_BASELINE_NICE:-10}" -p "$pid" > /dev/null 2>&1 || true
}

# early_baseline_reuse <approved commands file> <out tsv> <log> -- 0 with the baseline written, or 1 to run the approved list.
early_baseline_reuse() {
    local commands="$1" out="$2" log="$3" dir="$STATE_DIR/early-baseline" waited=0 pid now
    [[ -e "$dir/started" ]] || return 1
    # Join it if it is still running: it began long before this, and waiting is cheaper than running the suite again.
    pid="$(cat "$dir/pid" 2>/dev/null || true)"
    while [[ ! -e "$dir/done" ]]; do
        if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then break; fi
        if [[ "$waited" == 0 ]]; then echo "Waiting for the baseline started at the beginning of the run (still running)..."; fi
        waited=1
        sleep 2
    done
    if [[ ! -e "$dir/done" || "$(cat "$dir/done")" != 0 ]]; then
        echo "The early baseline did not finish cleanly; recording the approved baseline from scratch."
        return 1
    fi
    now="$(python3 -B "$ROOT/scripts/lib/tree_fingerprint.py" "$PWD" "$dir/commands" 2>/dev/null || true)"
    if [[ -z "$now" || "$now" != "$(cat "$dir/fingerprint")" || "$now" != "$(cat "$dir/fingerprint.after" 2>/dev/null)" ]]; then
        echo "The tree changed after the early baseline started; recording the approved baseline from scratch."
        return 1
    fi
    # Approved commands the early run did not run are run now, and only those.
    local remaining="$dir/remaining" extra="$dir/remaining.tsv"
    python3 -B "$ROOT/scripts/lib/early_baseline.py" remaining "$commands" "$dir/commands" > "$remaining"
    : > "$extra"
    if [[ -s "$remaining" ]]; then
        echo "Approved commands the early baseline did not run (running them now):"
        sed 's/^/  /' "$remaining"
        green_run "$remaining" "$extra" "$dir/remaining.log" "" "" || return 1
    fi
    # The approved order, one row per approved command, from whichever run covered it.
    python3 - "$commands" "$dir/baseline.tsv" "$extra" > "$out" <<'PY' || { : > "$out"; return 1; }
import sys
rows = {}
for source in sys.argv[2:4]:
    for line in open(source, encoding='utf-8'):
        status, _, command = line.rstrip('\n').partition('\t')
        rows[' '.join(command.split())] = (status, command)
for line in open(sys.argv[1], encoding='utf-8'):
    if line.strip():
        status, command = rows[' '.join(line.split())]
        print('%s\t%s' % (status, command))
PY
    { cat "$dir/baseline.log" 2>/dev/null; [[ ! -s "$extra" ]] || cat "$dir/remaining.log" 2>/dev/null; } > "$log"
    echo "Reusing the baseline recorded at the start of the run: $(grep -c . "$out") command(s), $(grep -c . "$remaining") of them run just now."
    return 0
}
