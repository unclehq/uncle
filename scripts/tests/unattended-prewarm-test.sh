#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
cd "$temp"

fake="$temp/claude"
marker="$temp/started"
cat > "$fake" <<'EOF'
#!/usr/bin/env python3
import os, pathlib, sys
pathlib.Path(os.environ['PREWARM_MARKER']).write_text('started')
for _ in sys.stdin:
    pass
EOF
chmod +x "$fake"

# Load just the transition/prewarm helpers.  The real driver has already
# loaded its configuration functions by the time it can call set_state.
sed -n '/^# Map state-machine destinations/,/^get_state() {/p' "$ROOT/scripts/stagegate.sh" \
    | sed '$d' > "$temp/helpers.sh"

UNATTENDED=0
UNCLE_RUNNER_REUSE=1
UNCLE_RUNNER_POOL_OWNER_PID=$$
STATE_FILE="$temp/state"
ROOT="$ROOT"
export UNCLE_RUNNER_POOL_OWNER_PID
export WORKFLOW_CLAUDE_CMD="$fake"
export PREWARM_MARKER="$marker"
stage_runner_config_name() { printf '%s\n' "$1"; }
uncle_resolve_stage_runner() { UNCLE_RESOLVED_RUNNER=claude; }
stage_command_overridden() { return 1; }
stage_agent_cmd() { printf '%s\n' "$fake"; }
stage_model() { printf '%s\n' fake-model; }
stage_effort() { printf '%s\n' low; }
stage_turns() { printf '%s\n' 40; }
stage_tools() { printf '%s\n' Read,Write; }
# shellcheck disable=SC1090
source "$temp/helpers.sh"

set_state PROJECT_PLAN
sleep .2
[[ ! -e "$marker" ]] || { echo 'attended transition unexpectedly prewarmed a runner' >&2; exit 1; }

UNATTENDED=1
set_state PROJECT_PLAN
for _ in {1..40}; do
    [[ -e "$marker" ]] && break
    sleep .05
done
[[ -e "$marker" ]] || { echo 'unattended transition did not prewarm its runner' >&2; exit 1; }
[[ "$(<"$STATE_FILE")" == PROJECT_PLAN ]]

echo 'unattended prewarm tests passed'

# The change-workflow has its own state machine and must use the same
# unattended-only behavior rather than inheriting the application driver's
# helper by accident.
rm -f "$marker"
sed -n '/^# Warm only destinations/,/^get_state() {/p' "$ROOT/scripts/change-workflow.sh" \
    | sed '$d' > "$temp/change-helpers.sh"
MODEL_CHANGE_PLAN=fake-model
MODEL_UPDATED_PLAN=fake-model
MODEL_IMPLEMENT=fake-model
MODEL_EXECUTE=fake-model
EFFORT_UPDATED_PLAN=low
EFFORT_EXECUTE=low
BUDGET_CHANGE_PLAN=1
BUDGET_UPDATED_PLAN=1
BUDGET_IMPLEMENT=1
BUDGET_EXECUTE=1
CLAUDE_TOOLS=Read,Write
stage_model_for() { printf '%s\n' "$2"; }
stage_effort_for() { printf '%s\n' low; }
current_issue() { printf '%s\n' 123; }
state_write() { printf '%s\n' "$2" > "$1"; }
# shellcheck disable=SC1090
source "$temp/change-helpers.sh"
UNATTENDED=0
set_state PLAN
sleep .2
[[ ! -e "$marker" ]] || { echo 'attended change transition unexpectedly prewarmed a runner' >&2; exit 1; }
UNATTENDED=1
set_state PLAN
for _ in {1..40}; do
    [[ -e "$marker" ]] && break
    sleep .05
done
[[ -e "$marker" ]] || { echo 'unattended change transition did not prewarm its runner' >&2; exit 1; }

echo 'change unattended prewarm tests passed'
