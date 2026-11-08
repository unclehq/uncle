#!/usr/bin/env bash
# `uncle --audit [BRANCH]` helper: re-run the final audit of a finished change.
#
# Usage: audit-command.sh [BRANCH]     (run from the caller's repository)
#
# Every refusal happens before any state write and leaves state untouched.
# The driver is always run from this install ($ROOT), never from the target
# checkout's copy. Mode travels only through the exported UNCLE_UNATTENDED.
# Exit status is the driver's, except that a driver exit 0 with no readable
# verdict prints 'verdict: UNKNOWN' and exits with the refusal code (AC-2).
#
# bash 3.2 compatible.

set -u

ROOT="$(cd "${BASH_SOURCE[0]%/*}/.." && pwd)"
REFUSE="${UNCLE_REFUSE_CODE:-1}"
. "$ROOT/scripts/lib/state.sh"
. "$ROOT/scripts/lib/worktrees.sh"

# Strip C0, DEL and C1 control bytes (raw and UTF-8 encoded) from printed values.
clean() {
    printf '%s' "$1" | LC_ALL=C tr -d '\000-\037\177' | LC_ALL=C sed $'s/\xc2[\x80-\x9f]//g'
}

refuse() {
    printf 'Error: %s\n' "$(clean "$1")" >&2
    exit "$REFUSE"
}

[[ $# -le 1 ]] || refuse "--audit takes at most one BRANCH"
BRANCH=""
HAVE_BRANCH=0
if [[ $# -eq 1 ]]; then
    HAVE_BRANCH=1
    BRANCH="$1"
    [[ -n "$BRANCH" ]] || refuse "--audit BRANCH must not be empty"
    [[ "$BRANCH" != -* ]] || refuse "--audit BRANCH must not start with '-': $BRANCH"
fi

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || refuse "not inside a git repository: $PWD"
CALLER="$(git rev-parse --show-toplevel 2>/dev/null)" || refuse "cannot resolve the repository root"
CALLER="$(worktree_real "$CALLER")"

TARGET="$CALLER"
if [[ "$HAVE_BRANCH" == 1 ]]; then
    git check-ref-format "refs/heads/$BRANCH" >/dev/null 2>&1 || refuse "invalid branch name: $BRANCH"
    git show-ref --verify --quiet -- "refs/heads/$BRANCH" || refuse "no such branch: $BRANCH"
    CURRENT="$(git symbolic-ref -q HEAD 2>/dev/null || true)"
    if [[ "$CURRENT" == "refs/heads/$BRANCH" ]]; then
        TARGET="$CALLER"
    else
        matches=0
        found=""
        path=""
        while IFS= read -r line; do
            case "$line" in
                "worktree "*) path="${line#worktree }" ;;
                "branch refs/heads/$BRANCH") matches=$((matches + 1)); found="$path" ;;
            esac
        done < <(git worktree list --porcelain 2>/dev/null)
        [[ "$matches" -ge 1 ]] || refuse "branch $BRANCH is not checked out in any worktree"
        [[ "$matches" -le 1 ]] || refuse "branch $BRANCH is checked out in more than one worktree"
        TARGET="$(worktree_real "$found")"
        [[ -n "$TARGET" ]] || refuse "worktree for branch $BRANCH does not exist: $found"
    fi
fi

UNCLE_DIR="$TARGET/.uncle"
[[ -d "$UNCLE_DIR" ]] || refuse "no .uncle directory in $TARGET"
[[ -O "$UNCLE_DIR" ]] || refuse ".uncle in $TARGET is not owned by the current user"

WF="$UNCLE_DIR/workflow"
STATE_FILE="$WF/state"
LOCK_FILE="$WF/driver.lock"
VERDICT_FILE="$WF/audit-verdict"

family="$(cat "$WF/family" 2>/dev/null | tr -d '[:space:]')"
[[ "$family" == change ]] || refuse "workflow family of $TARGET is '${family:-none}', not 'change'"
[[ -s "$STATE_FILE" ]] || refuse "no workflow state in $TARGET"

PREV_RAW="$(head -n 1 "$STATE_FILE")"
PREV="$(state_read "$STATE_FILE")"
ISSUE="$(state_issue "$STATE_FILE")"
case "$PREV" in
    WAIT_IMPLEMENT_APPROVAL|MANUAL_CHECKLIST|VALIDATE_MANUAL_CHECKLIST|EXECUTE_CHECKLIST|FINAL_AUDIT|VALIDATE_AUDIT|WAIT_AUDIT_OVERRIDE|COMPLETE) ;;
    *) refuse "state '$PREV' is not a post-implementation stage; finish the run before auditing" ;;
esac

# Non-blocking lock probe and the state write, under the held driver lock.
# exit 3 = lock held elsewhere; exit 0 = written.
lock_write() {
    python3 - "$LOCK_FILE" "$STATE_FILE" "$1" <<'PY'
import fcntl, sys
lock, state, text = sys.argv[1:4]
fd = open(lock, "a+")
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(3)
with open(state, "w") as f:
    f.write(text + "\n")
sys.exit(0)
PY
}

if [[ "$ISSUE" =~ ^[0-9]+$ ]]; then NEW="$ISSUE:FINAL_AUDIT"; else NEW="FINAL_AUDIT"; fi
lock_write "$NEW"
rc=$?
if [[ "$rc" == 3 ]]; then
    refuse "a workflow driver is running in $TARGET (driver.lock is held)"
elif [[ "$rc" != 0 ]]; then
    refuse "could not record the audit state in $TARGET"
fi

printf 'Previous state: %s\n' "$(clean "$PREV")"
START="$(date +%s)"

cd "$TARGET" || exit "$REFUSE"
bash "$ROOT/scripts/change-workflow.sh"
DRIVER_STATUS=$?

# If the driver could not take the lock (another process holds it) and nothing moved the
# state off what we wrote, put the previous state back.
if [[ "$DRIVER_STATUS" != 0 ]] && [[ "$(head -n 1 "$STATE_FILE" 2>/dev/null)" == "$NEW" ]]; then
    if ! python3 - "$LOCK_FILE" <<'PY'
import fcntl, sys
fd = open(sys.argv[1], "a+")
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(1)
PY
    then
        lock_write_restore=1
        printf '%s\n' "$PREV_RAW" > "$STATE_FILE"
        echo "Error: driver could not take the lock; previous state restored" >&2
    fi
fi

verdict="UNKNOWN"
if [[ -s "$VERDICT_FILE" ]]; then
    mtime="$(stat -f %m "$VERDICT_FILE" 2>/dev/null || stat -c %Y "$VERDICT_FILE" 2>/dev/null || echo 0)"
    if [[ "$mtime" =~ ^[0-9]+$ ]] && [[ "$mtime" -ge "$START" ]]; then
        v="$(verdict_file_field() { awk -F'\t' 'NR==1{ print (NF==3 ? $2 : $1); exit }' "$1"; }; verdict_file_field "$VERDICT_FILE")"
        if [[ "$v" =~ ^[A-Z_]+$ ]]; then verdict="$v"; fi
    fi
fi
printf 'verdict: %s\n' "$(clean "$verdict")"
printf 'audit: %s\n' "$(clean "$TARGET/.uncle/docs/FINAL_AUDIT.md")"
# AC-2: a missing, stale or unparsable verdict cannot be reported as success.
# A failing driver keeps its own status; a driver that exited 0 without a
# readable verdict exits with the refusal code.
if [[ "$verdict" == UNKNOWN && "$DRIVER_STATUS" == 0 ]]; then exit "$REFUSE"; fi
exit "$DRIVER_STATUS"
