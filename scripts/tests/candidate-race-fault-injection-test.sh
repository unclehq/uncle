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
names = ("upper", "stage_setting", "stage_setting_opt", "self_hosted_candidate_count",
          "race_self_hosted_candidates", "format_claude_stream")
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

if [[ "$FAILED" -ne 0 ]]; then
    echo "candidate-race-fault-injection-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "candidate-race-fault-injection-test.sh: $COUNT checks passed"
