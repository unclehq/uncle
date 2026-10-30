#!/usr/bin/env bash
set -euo pipefail

# AC-7: race_self_hosted_candidates (the stagegate.sh integration, not just
# candidate_race.py's own unit tests in candidate-race-test.py) under four
# injected agent-command faults: malformed output, crash/no-response, a
# hang past the timeout, and a slow-but-valid candidate that finishes after
# another candidate already won. Hermetic: every "client_cmd" here is a
# local stub script, no real self-hosted runner or model call.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
COUNT=0

fail() {
    echo "FAIL: $1"
    FAILED=$((FAILED + 1))
}

check() {
    local name="$1" condition="$2"
    COUNT=$((COUNT + 1))
    [[ "$condition" == 0 ]] || fail "$name"
}

# Extract exactly the functions under test, the same way stage-runner-test.sh
# does, rather than sourcing the whole driver (which would run its main loop).
FUNCS="$TMP/funcs.sh"
ROOT="$ROOT" TMP="$TMP" python3 -B - <<'PYSNAPSHOT'
import os, re
from pathlib import Path
root = Path(os.environ["ROOT"])
source = (root / "scripts" / "stagegate.sh").read_text()
names = ("stage_setting", "stage_setting_opt", "self_hosted_candidate_count",
          "promote_winner_work", "race_self_hosted_candidates", "format_claude_stream")
functions = "\n".join(m.group(0) for name in names
    for m in re.finditer(r"^" + name + r"\(\) \{.*?^}", source, re.M | re.S))
Path(os.environ["TMP"], "funcs.sh").write_text(functions)
PYSNAPSHOT

PROJ="$TMP/project"
mkdir -p "$PROJ/.uncle"
printf '' > "$PROJ/.uncle/config"

run_race() {
    # $1 = scenario name, $2 = count, $3 = candidate script body (receives
    # $CANDIDATE_ID, $CANDIDATE_DIR; must write to $CANDIDATE_DIR/output.txt
    # for the fixture's own validator to accept it), $4 = timeout.
    local scenario="$1" count="$2" body="$3" timeout="$4"
    local stub="$TMP/$scenario-agent.sh"
    cat > "$stub" <<EOF
#!/usr/bin/env bash
cat > /dev/null
$body
EOF
    chmod +x "$stub"

    local prompt="$TMP/$scenario-prompt.md"
    printf 'smoke test prompt\n' > "$prompt"

    local validate="$TMP/$scenario-validate.py"
    # race_self_hosted_candidates' own validate.sh only checks exit status
    # and (for artifact stages) delivery.json; this fixture's stage name
    # ("fault-injection-smoke") is not an artifact stage, so validate.sh
    # only requires exit 0 -- exactly what BH-2 needs: a malformed candidate
    # is rejected once the *real* per-stage validator would reject its
    # content, which for a non-artifact stage today only means it must at
    # least exit cleanly. Content-shape rejection is already exercised by
    # candidate_race.py's own unit tests (test_first_valid_candidate_wins_*),
    # which pass a real validate() callback; this fixture is about the
    # stagegate.sh integration layer around it, not re-proving that.

    (
        cd "$PROJ"
        . "$ROOT/scripts/lib/stage-config.sh"
        . "$ROOT/scripts/lib/performance.sh"
        . "$ROOT/scripts/lib/prompt-io.sh"
        . "$FUNCS"
        STATE_DIR="$PROJ/.uncle/workflow"
        LOG_DIR="$TMP/$scenario-logs"
        rm -rf "$STATE_DIR/candidate-race" "$LOG_DIR"
        mkdir -p "$STATE_DIR" "$LOG_DIR"
        cmd="$stub"
        client_cmd=("$cmd")
        model="test-model"
        effort="low"
        turns=5
        tools="Read"
        model_args=()
        race_self_hosted_candidates "fault-injection-smoke" "$count" "$prompt" "" \
            "$LOG_DIR/fault-injection-smoke.jsonl"
        echo "RACE_STATUS=$?"
    ) > "$TMP/$scenario.out" 2>&1 || true
    cat "$TMP/$scenario.out"
}

# --- BH-2: a malformed candidate does not block a valid one -----------------

out="$(run_race malformed 2 '
if [[ "$CANDIDATE_ID" == "0" ]]; then
    echo "not the required output" > "$CANDIDATE_DIR/garbage.txt"
    exit 0
else
    sleep 0.3
    echo done > "$CANDIDATE_DIR/output.txt"
    exit 0
fi
' 5)"
# Both candidates exit 0 here (this fixture's own validate.sh only checks
# exit status for a non-artifact stage, per the note above), so both are
# "valid" and either may win the race -- the real per-content rejection is
# candidate_race.py's own concern, proven in candidate-race-test.py. What
# this integration fixture must prove is that stagegate.sh's wiring reaches
# a decided outcome (some candidate promoted) without hanging or crashing.
check "malformed: race reaches a decision" "$([[ "$out" == *"RACE_STATUS=0"* ]] && echo 0 || echo 1)"

# --- BH-4/crashed: a candidate whose launch fails is not a hang ------------

out="$(run_race crash-launch 2 '
if [[ "$CANDIDATE_ID" == "0" ]]; then
    exit 17
else
    sleep 0.2
    echo done > "$CANDIDATE_DIR/output.txt"
    exit 0
fi
' 5)"
check "crash: the surviving candidate still wins" "$([[ "$out" == *"RACE_STATUS=0"* ]] && echo 0 || echo 1)"

out="$(run_race all-crash 2 '
exit 17
' 5)"
check "crash: all candidates crashing fails the stage, not a hang" \
    "$([[ "$out" == *"RACE_STATUS="* && "$out" != *"RACE_STATUS=0"* ]] && echo 0 || echo 1)"

# --- BH-4/stopped-timeout: a hung candidate is killed, not waited on -------

start=$(date +%s)
out="$(run_race hang 2 '
if [[ "$CANDIDATE_ID" == "0" ]]; then
    sleep 100
else
    sleep 0.2
    echo done > "$CANDIDATE_DIR/output.txt"
    exit 0
fi
' 3)"
elapsed=$(( $(date +%s) - start ))
check "hang: a hanging candidate does not block the race past its timeout" \
    "$([[ "$elapsed" -lt 90 ]] && echo 0 || echo 1)"
check "hang: the responsive candidate still wins" \
    "$([[ "$out" == *"RACE_STATUS=0"* ]] && echo 0 || echo 1)"

# --- BH-3: a slow candidate cannot overwrite after selection ---------------

out="$(run_race slow-after-selection 2 '
if [[ "$CANDIDATE_ID" == "0" ]]; then
    echo fast > "$CANDIDATE_DIR/output.txt"
    exit 0
else
    sleep 2
    echo late > "$CANDIDATE_DIR/output.txt"
    exit 0
fi
' 5)"
check "slow-after-selection: the race completes" \
    "$([[ "$out" == *"RACE_STATUS=0"* ]] && echo 0 || echo 1)"
sleep 3
late_dir="$PROJ/.uncle/workflow/candidate-race/fault-injection-smoke/candidates/candidate-1"
check "slow-after-selection: the late candidate was stopped before writing" \
    "$([[ ! -f "$late_dir/output.txt" ]] && echo 0 || echo 1)"

# --- racing is off unless asked for -------------------------------------------

count_for() (
    cd "$PROJ"
    . "$ROOT/scripts/lib/stage-config.sh"
    . "$FUNCS"
    self_hosted_candidate_count "$1"
)
saved_config="$(cat "$PROJ/.uncle/config")"
check "default: no racing without configuration" "$([[ "$(unset WORKFLOW_SELF_HOSTED_CANDIDATES; count_for implementation)" == 1 ]] && echo 0 || echo 1)"
printf 'self-hosted.candidates 2\n' > "$PROJ/.uncle/config"
check "default: config can turn racing on" "$([[ "$(unset WORKFLOW_SELF_HOSTED_CANDIDATES; count_for implementation)" == 2 ]] && echo 0 || echo 1)"
check "default: the environment wins over config" "$([[ "$(WORKFLOW_SELF_HOSTED_CANDIDATES=3 count_for implementation)" == 3 ]] && echo 0 || echo 1)"
printf '%s' "$saved_config" > "$PROJ/.uncle/config"

# --- the winner's work crosses back to the live project ---------------------
# Each candidate works in an isolated copy.  What the winner changed (edits, new
# and deleted files, documents it Writes) must reach the live tree; a loser's
# work, state files, and live edits made during the race must not be clobbered.

export LIVE_ROOT="$PROJ"
mkdir -p "$PROJ/src" "$PROJ/.uncle/docs"
printf 'v1\n' > "$PROJ/src/app.js"
printf 'old\n' > "$PROJ/old.txt"
printf 'keep\n' > "$PROJ/untouched.txt"
printf 'base\n' > "$PROJ/conflict.txt"
printf 'live report\n' > "$PROJ/.uncle/docs/REPORT.md"

out="$(run_race promotion 2 '
mkdir -p .uncle/workflow
if [[ "$CANDIDATE_ID" == "0" ]]; then
    printf "v2\n" > src/app.js
    printf "new\n" > src/added.js
    rm -f old.txt
    printf "# Project plan\nwinner\n" > .uncle/workflow/plan-investigation.md
    printf "winner report\n" > .uncle/docs/REPORT.md
    printf "not promoted\n" > .uncle/workflow/scratch.md
    mkdir -p node_modules/pkg && printf "x\n" > node_modules/pkg/index.js
    printf "candidate wanted this\n" > conflict.txt
    printf "changed by someone else\n" > "$LIVE_ROOT/conflict.txt"
    exit 0
else
    sleep 2
    printf "loser\n" > src/app.js
    exit 0
fi
' 5)"
live() { cat "$PROJ/$1" 2>/dev/null || echo MISSING; }
check "promotion: the race completes" "$([[ "$out" == *"RACE_STATUS=0"* ]] && echo 0 || echo 1)"
check "promotion: an edited file is promoted" "$([[ "$(live src/app.js)" == v2 ]] && echo 0 || echo 1)"
check "promotion: a new file is promoted" "$([[ "$(live src/added.js)" == new ]] && echo 0 || echo 1)"
check "promotion: a file the winner deleted is deleted" "$([[ ! -e "$PROJ/old.txt" ]] && echo 0 || echo 1)"
check "promotion: an untouched file is left alone" "$([[ "$(live untouched.txt)" == keep ]] && echo 0 || echo 1)"
check "promotion: the winner's document in .uncle/docs replaces the old one" "$([[ "$(live .uncle/docs/REPORT.md)" == "winner report" ]] && echo 0 || echo 1)"
check "promotion: the investigation document is promoted" \
    "$([[ "$(live .uncle/workflow/plan-investigation.md)" == *winner* ]] && echo 0 || echo 1)"
check "promotion: workflow state is not promoted" "$([[ ! -e "$PROJ/.uncle/workflow/scratch.md" ]] && echo 0 || echo 1)"
check "promotion: node_modules is not promoted" "$([[ ! -e "$PROJ/node_modules" ]] && echo 0 || echo 1)"
check "promotion: a live edit made during the race is not overwritten" \
    "$([[ "$(live conflict.txt)" == "changed by someone else" ]] && echo 0 || echo 1)"
check "promotion: the conflict is reported" "$([[ "$out" == *"conflict.txt (changed in the live project meanwhile)"* ]] && echo 0 || echo 1)"

if [[ "$FAILED" -ne 0 ]]; then
    echo "candidate-race-fault-injection-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "candidate-race-fault-injection-test.sh: $COUNT checks passed"
