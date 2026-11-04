#!/usr/bin/env bash
# Driver tests for scripts/housekeeping-workflow.sh with stub gh/git/agent.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DRIVER="$ROOT/scripts/housekeeping-workflow.sh"
REALGIT="$(command -v git)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILS=0
N=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok() { echo "ok: $*"; }

STUB="$TMP/stub"; mkdir -p "$STUB"
for prog in gh git; do
    cat > "$STUB/$prog" <<EOF
#!/usr/bin/env bash
echo "$prog \$*" >> "\$STUB_LOG"
if [[ -n "\${STUB_FAIL_MATCH:-}" && "\$*" == *"\$STUB_FAIL_MATCH"* ]]; then echo boom >&2; exit 1; fi
case "\$*" in
  "symbolic-ref "*) echo origin/main ;;
  "merge-base "*) exit "\${STUB_MERGE_RC:-0}" ;;
  "repo view"*|"issue view"*|"label list"*|"worktree list"*|"ls-remote "*|"branch --list"*) printf '%s\n' "\${STUB_VIEW_OUT:-}" ;;
esac
exit 0
EOF
    chmod +x "$STUB/$prog"
done
cat > "$STUB/agent" <<'EOF'
#!/usr/bin/env bash
cat > /dev/null
cat "$STUB_PLAN"
EOF
chmod +x "$STUB/agent"

new_repo() {
    N=$((N + 1))
    R="$TMP/r$N"; LOG="$TMP/log$N"; : > "$LOG"
    mkdir -p "$R/.uncle/workflow"
    echo sentinel > "$R/.uncle/workflow/state"
    (cd "$R" && "$REALGIT" init -q && echo '.uncle/' > .gitignore && "$REALGIT" add .gitignore \
        && "$REALGIT" -c commit.gpgsign=false -c user.email=t@t -c user.name=t commit -q -m init)
    HKD="$R/.uncle/workflow/housekeeping"
}

# run_driver PLAN_FILE APPROVAL_TEXT [VAR=value ...]  (driver under test: $DRV)
DRV="$DRIVER"
run_driver() {
    local plan="$1" ans="$2"; shift 2
    printf '%s\n' "$ans" > "$TMP/ans$N"
    (cd "$R" && env PATH="$STUB:$PATH" UNCLE_PROJECT_ROOT="$R" HK_ROOT="$ROOT" STUB_LOG="$LOG" STUB_PLAN="$plan" \
        WORKFLOW_AGENT_CMD_HOUSEKEEPING_PLAN="$STUB/agent" HOUSEKEEPING_APPROVAL_FILE="$TMP/ans$N" \
        "$@" bash "$DRV" "rename scratch repo X to Y" > "$TMP/out$N" 2>&1)
    RC=$?
}
ran() { grep -q -- "$1" "$LOG"; }
lock_free() {
    python3 -I -c 'import fcntl,sys; f=open(sys.argv[1],"a+"); fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)' \
        "$R/.uncle/workflow/driver.lock" 2>/dev/null
}
tree_untouched() {
    [[ "$(cat "$R/.uncle/workflow/state")" == sentinel ]] \
        && [[ -z "$(ls -A "$R/.uncle/workflow" | grep -v -e '^housekeeping$' -e '^driver.lock$' -e '^state$')" ]] \
        && [[ -z "$(cd "$R" && "$REALGIT" status --porcelain)" ]]
}

V_REPO='"verify":{"argv":["gh","repo","view","--json","name","--jq",".name"],"expect":"X"}'
op_rename() { printf '{"id":"%s","op":"repo-rename","argv":["gh","repo","rename","new-name","--yes"],"expected":"ok",%s}' "$1" "$V_REPO"; }
op_close() { printf '{"id":"%s","op":"issue-triage","argv":["gh","issue","close","%s"],"expected":"ok","verify":{"argv":["gh","issue","view","%s","--json","labels,state"],"expect":"X"}}' "$1" "$2" "$2"; }
plan() { printf '{"ops":[%s]}' "$1" > "$TMP/plan$N.json"; PLAN="$TMP/plan$N.json"; }

# 1. approve + verify
new_repo; plan "$(op_rename 1)"
run_driver "$PLAN" y STUB_VIEW_OUT=X
[[ $RC -eq 0 ]] && ran 'gh repo rename new-name' && ran 'gh repo view' && grep -q VERIFIED "$HKD/REPORT.md" \
    && tree_untouched && lock_free && ok approve-verify || fail "approve-verify rc=$RC"

# 2. decline
new_repo; plan "$(op_rename 1)"
run_driver "$PLAN" n STUB_VIEW_OUT=X
[[ $RC -eq 0 ]] && ! ran 'repo rename' && tree_untouched && lock_free && ok decline || fail "decline rc=$RC"

# 3. unattended
new_repo; plan "$(op_rename 1)"
run_driver "$PLAN" n STUB_VIEW_OUT=X UNCLE_HOUSEKEEPING_UNATTENDED=1
[[ $RC -eq 0 ]] && ran 'repo rename' && grep -q unattended "$HKD/run.log" && ok unattended || fail "unattended rc=$RC"

# 4. policy refusal (floor) in attended and unattended, nothing executes
for env_ in A=1 UNCLE_HOUSEKEEPING_UNATTENDED=1; do
    new_repo; plan "$(printf '{"id":"1","op":"repo-rename","argv":["gh","repo","delete","x","--yes"],"expected":"ok",%s}' "$V_REPO")"
    run_driver "$PLAN" y "$env_" STUB_VIEW_OUT=X
    [[ $RC -eq 1 ]] && [[ ! -s "$LOG" ]] && lock_free && tree_untouched && ok "policy-refusal ($env_)" || fail "policy-refusal $env_ rc=$RC"
done

# 5. schema refusals
check_refused() { # name plan-json
    new_repo; printf '%s' "$2" > "$TMP/plan$N.json"
    run_driver "$TMP/plan$N.json" y STUB_VIEW_OUT=X
    [[ $RC -eq 1 ]] && [[ ! -s "$LOG" ]] && lock_free && ok "refused: $1" || fail "refused: $1 rc=$RC"
}
check_refused invalid-json 'not json {'
check_refused zero-ops '{"ops":[]}'
check_refused duplicate-ids "{\"ops\":[$(op_close 1 5),$(op_close 1 6)]}"
for k in id op argv expected verify; do
    check_refused "missing-$k" "$(python3 -I -c 'import json,sys; o=json.loads(sys.argv[1]); del o[sys.argv[2]]; print(json.dumps({"ops":[o]}))' "$(op_rename 1)" "$k")"
done
check_refused verify-argv-not-template '{"ops":[{"id":"1","op":"repo-rename","argv":["gh","repo","rename","new-name","--yes"],"expected":"ok","verify":{"argv":["gh","repo","delete","x"],"expect":"X"}}]}'
check_refused mutating-verify-argv '{"ops":[{"id":"1","op":"issue-triage","argv":["gh","issue","close","5"],"expected":"ok","verify":{"argv":["gh","issue","close","5"],"expect":"X"}}]}'

# 6. mid-run failure: op1 ok, op2 fails, op3 never runs
new_repo; plan "$(op_close 1 5),$(op_close 2 6),$(op_close 3 7)"
run_driver "$PLAN" y STUB_VIEW_OUT=X STUB_FAIL_MATCH="issue close 6"
st1="$(awk -F'\t' '$1==1{print $2}' "$HKD/ops.status")"; st3="$(awk -F'\t' '$1==3{print $2}' "$HKD/ops.status")"
[[ $RC -eq 1 ]] && ! ran 'issue close 7' && [[ "$st1" == VERIFIED && "$st3" == NOT_VERIFIED ]] && ran 'issue view 5' \
    && lock_free && ok mid-run-failure || fail "mid-run-failure rc=$RC st1=$st1 st3=$st3"

# 7. verify output mismatch (exact string)
new_repo; plan "$(op_rename 1)"
run_driver "$PLAN" y STUB_VIEW_OUT="X "
st1="$(awk -F'\t' '$1==1{print $2}' "$HKD/ops.status")"
[[ $RC -eq 1 ]] && ran 'repo rename' && [[ "$st1" == VERIFY_FAILED ]] && grep -q VERIFY_FAILED "$HKD/REPORT.md" \
    && ok verify-mismatch || fail "verify-mismatch rc=$RC status=$st1"
new_repo; plan "$(op_rename 1)"
run_driver "$PLAN" y STUB_VIEW_OUT=X
st1="$(awk -F'\t' '$1==1{print $2}' "$HKD/ops.status")"
[[ $RC -eq 0 ]] && [[ "$st1" == VERIFIED ]] && ok verify-match-control || fail "verify-match-control rc=$RC status=$st1"

# 8. plan.checked.json mutated between approval and execute
new_repo; plan "$(op_rename 1)"; mkfifo "$TMP/fifo$N"
( until grep -q 'Run these commands' "$TMP/out$N" 2>/dev/null; do sleep 0.1; done; echo ' ' >> "$HKD/plan.checked.json"; echo y > "$TMP/fifo$N" ) &
writer=$!
(cd "$R" && env PATH="$STUB:$PATH" UNCLE_PROJECT_ROOT="$R" HK_ROOT="$ROOT" STUB_LOG="$LOG" STUB_PLAN="$PLAN" \
    WORKFLOW_AGENT_CMD_HOUSEKEEPING_PLAN="$STUB/agent" HOUSEKEEPING_APPROVAL_FILE="$TMP/fifo$N" \
    bash "$DRV" "rename scratch repo X to Y" > "$TMP/out$N" 2>&1); RC=$?
wait "$writer" 2>/dev/null
[[ $RC -eq 1 ]] && [[ ! -s "$LOG" ]] && lock_free && ok tamper-refused || fail "tamper rc=$RC"

# 9. control characters are escaped in the display
new_repo; plan "$(printf '{"id":"1","op":"issue-triage","argv":["gh","issue","comment","5","--body","hi\\u001b[31mred\\nforged"],"expected":"ok","verify":{"argv":["gh","issue","view","5","--json","labels,state"],"expect":"X"}}')"
run_driver "$PLAN" n STUB_VIEW_OUT=X
if grep -q $'\x1b' "$TMP/out$N"; then fail "raw ESC in display"
elif grep -q '\\x1b' "$TMP/out$N" && grep -q '\\n' "$TMP/out$N"; then ok control-chars-escaped
else fail "control chars not escaped (rc=$RC): $(head -c 300 "$TMP/out$N")"; fi

# 10. remote delete of an unmerged branch fails the execute-time merged check
new_repo; plan '{"id":"1","op":"branch-delete-merged","argv":["git","push","origin","--delete","feature"],"expected":"ok","verify":{"argv":["git","ls-remote","--heads","origin","feature"],"expect":""}}'
run_driver "$PLAN" y STUB_MERGE_RC=1
[[ $RC -eq 1 ]] && ! ran 'push origin --delete' && ran 'merge-base --is-ancestor' && ok remote-delete-unmerged || fail "remote-delete-unmerged rc=$RC"

# 11. another holder of driver.lock: refused, nothing runs; lock free afterwards
new_repo; plan "$(op_rename 1)"
python3 -I -c 'import fcntl,sys,time; f=open(sys.argv[1],"a+"); fcntl.flock(f, fcntl.LOCK_EX); open(sys.argv[2],"w").write("held"); time.sleep(60)' \
    "$R/.uncle/workflow/driver.lock" "$TMP/held$N" &
holder=$!
for _ in $(seq 50); do [[ -s "$TMP/held$N" ]] && break; sleep 0.1; done
run_driver "$PLAN" y STUB_VIEW_OUT=X
kill "$holder" 2>/dev/null; wait "$holder" 2>/dev/null
[[ $RC -eq 1 ]] && [[ ! -s "$LOG" ]] && grep -q 'another workflow' "$TMP/out$N" && lock_free && ok lock-held || fail "lock-held rc=$RC"

# 12. AC-13 static: one execution site, inside hk_run_checked, after the policy gate
src="$(grep -v '^[[:space:]]*#' "$DRIVER")"
sites="$(printf '%s\n' "$src" | grep -c '"${hk_argv\[@\]}"')"
infn="$(awk '/^hk_run_checked\(\)/,/^}/' "$DRIVER" | grep -c '"${hk_argv\[@\]}"')"
[[ "$sites" == 1 && "$infn" == 1 ]] || fail "AC-13: execution sites=$sites in-function=$infn"
printf '%s\n' "$src" | grep -Eq '(^|[^[:alnum:]_])eval([^[:alnum:]_]|$)' && fail "AC-13: eval present"
bad_bc="$(printf '%s\n' "$src" | grep 'bash -c' | grep -v 'agent_cmd' || true)"
[[ -z "$bad_bc" ]] || fail "AC-13: bash -c on non-agent data: $bad_bc"
printf '%s\n' "$src" | grep -q 'P.check_plan(plan, disallow)' || fail "AC-13: check_plan call missing"
gate_ln="$(grep -n 'hk_policy_gate ||' "$DRIVER" | head -1 | cut -d: -f1)"
exec_ln="$(grep -n 'hk_run_checked exec' "$DRIVER" | head -1 | cut -d: -f1)"
[[ -n "$gate_ln" && -n "$exec_ln" && "$gate_ln" -lt "$exec_ln" ]] || fail "AC-13: gate ($gate_ln) not before first exec ($exec_ln)"
[[ $FAILS -eq 0 ]] && ok ac13-static

# 13. AC-13 mutation: without check_plan a refused command executes (suite must detect)
mkdir -p "$TMP/mut/scripts"
sed 's/res = P.check_plan(plan, disallow)/res = True/' "$DRIVER" > "$TMP/mut/scripts/housekeeping-workflow.sh"
if cmp -s "$DRIVER" "$TMP/mut/scripts/housekeeping-workflow.sh"; then
    fail "mutation did not apply"
else
    refused_plan() { plan "$(printf '{"id":"1","op":"repo-rename","argv":["gh","repo","delete","x","--yes"],"expected":"ok",%s}' "$V_REPO")"; }
    new_repo; refused_plan
    DRV="$TMP/mut/scripts/housekeeping-workflow.sh"; run_driver "$PLAN" y STUB_VIEW_OUT=X; DRV="$DRIVER"
    if ran 'repo delete'; then
        new_repo; refused_plan; run_driver "$PLAN" y STUB_VIEW_OUT=X
        ran 'repo delete' && fail "real driver executed refused command" || ok "mutation-detected (mutant executes refused cmd, real driver does not)"
    else
        fail "mutant without check_plan still refused: refusal tests do not exercise check_plan"
    fi
fi

# 14. Defect injection beyond AC-13: each mutant of the driver must be observably worse
#     than the real driver on a scenario that the real driver handles correctly.
mutate() { # name sed-expression  -> writes $TMP/mut/scripts/housekeeping-workflow.sh
    mkdir -p "$TMP/mut/scripts"
    python3 -I -c 'import sys; s=open(sys.argv[1]).read(); assert sys.argv[2] in s, "site not found"; open(sys.argv[4],"w").write(s.replace(sys.argv[2], sys.argv[3]))' \
        "$DRIVER" "$2" "$3" "$TMP/mut/scripts/housekeeping-workflow.sh" || { fail "mutation site missing: $1"; return 1; }
}

# 14a. hash re-check removed (both places): tampering after approval then executes
if mutate hash-check '"$HK_ALLOWED_HASH" != "$(hk_hash)"' '"$HK_ALLOWED_HASH" != "$HK_ALLOWED_HASH"' \
   && python3 -I -c 'import sys; s=open(sys.argv[1]).read(); old=chr(34)+"$(hk_hash)"+chr(34)+" != "+chr(34)+"$HK_APPROVED_HASH"+chr(34); assert old in s; open(sys.argv[1],"w").write(s.replace(old, chr(34)+"x"+chr(34)+" != "+chr(34)+"x"+chr(34)))' "$TMP/mut/scripts/housekeeping-workflow.sh"; then
    new_repo; plan "$(op_rename 1)"; mkfifo "$TMP/fifo$N"
    ( until grep -q 'Run these commands' "$TMP/out$N" 2>/dev/null; do sleep 0.1; done; echo ' ' >> "$HKD/plan.checked.json"; echo y > "$TMP/fifo$N" ) &
    writer=$!
    (cd "$R" && env PATH="$STUB:$PATH" UNCLE_PROJECT_ROOT="$R" HK_ROOT="$ROOT" STUB_LOG="$LOG" STUB_PLAN="$PLAN" \
        WORKFLOW_AGENT_CMD_HOUSEKEEPING_PLAN="$STUB/agent" HOUSEKEEPING_APPROVAL_FILE="$TMP/fifo$N" \
        bash "$TMP/mut/scripts/housekeeping-workflow.sh" "rename scratch repo X to Y" > "$TMP/out$N" 2>&1)
    wait "$writer" 2>/dev/null
    ran 'repo rename' && ok mutation-detected-hash-check || fail "mutant without hash check still refused tampered plan"
fi

# 14b. execute-time merged check removed: an unmerged remote branch gets deleted
if mutate merged-check 'if ! hk_merged_check "${hk_argv[${#hk_argv[@]}-1]}"; then' 'if false; then'; then
    new_repo; plan '{"id":"1","op":"branch-delete-merged","argv":["git","push","origin","--delete","feature"],"expected":"ok","verify":{"argv":["git","ls-remote","--heads","origin","feature"],"expect":""}}'
    DRV="$TMP/mut/scripts/housekeeping-workflow.sh"; run_driver "$PLAN" y STUB_MERGE_RC=1; DRV="$DRIVER"
    ran 'push origin --delete' && ok mutation-detected-merged-check || fail "mutant without merged check still refused unmerged delete"
fi

# 14c. policy refusal of the default branch for remote delete (real driver, control for 14b)
new_repo; plan '{"id":"1","op":"branch-delete-merged","argv":["git","push","origin","--delete","main"],"expected":"ok","verify":{"argv":["git","ls-remote","--heads","origin","main"],"expect":""}}'
run_driver "$PLAN" y STUB_MERGE_RC=0
[[ $RC -eq 1 ]] && ! ran 'push origin --delete' && ok remote-delete-default-branch-refused || fail "remote-delete-default-branch rc=$RC"


[[ $FAILS -eq 0 ]] && { echo "housekeeping-workflow-test: all passed"; exit 0; }
echo "housekeeping-workflow-test: $FAILS failure(s)" >&2
exit 1
