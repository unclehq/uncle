#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for per-stage runners in both drivers.
# Hermetic: stub agent/reviewer commands under a temp directory, no real calls.
#
# Each stage resolves its own command and its own model. The property that
# matters most is the empty model: a stage configured with no model must be
# invoked with no --model flag at all, because claude, kimi, and codex have
# their own defaults and only cline needs to be told. A stage that names a
# model must still get it.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
COUNT=0

fail() {
    echo "FAIL: $1"
    FAILED=$((FAILED + 1))
}

check_eq() {
    local name="$1" expected="$2" actual="$3"
    COUNT=$((COUNT + 1))
    if [[ "$actual" != "$expected" ]]; then
        fail "$name — expected '$expected', got '$actual'"
    fi
}

check_contains() {
    local name="$1" needle="$2" hay="$3"
    COUNT=$((COUNT + 1))
    case "$hay" in
        *"$needle"*) ;;
        *) fail "$name — '$needle' not in: $hay" ;;
    esac
}

check_absent() {
    local name="$1" needle="$2" hay="$3"
    COUNT=$((COUNT + 1))
    case "$hay" in
        *"$needle"*) fail "$name — '$needle' should not be in: $hay" ;;
    esac
}

# --- stubs ------------------------------------------------------------------

make_agent_stub() {
    local path="$1" tag="$2"
    cat > "$path" <<EOF
#!/usr/bin/env bash
printf '$tag %s\n' "\$*" >> "\$ARGV_LOG"
cat > /dev/null
printf '# artifact\n' > REQUIREMENTS_INTERPRETATION.md
printf '# baseline\n\n## 8. Verification commands\n\n\`\`\`sh\ntrue\n\`\`\`\n' > BASELINE_REPORT.md
printf '# spec\n' > CHANGE_SPEC.md
echo '{"type":"result","subtype":"success","is_error":false,"num_turns":1,"duration_ms":1,"total_cost_usd":0}'
EOF
    chmod +x "$path"
}

make_agent_stub "$TMP/agent-global" "GLOBAL"
make_agent_stub "$TMP/agent-stage" "STAGE"

# --- stagegate: the stage's own command wins, and an empty model is honored -

PROJ="$TMP/newapp"
mkdir -p "$PROJ"
printf '# Project brief\n\n## Summary\nToy.\n' > "$PROJ/REQUIREMENTS.md"
ARGV="$TMP/sg.argv"
: > "$ARGV"

out="$(cd "$PROJ" && echo n | ARGV_LOG="$ARGV" \
    UNCLE_PROJECT_ROOT="$PROJ" \
    WORKFLOW_AGENT_CMD="$TMP/agent-global" \
    WORKFLOW_AGENT_CMD_REQUIREMENTS="$TMP/agent-stage" \
    WORKFLOW_MODEL_REQUIREMENTS= \
    WORKFLOW_EFFORT_REQUIREMENTS=low \
    WORKFLOW_SPECULATE=0 \
    bash "$ROOT/scripts/stagegate.sh" 2>&1)"

argv="$(cat "$ARGV")"
check_contains "stagegate: stage command ran" "STAGE " "$argv"
check_absent "stagegate: global command did not run" "GLOBAL " "$argv"
check_absent "stagegate: empty model emits no --model" "--model" "$argv"
check_contains "stagegate: stage effort is used" "--effort low" "$argv"
check_contains "stagegate: banner names the runner default" "(runner default)" "$out"

# A model that is set is still passed.
rm -rf "$PROJ/.uncle" "$PROJ/REQUIREMENTS_INTERPRETATION.md"
: > "$ARGV"
(cd "$PROJ" && echo n | ARGV_LOG="$ARGV" \
    UNCLE_PROJECT_ROOT="$PROJ" \
    WORKFLOW_AGENT_CMD="$TMP/agent-global" \
    WORKFLOW_MODEL_REQUIREMENTS=cline-pass/kimi-k3 \
    WORKFLOW_SPECULATE=0 \
    bash "$ROOT/scripts/stagegate.sh" > /dev/null 2>&1) || true
check_contains "stagegate: a set model is passed" \
    "--model cline-pass/kimi-k3" "$(cat "$ARGV")"

# --- change-workflow: same two properties ----------------------------------

if command -v git > /dev/null 2>&1; then
    CPROJ="$TMP/change"
    mkdir -p "$CPROJ"
    (
        cd "$CPROJ"
        git init -q .
        git config user.email t@e.st
        git config user.name t
        echo hi > app.txt
        git add -A
        git commit -qm init
    )
    printf '## Summary\nChange it.\n\n## Motivation\nTesting.\n' > "$CPROJ/CHANGE_REQUEST.md"
    ARGV="$TMP/cw.argv"
    : > "$ARGV"

    out="$(cd "$CPROJ" && echo n | ARGV_LOG="$ARGV" \
        UNCLE_PROJECT_ROOT="$CPROJ" \
        WORKFLOW_AGENT_CMD="$TMP/agent-global" \
        WORKFLOW_AGENT_CMD_BASELINE="$TMP/agent-stage" \
        WORKFLOW_MODEL_BASELINE= \
        WORKFLOW_EFFORT_BASELINE=high \
        WORKFLOW_MODEL_CHANGE_SPEC=cline-pass/glm-5.3 \
        WORKFLOW_SPECULATE=0 WORKFLOW_CLOSE_ISSUE=0 \
        bash "$ROOT/scripts/change-workflow.sh" 2>&1)"

    baseline_argv="$(grep '^STAGE ' "$ARGV" || true)"
    spec_argv="$(grep '^GLOBAL ' "$ARGV" || true)"
    check_contains "change: baseline ran on its own command" "--effort high" "$baseline_argv"
    check_absent "change: baseline empty model emits no --model" "--model" "$baseline_argv"
    check_contains "change: change-spec ran on the global command" \
        "--model cline-pass/glm-5.3" "$spec_argv"
else
    echo "NOTE skipped change-workflow cases: git is not available"
fi

# --- the config file is read per stage, not snapshotted at launch ----------

# A run stops at four gates, and that is when an operator changes their mind
# about the next stage. The driver must therefore read .uncle/config when the
# stage starts, not keep what it was launched with.

CPROJ2="$TMP/reread"
mkdir -p "$CPROJ2/.uncle"
printf '# Project brief\n\n## Summary\nToy.\n' > "$CPROJ2/REQUIREMENTS.md"
ARGV="$TMP/reread.argv"

run_reread() {
    : > "$ARGV"
    rm -rf "$CPROJ2/.uncle/workspace" "$CPROJ2/REQUIREMENTS_INTERPRETATION.md"
    (cd "$CPROJ2" && echo n | ARGV_LOG="$ARGV" \
        UNCLE_PROJECT_ROOT="$CPROJ2" UNCLE_CONFIG="$CPROJ2/.uncle/config" \
        WORKFLOW_AGENT_CMD="$TMP/agent-global" \
        WORKFLOW_SPECULATE=0 \
        bash "$ROOT/scripts/stagegate.sh" > /dev/null 2>&1) || true
    cat "$ARGV"
}

printf 'requirements.runner cline\nrequirements.model cline-pass/kimi-k3\nrequirements.effort high\n' \
    > "$CPROJ2/.uncle/config"
argv="$(run_reread)"
check_contains "config: model comes from the file" "--model cline-pass/kimi-k3" "$argv"
check_contains "config: effort comes from the file" "--effort high" "$argv"

# The same driver, the same command line, a different config file.
printf 'requirements.runner cline\nrequirements.model cline-pass/glm-5.3\nrequirements.effort low\n' \
    > "$CPROJ2/.uncle/config"
argv="$(run_reread)"
check_contains "config: an edited model is picked up" "--model cline-pass/glm-5.3" "$argv"
check_contains "config: an edited effort is picked up" "--effort low" "$argv"
check_absent "config: the old model is gone" "cline-pass/kimi-k3" "$argv"

# A non-cline runner in the file means no model flag at all.
printf 'requirements.runner kimi\nrequirements.effort medium\n' > "$CPROJ2/.uncle/config"
argv="$(run_reread)"
check_absent "config: a kimi stage gets no --model" "--model" "$argv"

# An explicit variable still outranks the file.
printf 'requirements.runner cline\nrequirements.model cline-pass/kimi-k3\n' \
    > "$CPROJ2/.uncle/config"
: > "$ARGV"
rm -rf "$CPROJ2/.uncle/workspace" "$CPROJ2/REQUIREMENTS_INTERPRETATION.md"
(cd "$CPROJ2" && echo n | ARGV_LOG="$ARGV" \
    UNCLE_PROJECT_ROOT="$CPROJ2" UNCLE_CONFIG="$CPROJ2/.uncle/config" \
    WORKFLOW_AGENT_CMD="$TMP/agent-global" \
    WORKFLOW_MODEL_REQUIREMENTS=vendor/override \
    WORKFLOW_SPECULATE=0 \
    bash "$ROOT/scripts/stagegate.sh" > /dev/null 2>&1) || true
check_contains "env overrides the config file" "--model vendor/override" "$(cat "$ARGV")"

# And the command the operator passed explicitly is the one that runs.
check_contains "explicit WORKFLOW_AGENT_CMD wins over the file's runner" \
    "GLOBAL " "$(cat "$ARGV")"

# --- report -----------------------------------------------------------------

# Reviewer effort/model settings must reach the actual command as well.
. "$ROOT/scripts/lib/sha256.sh"
RPROJ="$TMP/reviewer-settings"
mkdir -p "$RPROJ/.uncle/workspace/approvals"
printf 'plan\n' > "$RPROJ/PROJECT_PLAN.md"
hash_file "$RPROJ/PROJECT_PLAN.md" > "$RPROJ/.uncle/workspace/approvals/PROJECT_PLAN.sha256"
cat > "$TMP/config-reviewer" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" > "$ARGV_LOG"
while [[ $# -gt 0 ]]; do
    if [[ "$1" == --output-last-message ]]; then printf 'review\n' > "$2"; break; fi
    shift
done
EOF
chmod +x "$TMP/config-reviewer"
printf 'adversarial-review.runner cline\nadversarial-review.model vendor/reviewer\nadversarial-review.effort low\n' > "$RPROJ/.uncle/config"
printf 'ADVERSARIAL_REVIEW\n' > "$RPROJ/.uncle/workspace/state"
UNCLE_PROJECT_ROOT="$RPROJ" WORKFLOW_REVIEWER_CMD="$TMP/config-reviewer" \
    ARGV_LOG="$TMP/reviewer.argv" WORKFLOW_SPECULATE=0 bash "$ROOT/scripts/stagegate.sh" < /dev/null > /dev/null
argv="$(cat "$TMP/reviewer.argv")"
check_contains 'reviewer: configured model is used' '-m vendor/reviewer' "$argv"
check_contains 'reviewer: configured effort is used' 'model_reasoning_effort=low' "$argv"
check_contains 'reviewer: sandbox is retained' '--sandbox read-only' "$argv"
printf 'adversarial-review.runner codex\nadversarial-review.effort high\n' > "$RPROJ/.uncle/config"
printf 'ADVERSARIAL_REVIEW\n' > "$RPROJ/.uncle/workspace/state"
UNCLE_PROJECT_ROOT="$RPROJ" WORKFLOW_REVIEWER_CMD="$TMP/config-reviewer" \
    ARGV_LOG="$TMP/reviewer.argv" WORKFLOW_SPECULATE=0 WORKFLOW_EFFORT_ADVERSARIAL_REVIEW=low \
    bash "$ROOT/scripts/stagegate.sh" < /dev/null > /dev/null
argv="$(cat "$TMP/reviewer.argv")"
check_contains 'reviewer: explicit effort wins' 'model_reasoning_effort=low' "$argv"
check_absent 'reviewer: default model is not invented' '-m vendor/reviewer' "$argv"

if [[ "$FAILED" -ne 0 ]]; then
    echo "stage-runner-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "stage-runner-test.sh: $COUNT checks passed"
