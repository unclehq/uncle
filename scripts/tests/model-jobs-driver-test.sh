#!/usr/bin/env bash
# No Git repositories, model servers, or external agents are used here.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
. "$ROOT/scripts/lib/stage-config.sh"
. "$ROOT/scripts/lib/model-jobs.sh"
export UNCLE_CONFIG="$TMP/config"
unset WORKFLOW_SELF_HOSTED_STAGE_JOBS
runner=self-hosted
stage_uses_self_hosted() { [[ "$runner" == self-hosted ]]; }
[[ "$(workflow_model_jobs project-plan)" == 4 ]]
printf 'self-hosted.stage-jobs 2\n' > "$UNCLE_CONFIG"
[[ "$(workflow_model_jobs project-plan)" == 2 ]]
[[ "$(WORKFLOW_SELF_HOSTED_STAGE_JOBS=3 workflow_model_jobs updated-plan)" == 3 ]]
for value in 0 9 -1 02 bogus; do
    [[ "$(WORKFLOW_SELF_HOSTED_STAGE_JOBS="$value" workflow_model_jobs project-plan 2> "$TMP/invalid")" == 4 ]]
    [[ -s "$TMP/invalid" ]]
done
for runner in claude codex kimi cline; do
    [[ "$(WORKFLOW_SELF_HOSTED_STAGE_JOBS=2 workflow_model_jobs project-plan)" == 0 ]]
done
runner=self-hosted

# A free slot must be reusable while the oldest worker is still alive.
sleep 1 & slow=$!
sleep 0.05 & fast=$!
workflow_model_slot 2 "$slow" "$fast"
kill -0 "$slow"
wait "$slow"; wait "$fast"
(
    sleep 0.05
    touch "$TMP/drained"
) &
workflow_model_drain 2 "$!"
[[ -e "$TMP/drained" ]]

awk '/^(project_plan_section_settle|run_project_plan_sections_bounded)\(\) \{/,/^}/' "$ROOT/scripts/stagegate.sh" > "$TMP/functions.sh"
. "$TMP/functions.sh"
STATE_DIR="$TMP/state"; LOG_DIR="$STATE_DIR/logs"
mkdir -p "$LOG_DIR"
project_plan_section_run() {
    local name="$1" directory="$2"
    printf '%s start\n' "$name" >> "$STATE_DIR/events"
    # A slow early worker must not impose a barrier on outline dependents.
    # behaviors stays busy until a dependent has started (up to 10 s), so the
    # ordering check below does not depend on how fast the machine is.
    if [[ "$name" == behaviors ]]; then
        local waited=0
        while [[ "$waited" -lt 200 ]] && ! grep -qx 'design start' "$STATE_DIR/events"; do
            sleep 0.05; waited=$((waited + 1))
        done
    else
        sleep 0.05
    fi
    if [[ "$CASE:$name" == fail:outline ]]; then
        printf '%s end\n' "$name" >> "$STATE_DIR/events"
        return 1
    fi
    if [[ "$CASE:$name" == retry:commands && ! -e "$directory/retried" ]]; then
        touch "$directory/retried"
    else
        touch "$directory/$name.md"
    fi
    printf '%s end\n' "$name" >> "$STATE_DIR/events"
}
project_plan_section_finish() { [[ -e "$2/$1.md" ]]; }
for CASE in ok retry fail; do
    for jobs in 1 2 4; do
        directory="$TMP/$CASE-$jobs"; mkdir -p "$directory"
        : > "$STATE_DIR/events"
        status=0
        run_project_plan_sections_bounded "$directory" file "$jobs" > "$STATE_DIR/out" 2>&1 || status=$?
        if [[ "$CASE" == fail ]]; then [[ "$status" == 1 ]]; else [[ "$status" == 0 ]]; fi
        python3 - "$STATE_DIR/events" "$jobs" "$CASE" <<'PY'
import sys
rows = [line.split() for line in open(sys.argv[1])]
limit, case = int(sys.argv[2]), sys.argv[3]
active = set(); peak = 0; done = set(); starts = []
early = {'outline', 'behaviors', 'handling', 'checks', 'decisions', 'restrictions', 'limits', 'bounds'}
for name, action in rows:
    if action == 'start':
        if name not in early: assert 'outline' in done, rows
        active.add(name); starts.append(name); peak = max(peak, len(active))
    else:
        active.remove(name); done.add(name)
assert not active, rows  # failure must drain all its children before fallback
assert peak <= limit, (peak, limit)
if case == 'fail':
    assert set(starts) <= early, starts
else:
    assert len(set(starts)) == 22, starts
    assert starts.count('commands') == (2 if case == 'retry' else 1)
    if limit > 1:
        assert peak > 1
        assert rows.index(['design', 'start']) < rows.index(['behaviors', 'end']), rows
PY
    done
done
printf 'model-jobs-driver-test.sh: all checks passed\n'
