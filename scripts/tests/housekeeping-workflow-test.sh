#!/usr/bin/env bash
# Driver tests for scripts/housekeeping-workflow.sh with a stub agent.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DRV="$ROOT/scripts/housekeeping-workflow.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILS=0; N=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok() { echo "ok: $*"; }

cat > "$TMP/agent" <<'EOS'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$STUB_ARGS"
cat > "$STUB_PROMPT"
echo "agent says done"
exit "${STUB_RC:-0}"
EOS
chmod +x "$TMP/agent"

# run NAME [ENV=val ...] -- driver args ; sets R (repo), OUT, RC
run() {
    N=$((N + 1)); R="$TMP/r$N"; mkdir -p "$R/.uncle"
    local envs=()
    while [[ "$1" != -- ]]; do envs+=("$1"); shift; done; shift
    OUT="$(cd "$R" && env UNCLE_PROJECT_ROOT="$R" UNCLE_CONFIG="$R/.uncle/config" \
        WORKFLOW_AGENT_CMD_HOUSEKEEPING="$TMP/agent" STUB_ARGS="$R/args" STUB_PROMPT="$R/prompt" \
        ${envs[@]+"${envs[@]}"} "$DRV" "$@" 2>&1 < /dev/null)"
    RC=$?
}

run -- --unattended "tidy branches"
[[ $RC == 0 ]] && ok "unattended run succeeds" || fail "rc=$RC $OUT"
grep -q 'tidy branches' "$R/prompt" && ok "request reaches agent" || fail "request missing"
grep -q -- '--disallowedTools' "$R/args" && ok "deny list passed" || fail "no deny list"
grep -q 'Bash(gh repo delete:\*)' "$R/args" && ok "floor denied" || fail "floor missing"
grep -q 'Bash(sudo:\*)' "$R/args" && ok "sudo denied" || fail "sudo missing"
grep -q 'Bash(git branch -D:\*)' "$R/args" && ok "default disallow denied" || fail "default list missing"
grep -qx 'sonnet' "$R/args" && grep -qx 'low' "$R/args" && ok "supervisor default model/effort" || fail "model/effort"
grep -q 'agent says done' "$R/.uncle/workflow/housekeeping/REPORT.md" && ok "report written" || fail "report"

run -- --unattended "x"
printf 'housekeeping.disallow ["git stash drop"]\nsupervision.model opus\nsupervision.effort high\n' > "$R/.uncle/config"
rm -rf "$R/.uncle/workflow"
OUT="$(cd "$R" && env UNCLE_PROJECT_ROOT="$R" UNCLE_CONFIG="$R/.uncle/config" WORKFLOW_AGENT_CMD_HOUSEKEEPING="$TMP/agent" \
    STUB_ARGS="$R/args" STUB_PROMPT="$R/prompt" "$DRV" --unattended x 2>&1 < /dev/null)"
grep -q 'Bash(git stash drop:\*)' "$R/args" && ok "configured pattern denied" || fail "configured pattern"
grep -qx 'opus' "$R/args" && grep -qx 'high' "$R/args" && ok "supervisor model/effort used" || fail "supervisor model"

run STUB_RC=3 -- --unattended "x"
[[ $RC == 1 ]] && grep -q FAILED "$R/.uncle/workflow/housekeeping/state" && ok "agent failure -> exit 1" || fail "failure rc=$RC"

echo n > "$TMP/no"
run HOUSEKEEPING_APPROVAL_FILE="$TMP/no" UNCLE_ATTENDED=1 UNCLE_STDIN_TTY=1 -- "x"
[[ $RC == 0 && ! -e "$R/args" ]] && ok "attended decline runs nothing" || fail "decline rc=$RC"

run -- --unattended "   "
[[ $RC == 1 ]] && ok "empty request refused" || fail "empty rc=$RC"

N=$((N + 1)); R="$TMP/r$N"; mkdir -p "$R/.uncle"
printf 'supervision.runner codex\n' > "$R/.uncle/config"
OUT="$(cd "$R" && env UNCLE_PROJECT_ROOT="$R" UNCLE_CONFIG="$R/.uncle/config" "$DRV" --unattended x 2>&1 < /dev/null)"; RC=$?
[[ $RC == 1 && "$OUT" == *"needs claude"* ]] && ok "non-claude supervisor runner refused" || fail "codex rc=$RC $OUT"

((FAILS == 0)) && echo "all passed" || { echo "$FAILS failed"; exit 1; }
