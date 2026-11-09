#!/usr/bin/env bash
# Driver exit status: the completion path of change-workflow.sh exits 1 when an
# unattended worktree run's change_pr_complete fails (CLOSE_ISSUE=1), and 0 for
# a non-worktree fixture, an attended run, or CLOSE_ISSUE=0.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT+1)); [[ "$2" == "$3" ]] || { FAILED=$((FAILED+1)); echo "FAIL: $1: expected [$2] got [$3]"; }; }

DRIVER="$ROOT/scripts/change-workflow.sh"
# Extract the completion arm: from the triage_print_actions line preceding the
# Issue 107 comment through the arm's closing `exit 0`.
awk '
  /triage_print_actions "\$STATE_DIR"/ { buf=$0; hold=1; next }
  hold && /Issue 107: no dialog/ { started=1 }
  hold && !started { buf=buf "\n" $0; if ($0 ~ /^            triage_print_actions/) buf=$0; next }
  started { if (!printed) { print buf; printed=1 } print; if ($0 ~ /^            exit [0-9]/) exit }
' "$DRIVER" > "$TMP/arm.sh"
[[ -s "$TMP/arm.sh" ]] || { echo "FAIL: could not extract completion arm"; exit 1; }

git_q() { git -c commit.gpgsign=false -c user.name=t -c user.email=t@t "$@" >/dev/null 2>&1; }

mkrepo() { # $1 dir
    mkdir -p "$1" && ( cd "$1" && git init -q . && echo x > f && git add f && git_q commit --no-gpg-sign -m init ); }
mkdir -p "$TMP/plain-parent"
mkrepo "$TMP/main"
( cd "$TMP/main" && git_q worktree add -b wt "$TMP/wt" )
mkdir -p "$TMP/plain" ; mkrepo "$TMP/plain"

run_case() { # dir unattended close_issue
    local d="$1" un="$2" ci="$3"
    mkdir -p "$d/.uncle/workflow"
    cat > "$TMP/harness.sh" <<HARNESS
. "$ROOT/scripts/lib/change-pr.sh"
PROJECT_ROOT='$d'; STATE_DIR='$d/.uncle/workflow'
UNATTENDED_FILE="\$STATE_DIR/unattended-gates"; : > "\$UNATTENDED_FILE"
LEDGER_FILE="\$STATE_DIR/ledger"; ORIGIN_FILE="\$STATE_DIR/origin"; DIFF_FILE=DIFF
UNATTENDED=$un; CLOSE_ISSUE=$ci; WORKFLOW_CLOSE_ISSUE=$ci; export WORKFLOW_CLOSE_ISSUE
triage_print_actions() { :; }
finished_build_line() { :; }
completed_verdict() { echo READY; }
finished_extras() { :; }
change_pr_extras_print() { :; }
change_pr_complete() { return 1; }
state=complete
LEDGER_FILE=/nonexistent
$(cat "$TMP/arm.sh")
HARNESS
    ( cd "$d" && bash "$TMP/harness.sh" </dev/null >/dev/null 2>&1 ); echo $?
}

check "unattended worktree, CLOSE_ISSUE=1, stub rc 1 -> exit 1" "1" "$(run_case "$TMP/wt" 1 1)"
check "unattended non-worktree, stub rc 1 -> exit 0"            "0" "$(run_case "$TMP/plain" 1 1)"
check "attended worktree, stub rc 1 -> exit 0"                  "0" "$(run_case "$TMP/wt" 0 1)"
check "unattended worktree, CLOSE_ISSUE=0, stub rc 1 -> exit 0" "0" "$(run_case "$TMP/wt" 1 0)"

if (( FAILED )); then echo "change-workflow-exit-status-test: $FAILED of $COUNT failed"; exit 1; fi
echo "change-workflow-exit-status-test: $COUNT passed"
