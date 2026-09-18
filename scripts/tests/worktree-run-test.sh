#!/usr/bin/env bash
set -uo pipefail

# Hermetic coverage of `from-issue.sh --worktree` (Issue 64): worktree creation,
# seeding and driver cwd, concurrent runs, config copy, refusals, removal
# guards, the removal offer, `uncle --runs`, and the no-flag path. No network:
# a stubbed gh and a stub driver sit on PATH; scripts run from a scratch
# install directory against a scratch project, as an installed `uncle` does.
#
# Signing: the global git config demands signing through a fake signer that
# logs and refuses; every fixture commit passes --no-gpg-sign under
# -c commit.gpgsign=false -c tag.gpgsign=false, and the log must stay absent.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
TMP="$(cd "$TMP" && pwd -P)"
trap 'if [[ "${UNCLE_KEEP_TEST_TMP:-0}" == 1 ]]; then echo "Kept worktree fixtures: $TMP"; else rm -rf "$TMP"; fi' EXIT

for var in $(env | sed -n 's/^\(UNCLE_[A-Z_0-9]*\|STAGEGATE_[A-Z_0-9]*\|WORKFLOW_[A-Z_0-9]*\|GIT_[A-Z_0-9]*\|GPG_[A-Z_0-9]*\|SSH_[A-Z_0-9]*\)=.*/\1/p'); do
    unset "$var"
done

REAL_GIT="$(command -v git)"
mkdir -p "$TMP/bin"
cat > "$TMP/bin/fake-signer" <<'SIGNER'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SIGNER_CALLS"
exit 1
SIGNER
cat > "$TMP/gitconfig" <<EOF
[commit]
	gpgsign = true
[tag]
	gpgsign = true
[gpg]
	program = $TMP/bin/fake-signer
[gpg "ssh"]
	program = $TMP/bin/fake-signer
EOF
# Records every git invocation so the suite can prove no branch deletion or
# forced removal ever ran (I-4).
cat > "$TMP/bin/git" <<'GITSHIM'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GIT_CALLS"
exec "$REAL_GIT" "$@"
GITSHIM
# The stub gh answers the issue fetch and the label lookup; nothing else.
cat > "$TMP/bin/gh" <<'GH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GH_LOG_FILE"
if [[ "${1:-}" == "auth" ]]; then exit 0; fi
if [[ "${1:-}" == "issue" && "${2:-}" == "view" ]]; then
    num="$3"
    if [[ "$*" == *"--json labels"* ]]; then
        printf '{"labels":[{"name":"%s"}]}\n' "${FAKE_GH_LABEL:-enhancement}"
        exit 0
    fi
    printf '{"title":"Add widget %s","body":"Body of issue %s","url":"https://github.com/owner/repo/issues/%s","state":"OPEN","labels":[],"comments":[]}\n' "$num" "$num" "$num"
    exit 0
fi
exit 1
GH
chmod +x "$TMP/bin/fake-signer" "$TMP/bin/git" "$TMP/bin/gh"
export PATH="$TMP/bin:$PATH" REAL_GIT
export GIT_CONFIG_GLOBAL="$TMP/gitconfig" GIT_CONFIG_NOSYSTEM=1
export SIGNER_CALLS="$TMP/signer.log" GIT_CALLS="$TMP/git.log"

FAILED=0
COUNT=0
CASE_NAME=""
CASE=""
PROJ=""
INSTALL=""
OUT=""
GH_LOG=""
DRIVER_LOG=""
RC=0

fail() {
    echo "FAIL [$CASE_NAME] $1"
    FAILED=$((FAILED + 1))
}

check() {
    # check <description> <command...>: counts one assertion.
    local what="$1"
    shift
    COUNT=$((COUNT + 1))
    if ! "$@"; then
        fail "$what"
        [[ -s "$OUT" ]] && sed 's/^/    /' < "$OUT"
    fi
}

expect_status() {
    COUNT=$((COUNT + 1))
    if [[ "$RC" != "$1" ]]; then
        fail "expected exit $1, got $RC"
        sed 's/^/    /' < "$OUT"
    fi
}

expect_out() {
    COUNT=$((COUNT + 1))
    if ! grep -qF -- "$1" "$OUT"; then
        fail "expected output to contain: $1"
        sed 's/^/    /' < "$OUT"
    fi
}

expect_not_out() {
    COUNT=$((COUNT + 1))
    if grep -qF -- "$1" "$OUT"; then
        fail "expected output NOT to contain: $1"
    fi
}

g() {
    git -c commit.gpgsign=false -c tag.gpgsign=false "$@"
}

# ---------------------------------------------------------------------------
# Scratch fixture: an install dir holding the scripts and a stub driver, and a
# project repo with a GitHub-shaped remote and one unsigned commit.
# ---------------------------------------------------------------------------

new_case() {
    CASE_NAME="$1"
    CASE="$TMP/$1"
    PROJ="$CASE/proj"
    INSTALL="$CASE/install"
    OUT="$CASE/out.txt"
    GH_LOG="$CASE/gh.log"
    DRIVER_LOG="$CASE/driver.log"
    mkdir -p "$INSTALL/scripts/lib" "$PROJ/.uncle" "$CASE/bin"
    : > "$OUT"; : > "$GH_LOG"; : > "$DRIVER_LOG"

    cp "$ROOT/scripts/from-issue.sh" "$INSTALL/scripts/from-issue.sh"
    cp "$ROOT"/scripts/lib/*.sh "$INSTALL/scripts/lib/"
    cp "$ROOT"/scripts/lib/*.py "$INSTALL/scripts/lib/"
    cat > "$INSTALL/scripts/change-workflow.sh" <<'DRV'
#!/usr/bin/env bash
set -uo pipefail
before="$PWD"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="${UNCLE_PROJECT_ROOT:-$ROOT}"
cd "$PROJECT_ROOT"
mkdir -p .uncle/workflow/approvals
mkdir .uncle/workflow/lock || { echo "lock held"; exit 9; }
printf 'cwd\t%s\nroot\t%s\nargs\t%s\nstart\t%s\n' "$before" "${UNCLE_PROJECT_ROOT:-}" "$*" "$(date +%s)" >> "$DRIVER_LOG"
printf '%s\n' "${STAGEGATE_ORIGIN_ISSUE:-}:${FAKE_STATE:-COMPLETE}" > .uncle/workflow/state
: > .uncle/workflow/approvals/CHANGE_PLAN.md.sha256
if [[ -n "${FAKE_DRIVER_SLEEP:-}" ]]; then sleep "$FAKE_DRIVER_SLEEP"; fi
printf 'end\t%s\n' "$(date +%s)" >> "$DRIVER_LOG"
rmdir .uncle/workflow/lock
exit "${FAKE_DRIVER_EXIT:-0}"
DRV
    chmod +x "$INSTALL/scripts/change-workflow.sh"

    g init -q -b main "$PROJ"
    g -C "$PROJ" config commit.gpgsign false
    g -C "$PROJ" config tag.gpgsign false
    g -C "$PROJ" config user.name Fixture
    g -C "$PROJ" config user.email fixture@example.test
    g -C "$PROJ" remote add origin https://github.com/owner/repo.git
    echo "hello" > "$PROJ/hello.txt"
    printf '.uncle/\n' > "$PROJ/.gitignore"
    g -C "$PROJ" add -A
    g -C "$PROJ" commit --no-gpg-sign -q -m "initial"
    printf 'runner claude\neffort high\n' > "$PROJ/.uncle/config"
}

# run_issue <stdin-file> <args...> — from-issue.sh from the project, as the launcher runs it.
run_issue() {
    local stdin_file="$1"
    shift
    (cd "$PROJ" && env UNCLE_PROJECT_ROOT="$PROJ" GH_LOG_FILE="$GH_LOG" DRIVER_LOG="$DRIVER_LOG" \
        bash "$INSTALL/scripts/from-issue.sh" "$@" < "$stdin_file" > "$OUT" 2>&1)
    RC=$?
}

registered() {
    # registered <dir>: git lists the physical path of <dir>.
    local want
    want="$(cd "$1" 2>/dev/null && pwd -P)" || return 1
    g -C "$PROJ" worktree list --porcelain | sed -n 's/^worktree //p' | while IFS= read -r p; do
        [[ "$(cd "$p" 2>/dev/null && pwd -P)" == "$want" ]] && echo yes
    done | grep -q yes
}

branch_exists() {
    g -C "$PROJ" show-ref --verify --quiet "refs/heads/$1"
}

driver_field() {
    sed -n "s/^$1"$'\t''//p' "$DRIVER_LOG" | head -n 1
}

# A finished run's tracked files are committed by the PR handoff; `.uncle/`
# stays ignored. Removal is tested against that shape.
commit_worktree() {
    g -C "$1" add -A
    g -C "$1" commit --no-gpg-sign -q -m "handoff"
}

# ---------------------------------------------------------------------------
# AC-1, AC-4, AC-6 hint: create, seed in the worktree, driver runs there.
# ---------------------------------------------------------------------------

new_case create-seeds-and-runs-in-worktree
export UNCLE_STATUS_FILE="$CASE/status.jsonl"
run_issue /dev/null 42 --worktree
unset UNCLE_STATUS_FILE
expect_status 0
WT="$CASE/proj-issue-42"
check "project_root status event names the worktree" \
    test "$(jq -r 'select(.event == "project_root") | .path' "$CASE/status.jsonl" | head -n 1)" == "$(driver_field root)"
check "worktree registered at the default dir" registered "$WT"
check "branch feat/add-widget-42 exists" branch_exists feat/add-widget-42
check "worktree is on the branch" test "$(g -C "$WT" branch --show-current)" == feat/add-widget-42
check "CHANGE_REQUEST.md seeded in the worktree" test -s "$WT/CHANGE_REQUEST.md"
check "no CHANGE_REQUEST.md in the source project" test ! -e "$PROJ/CHANGE_REQUEST.md"
check "driver cwd is the worktree" test "$(driver_field cwd)" == "$(cd "$WT" && pwd -P)"
check "driver UNCLE_PROJECT_ROOT is the worktree" test "$(driver_field root)" == "$(cd "$WT" && pwd -P)"
check "config copied byte-for-byte" cmp -s "$PROJ/.uncle/config" "$WT/.uncle/config"
check "worktree holds its own origin" test -s "$WT/.uncle/workflow/origin"
check "source project has no state" test ! -e "$PROJ/.uncle/workflow/state"
expect_out "Created worktree"
expect_out "kept; remove with: scripts/lib/worktrees.sh remove"
expect_not_out "Remove worktree"
check "gh label lookup was made" grep -q -- "--json labels" "$GH_LOG"

# In-flight state with no origin in this issue's own worktree is an earlier
# run of the same issue: it is archived and the seed starts fresh. A run that
# still holds the lock is refused as before.
new_case ownerless-state-in-own-worktree-is-archived
run_issue /dev/null 42 --worktree
expect_status 0
WT="$CASE/proj-issue-42"
printf '42:WAIT_UPDATED_PLAN_APPROVAL\n' > "$WT/.uncle/workflow/state"
rm -f "$WT/.uncle/workflow/origin"
run_issue /dev/null 42 --worktree
expect_status 0
expect_out "recorded no owner; archiving it and starting"
check "driver ran in the worktree again"        test "$(driver_field cwd)" == "$(cd "$WT" && pwd -P)"
check "stale state archived, not deleted"       grep -rq "WAIT_UPDATED_PLAN_APPROVAL" "$WT/.uncle/workflow-history"
check "fresh run recorded its state"            test "$(cat "$WT/.uncle/workflow/state")" == "42:COMPLETE"

new_case ownerless-state-with-live-lock-is-refused
run_issue /dev/null 42 --worktree
expect_status 0
WT="$CASE/proj-issue-42"
printf '42:WAIT_UPDATED_PLAN_APPROVAL\n' > "$WT/.uncle/workflow/state"
rm -f "$WT/.uncle/workflow/origin"
mkdir "$WT/.uncle/workflow/lock"
run_issue /dev/null 42 --worktree
expect_status 1
expect_out "Refusing to seed"
expect_not_out "recorded no owner"
check "nothing archived while the lock is held" test ! -e "$WT/.uncle/workflow-history"
rmdir "$WT/.uncle/workflow/lock"

# A driver that exits 0 short of COMPLETE has moved the run to a gate it wants
# re-entered; the seed re-runs it instead of calling the run finished, and
# stops once the state no longer moves.
new_case reopened-gate-is-reentered-not-finished
FAKE_STATE=WAIT_PLAN_APPROVAL run_issue /dev/null 42 --worktree
expect_status 0
expect_out "The run is waiting at WAIT_PLAN_APPROVAL; opening that gate now."
expect_out "stopped at WAIT_PLAN_APPROVAL"
expect_not_out "Change workflow finished"
expect_not_out "Making PR"
check "driver was re-entered exactly once"  test "$(grep -c '^start' "$DRIVER_LOG")" -eq 2

# --branch overrides the derived name; --worktree-dir the directory.
new_case explicit-branch-and-dir
run_issue /dev/null 42 --worktree-dir "$CASE/elsewhere" --branch topic/x
expect_status 0
check "explicit dir registered" registered "$CASE/elsewhere"
check "explicit branch checked out" test "$(g -C "$CASE/elsewhere" branch --show-current)" == topic/x
check "no gh label lookup with --branch" bash -c '! grep -q -- "--json labels" "$1"' _ "$GH_LOG"

# Label lookup failure falls back to the uncle/ prefix.
new_case label-lookup-fails
FAKE_GH_LABEL=nothing run_issue /dev/null 7 --worktree
expect_status 0
check "uncle/ prefix without a mapped label" branch_exists uncle/add-widget-7

# ---------------------------------------------------------------------------
# AC-4: absent source config yields no file and no error.
# ---------------------------------------------------------------------------

new_case absent-config
rm -f "$PROJ/.uncle/config"
run_issue /dev/null 42 --worktree
expect_status 0
check "no config in the worktree" test ! -e "$CASE/proj-issue-42/.uncle/config"
expect_not_out "Could not copy"

# ---------------------------------------------------------------------------
# AC-7 / D-11: config copy failure rolls the directory back, keeps the branch.
# ---------------------------------------------------------------------------

new_case config-copy-fails-rolls-back
rm -f "$PROJ/.uncle/config"
mkdir "$PROJ/.uncle/config"
run_issue /dev/null 42 --worktree
expect_status 1
check "worktree dir removed" test ! -e "$CASE/proj-issue-42"
check "worktree unregistered" bash -c '! git -C "$1" worktree list --porcelain | grep -q "proj-issue-42"' _ "$PROJ"
check "branch kept" branch_exists feat/add-widget-42
expect_out "git branch -d feat/add-widget-42"
check "no CHANGE_REQUEST.md anywhere" bash -c '[[ ! -e "$1/CHANGE_REQUEST.md" && ! -e "$1-issue-42/CHANGE_REQUEST.md" ]]' _ "$PROJ"
check "driver did not run" test ! -s "$DRIVER_LOG"

# ---------------------------------------------------------------------------
# AC-2: two worktrees, two drivers, overlapping, isolated.
# ---------------------------------------------------------------------------

new_case concurrent-runs
LOG42="$CASE/driver42.log"; LOG43="$CASE/driver43.log"
OUT42="$CASE/out42.txt"; OUT43="$CASE/out43.txt"
(cd "$PROJ" && env UNCLE_PROJECT_ROOT="$PROJ" GH_LOG_FILE="$GH_LOG" DRIVER_LOG="$LOG42" FAKE_DRIVER_SLEEP=3 \
    bash "$INSTALL/scripts/from-issue.sh" 42 --worktree < /dev/null > "$OUT42" 2>&1) &
P42=$!
(cd "$PROJ" && env UNCLE_PROJECT_ROOT="$PROJ" GH_LOG_FILE="$GH_LOG" DRIVER_LOG="$LOG43" FAKE_DRIVER_SLEEP=3 \
    bash "$INSTALL/scripts/from-issue.sh" 43 --worktree < /dev/null > "$OUT43" 2>&1) &
P43=$!
wait "$P42"; RC42=$?
wait "$P43"; RC43=$?
cat "$OUT42" "$OUT43" > "$OUT"
check "issue 42 run exited 0" test "$RC42" == 0
check "issue 43 run exited 0" test "$RC43" == 0
W42="$CASE/proj-issue-42"; W43="$CASE/proj-issue-43"
for n in 42 43; do
    wt="$CASE/proj-issue-$n"
    check "worktree $n state COMPLETE" test "$(cat "$wt/.uncle/workflow/state")" == "$n:COMPLETE"
    check "worktree $n has approvals/" test -d "$wt/.uncle/workflow/approvals"
    check "worktree $n has origin" grep -q "	$n	" "$wt/.uncle/workflow/origin"
    check "worktree $n lock released" test ! -e "$wt/.uncle/workflow/lock"
done
check "runs overlapped" bash -c '
    s43="$(sed -n "s/^start\t//p" "$2")"; e42="$(sed -n "s/^end\t//p" "$1")"
    [[ -n "$s43" && -n "$e42" && "$s43" -lt "$e42" ]]' _ "$LOG42" "$LOG43"
check "source project has no lock/state/approvals/origin" bash -c \
    '[[ ! -e "$1/.uncle/workflow/lock" && ! -e "$1/.uncle/workflow/state" && ! -e "$1/.uncle/workflow/approvals" && ! -e "$1/.uncle/workflow/origin" ]]' _ "$PROJ"
check "worktree 42 request is not 43's" bash -c '! grep -q "Add widget 43" "$1/CHANGE_REQUEST.md" && grep -q "Add widget 42" "$1/CHANGE_REQUEST.md"' _ "$W42"
check "worktree 43 request is not 42's" bash -c '! grep -q "Add widget 42" "$1/CHANGE_REQUEST.md" && grep -q "Add widget 43" "$1/CHANGE_REQUEST.md"' _ "$W43"

# ---------------------------------------------------------------------------
# AC-6: uncle --runs lists both worktrees; lock shows as locked.
# ---------------------------------------------------------------------------

mkdir "$W43/.uncle/workflow/lock"
(cd "$PROJ" && bash "$ROOT/uncle" --runs > "$OUT" 2>&1)
RC=$?
expect_status 0
expect_out "#42	COMPLETE	idle	"
expect_out "#43	COMPLETE	locked	"
check "one line per run" test "$(grep -c '^#' "$OUT")" == 2
check "42 row names its path" grep -q "^#42	COMPLETE	idle	.*proj-issue-42$" "$OUT"
rmdir "$W43/.uncle/workflow/lock"

# ---------------------------------------------------------------------------
# AC-7: removal guards; the branch survives; no git branch -d/-D ever runs.
# ---------------------------------------------------------------------------

CASE_NAME=remove-guards
commit_worktree "$W42"
mkdir "$W42/.uncle/workflow/lock"
bash "$INSTALL/scripts/lib/worktrees.sh" remove "$W42" > "$OUT" 2>&1; RC=$?
expect_status 1
expect_out "lock"
check "dir kept while locked" test -d "$W42"
rmdir "$W42/.uncle/workflow/lock"
printf '42:IMPLEMENT\n' > "$W42/.uncle/workflow/state"
bash "$INSTALL/scripts/lib/worktrees.sh" remove "$W42" > "$OUT" 2>&1; RC=$?
expect_status 1
expect_out "not COMPLETE"
check "dir kept while non-COMPLETE" test -d "$W42"
printf '42:COMPLETE\n' > "$W42/.uncle/workflow/state"
bash "$INSTALL/scripts/lib/worktrees.sh" remove "$W42" > "$OUT" 2>&1; RC=$?
expect_status 0
check "dir removed" test ! -e "$W42"
check "worktree unregistered" bash -c '! git -C "$1" worktree list --porcelain | grep -q "proj-issue-42$"' _ "$PROJ"
check "branch survives removal" branch_exists feat/add-widget-42
# A dirty COMPLETE worktree: git's own refusal, dir kept.
bash "$INSTALL/scripts/lib/worktrees.sh" remove "$W43" > "$OUT" 2>&1; RC=$?
expect_status 1
expect_out "worktree kept"
check "dirty dir kept" test -d "$W43"
bash "$INSTALL/scripts/lib/worktrees.sh" remove "$CASE/nowhere" > "$OUT" 2>&1; RC=$?
expect_status 1
expect_out "Not a registered git worktree"

# ---------------------------------------------------------------------------
# AC-5 / I-3: refusals before any write.
# ---------------------------------------------------------------------------

new_case existing-branch-refused
g -C "$PROJ" branch feat/add-widget-42
run_issue /dev/null 42 --worktree
expect_status 1
expect_out "Branch already exists: feat/add-widget-42"
check "no worktree dir" test ! -e "$CASE/proj-issue-42"
check "no CHANGE_REQUEST.md in the project" test ! -e "$PROJ/CHANGE_REQUEST.md"
check "driver did not run" test ! -s "$DRIVER_LOG"

new_case non-empty-dir-refused
mkdir -p "$CASE/full" && echo x > "$CASE/full/file"
run_issue /dev/null 42 --worktree-dir "$CASE/full"
expect_status 1
expect_out "Directory is not empty: $CASE/full"
check "branch not created" bash -c '! git -C "$1" show-ref --verify --quiet refs/heads/feat/add-widget-42' _ "$PROJ"
check "no CHANGE_REQUEST.md anywhere" bash -c '[[ ! -e "$1/CHANGE_REQUEST.md" && ! -e "$2/CHANGE_REQUEST.md" ]]' _ "$PROJ" "$CASE/full"

new_case dir-inside-project-refused
run_issue /dev/null 42 --worktree-dir "$PROJ/.uncle/wt"
expect_status 1
expect_out "must not be inside the project"
check "nothing created" test ! -e "$PROJ/.uncle/wt"

new_case bad-branch-refused
run_issue /dev/null 42 --worktree --branch "bad name"
expect_status 1
expect_out "Invalid branch name"

# ---------------------------------------------------------------------------
# AC-9: --new with --worktree is refused before fetching.
# ---------------------------------------------------------------------------

new_case new-with-worktree
run_issue /dev/null 42 --new --worktree
expect_status 1
expect_out "require --change"
expect_out "Usage:"
check "nothing fetched" test ! -s "$GH_LOG"
run_issue /dev/null 42 --worktree-dir "$CASE/x" --new
expect_status 1
expect_out "require --change"
check "nothing fetched" test ! -s "$GH_LOG"
# --branch names the worktree's branch. It no longer needs --worktree, because
# an issue run has one unless --no-worktree says otherwise.
run_issue /dev/null 42 --branch topic/x --no-worktree
expect_status 1
expect_out "--branch requires --worktree"

new_case not-a-repo
rm -rf "$PROJ/.git"
run_issue /dev/null 42 --worktree
expect_status 1
expect_out "Not a git repository"
check "nothing fetched" test ! -s "$GH_LOG"

# ---------------------------------------------------------------------------
# AC-8: without the flag, files, cwd and driver args are as before.
# ---------------------------------------------------------------------------

# An issue run takes its own worktree by default: one issue, one directory, one
# branch, so a second issue can start while this one is going.
new_case default-worktree
run_issue /dev/null 42 --change --unattended
expect_status 0
check "a worktree was created" test "$(g -C "$PROJ" worktree list --porcelain | grep -c '^worktree ')" == 2
check "driver cwd is the worktree" test "$(driver_field cwd)" != "$(cd "$PROJ" && pwd -P)"
check "CHANGE_REQUEST.md in the worktree" test ! -s "$PROJ/CHANGE_REQUEST.md"
check "driver args unchanged" test "$(driver_field args)" == "--unattended"

# --no-worktree is the opt-out, and keeps everything where it was.
new_case no-worktree-opt-out
run_issue /dev/null 42 --change --no-worktree --unattended
expect_status 0
check "driver cwd is the project" test "$(driver_field cwd)" == "$(cd "$PROJ" && pwd -P)"
check "driver root is the project" test "$(driver_field root)" == "$PROJ"
check "driver args unchanged" test "$(driver_field args)" == "--unattended"
check "CHANGE_REQUEST.md in the project" test -s "$PROJ/CHANGE_REQUEST.md"
check "state in the project" test -s "$PROJ/.uncle/workflow/state"
check "no worktree created" test "$(g -C "$PROJ" worktree list --porcelain | grep -c '^worktree ')" == 1
check "no sibling dir" test ! -e "$CASE/proj-issue-42"
expect_not_out "worktree"
expect_not_out "Remove"

# ---------------------------------------------------------------------------
# B-8: the removal offer. Sourced directly, then end to end under a pty.
# ---------------------------------------------------------------------------

new_case offer-answer-paths
run_issue /dev/null 42 --worktree
expect_status 0
W42="$CASE/proj-issue-42"
commit_worktree "$W42"
(cd "$PROJ" && printf 'n\n' | env STAGEGATE_FROM_ISSUE_SOURCE_ONLY=1 UNCLE_PROJECT_ROOT="$PROJ" bash -c \
    '. "$1"; offer_worktree_removal "$2"' _ "$INSTALL/scripts/from-issue.sh" "$W42" > "$OUT" 2>&1)
RC=$?
expect_status 0
expect_out "Remove worktree $W42? [y/N]"
expect_out "Keeping worktree"
check "n keeps the dir" test -d "$W42"
(cd "$PROJ" && printf 'y\n' | env STAGEGATE_FROM_ISSUE_SOURCE_ONLY=1 UNCLE_PROJECT_ROOT="$PROJ" bash -c \
    '. "$1"; offer_worktree_removal "$2"' _ "$INSTALL/scripts/from-issue.sh" "$W42" > "$OUT" 2>&1)
RC=$?
expect_status 0
expect_out "Removed worktree"
check "y removes the dir" test ! -e "$W42"
check "branch kept after y" branch_exists feat/add-widget-42

cat > "$TMP/pty-run.py" <<'PTY'
import os, pty, select, sys, time
pid, fd = pty.fork()
if pid == 0:
    os.execvp(sys.argv[1], sys.argv[1:])
out = b''
answered = False
deadline = time.time() + 30
while True:
    ready, _, _ = select.select([fd], [], [], 1)
    if ready:
        try:
            data = os.read(fd, 4096)
        except OSError:
            break
        if not data:
            break
        out += data
        if b'Remove worktree' in out and not answered:
            os.write(fd, b'n\n')
            answered = True
    if time.time() > deadline:
        os.kill(pid, 9)
        out += b'\nPTY TIMEOUT\n'
        break
_, status = os.waitpid(pid, 0)
sys.stdout.buffer.write(out)
sys.exit(os.waitstatus_to_exitcode(status))
PTY

new_case offer-under-pty
(cd "$PROJ" && env UNCLE_PROJECT_ROOT="$PROJ" GH_LOG_FILE="$GH_LOG" DRIVER_LOG="$DRIVER_LOG" \
    python3 "$TMP/pty-run.py" bash "$INSTALL/scripts/from-issue.sh" 42 --worktree > "$OUT" 2>&1)
RC=$?
expect_status 0
expect_out "Remove worktree $CASE/proj-issue-42? [y/N]"
expect_not_out "PTY TIMEOUT"
check "n keeps the worktree" test -d "$CASE/proj-issue-42"

new_case unattended-under-pty
(cd "$PROJ" && env UNCLE_PROJECT_ROOT="$PROJ" GH_LOG_FILE="$GH_LOG" DRIVER_LOG="$DRIVER_LOG" \
    python3 "$TMP/pty-run.py" bash "$INSTALL/scripts/from-issue.sh" 42 --worktree --unattended > "$OUT" 2>&1)
RC=$?
expect_status 0
expect_not_out "Remove worktree"
expect_out "kept; remove with: scripts/lib/worktrees.sh remove"
check "driver got --unattended" test "$(driver_field args)" == "--unattended"
check "worktree kept" test -d "$CASE/proj-issue-42"

# Driver failure: existing message, no offer.
new_case driver-fails-no-offer
(cd "$PROJ" && env UNCLE_PROJECT_ROOT="$PROJ" GH_LOG_FILE="$GH_LOG" DRIVER_LOG="$DRIVER_LOG" FAKE_DRIVER_EXIT=3 \
    python3 "$TMP/pty-run.py" bash "$INSTALL/scripts/from-issue.sh" 42 --worktree > "$OUT" 2>&1)
RC=$?
expect_status 3
expect_out "change-workflow.sh exited 3"
expect_not_out "Remove worktree"

# ---------------------------------------------------------------------------
# I-4 across the whole suite, and AC-10.
# ---------------------------------------------------------------------------

CASE_NAME=suite-wide
: > "$OUT"
check "no git branch -d/-D ran" bash -c '! grep -Eq "^branch -[dD]|^(-C [^ ]+ )?branch -[dD]" "$1"' _ "$GIT_CALLS"
check "no forced worktree removal ran" bash -c '! grep -q "worktree remove.*--force" "$1"' _ "$GIT_CALLS"
check "fixture git never reached the signer" test ! -e "$SIGNER_CALLS"

if [[ "$FAILED" -ne 0 ]]; then
    echo "worktree-run-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi
echo "worktree-run-test.sh: $COUNT checks passed"
