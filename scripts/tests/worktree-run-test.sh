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

# Refused while an uncle build is driving this checkout, before anything else
# here runs.
#
# This suite exists only in uncle's own repository, so if it is running at all
# the project under test is uncle. The case to avoid is therefore exactly one:
# uncle building uncle.
#
# The reason is not that it is slow. This suite drives worktree creation and
# from-issue.sh -- the very machinery the build is running on, and in the
# middle of changing. Exercising that against a checkout a live run owns tests
# nothing anybody can act on: a pass says the machinery worked while being
# rewritten underneath it, and a failure cannot be told apart from the build's
# own half-applied edits. A baseline is meant to record what passed before the
# change; this suite cannot answer that question about itself.
#
# It also hangs, which is only how the problem announces itself -- about 15
# seconds on its own against the harness's 600-second timeout, with 87 of 88
# suites finished and the whole baseline waiting on this one, leaving the build
# at IMPLEMENT behind a baseline that cannot complete.
#
# Detected from the environment, not from a lock file. Two earlier guesses were
# wrong and both failed silently: change-workflow.sh defines acquire_lock() and
# never calls it, so .uncle/workflow/lock is never created; and
# UNCLE_PROJECT_ROOT is stripped before a stage runs. UNCLE_UNATTENDED is
# exported unconditionally by both drivers and UNCLE_STATUS_STAGE whenever a
# stage starts, while a developer's shell has no UNCLE_ variables at all.
# Neither can be left behind by a killed run: they live in the process
# environment, not on disk.
#
# Skipping is the honest result -- the suite has not run, and exit 77 says so
# rather than reporting a pass nobody earned. The check must come before the
# hermetic unset below, which strips the variables it reads.
#
# UNCLE_TEST_ALLOW_NESTED=1 forces it to run anyway.
if [[ "${UNCLE_TEST_ALLOW_NESTED:-0}" != 1 ]] \
   && [[ -n "${UNCLE_UNATTENDED:-}" || -n "${UNCLE_STATUS_STAGE:-}" ]]; then
    echo "worktree-run-test.sh: skipped, an uncle build is driving this checkout (stage ${UNCLE_STATUS_STAGE:-unknown})"
    echo "worktree-run-test.sh: it exercises the worktree machinery this build is changing, so the result would mean nothing; set UNCLE_TEST_ALLOW_NESTED=1 to run anyway"
    exit 77
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export ENGINE_SRC="$ROOT/scripts/lib/change-pr.sh"
# A failed mktemp must stop the suite: `cd ""` succeeds in place, which would
# make the scratch directory -- and the EXIT trap's rm -rf -- the checkout.
TMP="$(mktemp -d)" || { echo "worktree-run-test.sh: mktemp -d failed" >&2; exit 1; }
[[ -n "$TMP" && -d "$TMP" ]] || { echo "worktree-run-test.sh: no scratch directory" >&2; exit 1; }
TMP="$(cd "$TMP" && pwd -P)" || exit 1
if [[ "$TMP" == "$ROOT" || "$TMP" == "/" || "$ROOT" == "$TMP"/* ]]; then
    echo "worktree-run-test.sh: refusing scratch directory $TMP that contains the checkout" >&2
    exit 1
fi
trap 'if [[ "${UNCLE_KEEP_TEST_TMP:-0}" == 1 ]]; then echo "Kept worktree fixtures: $TMP"; else rm -rf "$TMP"; fi' EXIT

# -E, because this is the whole of the suite's hermeticity and it was silently
# doing nothing. BSD sed -- which is what macOS ships -- has no \| alternation
# in a basic regular expression, so the pattern matched no line, the loop
# iterated over an empty list, and not one variable was unset. GNU sed accepts
# \|, so this worked in CI and failed only on the machine it was written on.
#
# What that cost: from-issue.sh prefers $UNCLE_RUNTIME_ROOT over its own
# location, so a suite inheriting a live build's environment resolved the
# installed uncle instead of the scratch install below -- running the real
# driver, and real model calls at --max-turns 120, in place of the stub driver
# this fixture writes. That is why the suite took 18 seconds alone and hit the
# harness's 600-second timeout inside a build.
for var in $(env | sed -nE 's/^(UNCLE_[A-Z_0-9]*|STAGEGATE_[A-Z_0-9]*|WORKFLOW_[A-Z_0-9]*|GIT_[A-Z_0-9]*|GPG_[A-Z_0-9]*|SSH_[A-Z_0-9]*)=.*/\1/p'); do
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
    case "$1" in
        no-pr-*|*-under-pty) export FAKE_FINALIZE=1 ;;
        *) unset FAKE_FINALIZE ;;
    esac
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
# Opt-in PR journal: only when FAKE_PR_PHASE is set (FAKE_PR_RAW overrides the
# content wholesale; FAKE_PR_BRANCH adds a branch field).
if [[ -n "${FAKE_PR_RAW+x}" ]]; then
    mkdir -p .uncle/workflow/pr
    printf '%s' "$FAKE_PR_RAW" > .uncle/workflow/pr/journal.json
elif [[ -n "${FAKE_PR_REAL_WRITER:-}" ]]; then
    # The journal comes from the real writer: the engine embedded in
    # lib/change-pr.sh, its record_pr and save run unmodified. Only the
    # earlier-stage field (head_branch) is seeded, as the engine's own
    # `start`/bind steps record it before a PR exists.
    python3 -I - "$ENGINE_SRC" "$(git branch --show-current)" "${FAKE_PR_URL:-https://github.com/owner/repo/pull/1}" <<'WPY'
import sys
src = open(sys.argv[1]).read().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
ns = {}
exec(src[:src.rindex('\ntry:\n    main()')], ns)
ns['record_pr']({'head_branch': sys.argv[2], 'phase': 'published'}, {'url': sys.argv[3], 'number': 1})
WPY
elif [[ -n "${FAKE_PR_PHASE:-}" ]]; then
    mkdir -p .uncle/workflow/pr
    # Field names as the real writer (lib/change-pr.sh) records them: phase,
    # url, head_branch; pr_url and branch are the plan's names, emitted too so
    # either validator spelling sees this run's branch.
    jb="${FAKE_PR_BRANCH:-$(git branch --show-current)}"
    jtarget=.uncle/workflow/pr/journal.json
    if [[ -n "${FAKE_PR_SYMLINK:-}" ]]; then jtarget=.uncle/workflow/pr/real.json; fi
    printf '{"phase":"%s","url":"%s","pr_url":"%s","branch":"%s","head_branch":"%s"}\n' "$FAKE_PR_PHASE" "${FAKE_PR_URL-https://github.com/owner/repo/pull/1}" "${FAKE_PR_URL-https://github.com/owner/repo/pull/1}" "$jb" "$jb" > "$jtarget"
    if [[ -n "${FAKE_PR_SYMLINK:-}" ]]; then ln -s real.json .uncle/workflow/pr/journal.json; fi
fi
# The real PR step commits its work; do the same so the tree is clean.
if [[ -n "${FAKE_PR_PHASE:-}${FAKE_PR_RAW+x}${FAKE_PR_REAL_WRITER:-}" ]]; then
    git add -A && git -c commit.gpgsign=false commit --no-gpg-sign -q -m "fake driver work" || true
    # The real PR step pushes, which records the remote-tracking ref.
    if [[ -z "${FAKE_NO_REMOTE_REF:-}" ]]; then
        git update-ref "refs/remotes/origin/$(git branch --show-current)" HEAD
    fi
    # A commit made after the push: on the branch, not on the remote.
    if [[ -n "${FAKE_UNPUSHED:-}" ]]; then
        echo later > later.txt
        git add -A && git -c commit.gpgsign=false commit --no-gpg-sign -q -m "unpushed" || true
    fi
fi
if [[ -n "${FAKE_DIRTY:-}" ]]; then echo dirty >> hello.txt; fi
if [[ -n "${FAKE_UNTRACKED:-}" ]]; then echo stray > untracked-file.txt; fi
if [[ -n "${FAKE_IGNORED:-}" ]]; then
    echo '*.ignored' >> "$(git rev-parse --git-path info/exclude)"
    echo junk > only.ignored
fi
if [[ -n "${FAKE_DRIVER_SLEEP:-}" ]]; then sleep "$FAKE_DRIVER_SLEEP"; fi
# Issue 141: a COMPLETE run with no PR is now committed, removed and switched.
# Older cases that predate that and only exercise creation/guards keep their
# kept-worktree shape because the source checkout is left dirty here; cases that
# test finalization set FAKE_FINALIZE=1 (see new_case) to skip this.
if [[ -z "${FAKE_FINALIZE:-}" ]]; then
    echo stray > "$(dirname "$(git rev-parse --git-common-dir)")/.main-dirty-by-fixture"
fi
# Test-only hook: run a command that changes the source checkout mid-run.
if [[ -n "${FAKE_SOURCE_HOOK:-}" ]]; then eval "$FAKE_SOURCE_HOOK"; fi
printf 'end\t%s\n' "$(date +%s)" >> "$DRIVER_LOG"
if [[ -z "${FAKE_KEEP_LOCK:-}" ]]; then rmdir .uncle/workflow/lock; fi
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
    # Matches what _ensure_uncle_gitignored (uncle_tui.py) writes on a
    # project's first run: a generated REQUIREMENTS.md/CHANGE_REQUEST.md
    # under .uncle/docs stays tracked, so worktree removal's git-native
    # dirty check still sees an unused one.
    printf '.uncle/*\n!.uncle/docs/\n' > "$PROJ/.gitignore"
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
check "CHANGE_REQUEST.md seeded in the worktree" test -s "$WT/.uncle/docs/CHANGE_REQUEST.md"
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
check "worktree 42 request is not 43's" bash -c '! grep -q "Add widget 43" "$1/.uncle/docs/CHANGE_REQUEST.md" && grep -q "Add widget 42" "$1/.uncle/docs/CHANGE_REQUEST.md"' _ "$W42"
check "worktree 43 request is not 42's" bash -c '! grep -q "Add widget 42" "$1/.uncle/docs/CHANGE_REQUEST.md" && grep -q "Add widget 43" "$1/.uncle/docs/CHANGE_REQUEST.md"' _ "$W43"

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
# A dirty COMPLETE worktree: git's own refusal, dir kept. (No-PR finalization
# now commits run output, so dirty the tracked file here after the run.)
echo dirty-after-run >> "$W43/hello.txt"
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
check "CHANGE_REQUEST.md in the worktree" test ! -s "$PROJ/.uncle/docs/CHANGE_REQUEST.md"
check "driver args unchanged" test "$(driver_field args)" == "--unattended"

# --no-worktree is the opt-out, and keeps everything where it was.
new_case no-worktree-opt-out
run_issue /dev/null 42 --change --no-worktree --unattended
expect_status 0
check "driver cwd is the project" test "$(driver_field cwd)" == "$(cd "$PROJ" && pwd -P)"
check "driver root is the project" test "$(driver_field root)" == "$PROJ"
check "driver args unchanged" test "$(driver_field args)" == "--unattended"
check "CHANGE_REQUEST.md in the project" test -s "$PROJ/.uncle/docs/CHANGE_REQUEST.md"
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
# Issue 141: no PR means no prompt; the run is finalized (committed, removed, switched).
expect_not_out "Remove worktree"
expect_not_out "[y/N]"
expect_not_out "PTY TIMEOUT"
expect_out "Branch feat/add-widget-42: worktree removed; project switched."
check "worktree removed without a prompt" test ! -e "$CASE/proj-issue-42"

new_case unattended-under-pty
(cd "$PROJ" && env UNCLE_PROJECT_ROOT="$PROJ" GH_LOG_FILE="$GH_LOG" DRIVER_LOG="$DRIVER_LOG" \
    python3 "$TMP/pty-run.py" bash "$INSTALL/scripts/from-issue.sh" 42 --worktree --unattended > "$OUT" 2>&1)
RC=$?
expect_status 0
expect_not_out "Remove worktree"
expect_out "Branch feat/add-widget-42: worktree removed; project switched."
expect_not_out "kept; remove with"
check "driver got --unattended" test "$(driver_field args)" == "--unattended"
check "worktree removed" test ! -e "$CASE/proj-issue-42"

# Driver failure: existing message, no offer.
new_case driver-fails-no-offer
(cd "$PROJ" && env UNCLE_PROJECT_ROOT="$PROJ" GH_LOG_FILE="$GH_LOG" DRIVER_LOG="$DRIVER_LOG" FAKE_DRIVER_EXIT=3 \
    python3 "$TMP/pty-run.py" bash "$INSTALL/scripts/from-issue.sh" 42 --worktree > "$OUT" 2>&1)
RC=$?
expect_status 3
expect_out "change-workflow.sh exited 3"
expect_not_out "Remove worktree"

# ---------------------------------------------------------------------------
# Auto-removal after a created PR (Issue 119).
# ---------------------------------------------------------------------------

pr_run() {
    # pr_run <mode>: unattended | pty | pipe; env FAKE_* passes through.
    case "$1" in
        unattended)
            run_issue /dev/null 42 --worktree --unattended ;;
        pty)
            (cd "$PROJ" && env UNCLE_PROJECT_ROOT="$PROJ" GH_LOG_FILE="$GH_LOG" DRIVER_LOG="$DRIVER_LOG" \
                python3 "$TMP/pty-run.py" bash "$INSTALL/scripts/from-issue.sh" 42 --worktree > "$OUT" 2>&1)
            RC=$? ;;
        pipe)
            run_issue /dev/null 42 --worktree ;;
    esac
}

expect_removed() {
    expect_status 0
    expect_out "Removed worktree $CASE/proj-issue-42 (branch kept)"
    expect_not_out "kept; remove with"
    expect_not_out "Keeping worktree"
    expect_not_out "Remove worktree"
    check "worktree dir removed" test ! -e "$CASE/proj-issue-42"
    check "branch kept" branch_exists feat/add-widget-42
}

expect_kept() {
    check "worktree dir kept" test -d "$CASE/proj-issue-42"
    expect_not_out "Removed worktree"
}

expect_kept_at() {
    check "worktree dir kept at $1" test -d "$1"
    expect_not_out "Removed worktree"
    expect_not_out "Remove worktree"
    expect_out "scripts/lib/worktrees.sh remove"
}

for mode in unattended pty pipe; do
    new_case pr-created-removes-$mode
    FAKE_PR_PHASE=created pr_run $mode
    expect_removed
done

new_case pr-created-driver-fails-keeps
FAKE_PR_PHASE=created FAKE_DRIVER_EXIT=3 pr_run unattended
expect_status 3
expect_kept

new_case pr-created-not-complete-keeps
FAKE_PR_PHASE=created FAKE_STATE=IMPLEMENT pr_run unattended
expect_kept

new_case pr-no-journal-keeps
pr_run unattended
expect_status 0
expect_kept

new_case pr-phase-not-created-keeps
FAKE_PR_PHASE=pending pr_run unattended
expect_status 0
expect_kept

new_case pr-malformed-journal-keeps
FAKE_PR_RAW='{not json' pr_run unattended
expect_status 0
expect_kept

new_case pr-journal-not-object-keeps
FAKE_PR_RAW='["created"]' pr_run unattended
expect_status 0
expect_kept

for u in "" "not-a-url" "https://github.com/o/r/issues/5" "http://github.com/owner/repo/pull/1"; do
    new_case "pr-bad-url-keeps-${u:-empty}"
    FAKE_PR_PHASE=created FAKE_PR_URL="$u" pr_run unattended
    expect_status 0
    expect_kept
done

new_case pr-branch-mismatch-keeps
FAKE_PR_PHASE=created FAKE_PR_BRANCH=other/branch pr_run unattended
expect_status 0
expect_kept

# A journal left by an earlier run of the same worktree is not this run's PR.
new_case pr-stale-journal-keeps
run_issue /dev/null 42 --worktree
expect_status 0
WT="$CASE/proj-issue-42"
printf '42:WAIT_UPDATED_PLAN_APPROVAL\n' > "$WT/.uncle/workflow/state"
rm -f "$WT/.uncle/workflow/origin"
mkdir -p "$WT/.uncle/workflow/pr"
printf '{"phase":"created","url":"https://github.com/owner/repo/pull/1"}\n' > "$WT/.uncle/workflow/pr/journal.json"
run_issue /dev/null 42 --worktree --unattended
expect_status 0
expect_kept

new_case pr-rewritten-journal-removes
run_issue /dev/null 42 --worktree
expect_status 0
WT="$CASE/proj-issue-42"
printf '42:WAIT_UPDATED_PLAN_APPROVAL\n' > "$WT/.uncle/workflow/state"
rm -f "$WT/.uncle/workflow/origin"
mkdir -p "$WT/.uncle/workflow/pr"
printf '{"phase":"created","url":"https://github.com/owner/repo/pull/1"}\n' > "$WT/.uncle/workflow/pr/journal.json"
FAKE_PR_PHASE=created FAKE_PR_URL=https://github.com/owner/repo/pull/2 run_issue /dev/null 42 --worktree --unattended
expect_removed

# Refusal: a dirty worktree is kept with the reason and the kept line.
new_case pr-created-dirty-refused
FAKE_PR_PHASE=created FAKE_DIRTY=1 run_issue /dev/null 42 --worktree --unattended
expect_status 0
expect_kept
expect_out "Worktree $CASE/proj-issue-42 kept; remove with: scripts/lib/worktrees.sh remove"
# Fixture shape: modified tracked file, no untracked files, pushed HEAD.
check "tracked change is the only dirt" test "$(g -C "$CASE/proj-issue-42" status --porcelain | grep -vc '^ M ')" == 0
check "tracked file is modified" test -n "$(g -C "$CASE/proj-issue-42" status --porcelain | grep '^ M hello.txt')"
check "HEAD is pushed (no unpushed commits)" test -z "$(g -C "$CASE/proj-issue-42" rev-list HEAD --not --remotes)"
check "branch survives the refusal" branch_exists feat/add-widget-42
expect_not_out "Removed worktree"
expect_not_out "Remove worktree"

# Untracked file: refused, no prompt in either mode, status unchanged.
for mode in unattended pty; do
    new_case pr-created-untracked-refused-$mode
    FAKE_PR_PHASE=created FAKE_UNTRACKED=1 pr_run $mode
    expect_status 0
    expect_kept
    expect_not_out "Remove worktree"
    expect_out "scripts/lib/worktrees.sh remove"
done

# Refusal never changes a non-zero run status.
new_case pr-created-dirty-refused-nonzero-status
FAKE_PR_PHASE=created FAKE_DIRTY=1 FAKE_DRIVER_EXIT=3 pr_run unattended
expect_status 3
expect_kept

# Refusal in attended mode: no prompt either.
new_case pr-created-dirty-refused-pty
FAKE_PR_PHASE=created FAKE_DIRTY=1 pr_run pty
expect_status 0
expect_kept
expect_not_out "Remove worktree"
expect_out "scripts/lib/worktrees.sh remove"

# Byte-identical rewrite of a pre-existing journal is stale (resume rule).
new_case pr-identical-rewrite-keeps
run_issue /dev/null 42 --worktree
expect_status 0
WT="$CASE/proj-issue-42"
printf '42:WAIT_UPDATED_PLAN_APPROVAL\n' > "$WT/.uncle/workflow/state"
rm -f "$WT/.uncle/workflow/origin"
mkdir -p "$WT/.uncle/workflow/pr"
SAMEJ='{"phase":"created","url":"https://github.com/owner/repo/pull/1"}'
printf '%s' "$SAMEJ" > "$WT/.uncle/workflow/pr/journal.json"
FAKE_PR_RAW="$SAMEJ" run_issue /dev/null 42 --worktree --unattended
expect_status 0
expect_kept

# Foreign-repo PR URL: not this project's PR.
new_case pr-foreign-repo-keeps
FAKE_PR_PHASE=created FAKE_PR_URL=https://github.com/other/thing/pull/1 pr_run unattended
expect_status 0
expect_kept

# URL shapes that must not match exactly.
for u in "https://github.com/owner/repo/pull/1/" "https://github.com/owner/repo/pull/1?x=1" "https://github.com/owner/repo/pull/1/files"; do
    new_case "pr-url-shape-keeps-$(printf '%s' "$u" | tr -c 'A-Za-z0-9' '_')"
    FAKE_PR_PHASE=created FAKE_PR_URL="$u" pr_run unattended
    expect_status 0
    expect_kept
done

# Missing url field.
new_case pr-missing-url-keeps
FAKE_PR_RAW='{"phase":"created"}' pr_run unattended
expect_status 0
expect_kept

# Symlinked journal file / pr directory: no valid evidence.
new_case pr-symlink-journal-keeps
FAKE_PR_PHASE=created FAKE_PR_SYMLINK=1 pr_run unattended
expect_status 0
expect_kept

new_case pr-symlink-dir-keeps
run_issue /dev/null 42 --worktree
expect_status 0
WT="$CASE/proj-issue-42"
printf '42:WAIT_UPDATED_PLAN_APPROVAL\n' > "$WT/.uncle/workflow/state"
rm -f "$WT/.uncle/workflow/origin"
mkdir -p "$CASE/elsewhere-pr"
printf '{"phase":"created","url":"https://github.com/owner/repo/pull/9"}\n' > "$CASE/elsewhere-pr/journal.json"
ln -s "$CASE/elsewhere-pr" "$WT/.uncle/workflow/pr"
run_issue /dev/null 42 --worktree --unattended
expect_status 0
expect_kept

# The journal is produced by the real PR writer (record_pr/save from
# lib/change-pr.sh, executed), so a writer/validator field or phase mismatch
# fails here: the worktree must be removed on that journal alone.
new_case pr-real-writer-journal-removes
FAKE_PR_REAL_WRITER=1 pr_run unattended
expect_status 0
expect_removed

new_case pr-real-writer-journal-pty-removes
FAKE_PR_REAL_WRITER=1 pr_run pty
expect_status 0
expect_removed
expect_not_out "Remove worktree"

# Unpushed commit on an otherwise clean worktree: kept, reason and command
# printed, no prompt, status unchanged.
for mode in unattended pty; do
    new_case pr-created-unpushed-refused-$mode
    FAKE_PR_PHASE=created FAKE_UNPUSHED=1 pr_run $mode
    expect_status 0
    expect_kept
    expect_not_out "Remove worktree"
    expect_out "not pushed to a remote"
    expect_out "scripts/lib/worktrees.sh remove"
done
new_case pr-created-unpushed-refused-nonzero-status
FAKE_PR_PHASE=created FAKE_UNPUSHED=1 FAKE_DRIVER_EXIT=3 pr_run unattended
expect_status 3
expect_kept

# Path guard (AC-4): outside the managed root (the project's parent directory).
new_case pr-worktree-outside-managed-root-keeps
mkdir -p "$TMP/outside-$$"
FAKE_PR_PHASE=created run_issue /dev/null 42 --worktree-dir "$TMP/outside-$$/wt" --unattended
expect_status 0
expect_kept_at "$TMP/outside-$$/wt"
expect_out "outside the managed worktrees root"

# Path guard: a worktree path that is itself a symlink to a registered worktree.
new_case pr-worktree-symlink-dir-keeps
run_issue /dev/null 42 --worktree
expect_status 0
WT="$CASE/proj-issue-42"
ln -s "$WT" "$CASE/wtlink"
printf '42:WAIT_UPDATED_PLAN_APPROVAL\n' > "$WT/.uncle/workflow/state"
rm -f "$WT/.uncle/workflow/origin"
FAKE_PR_PHASE=created run_issue /dev/null 42 --worktree-dir "$CASE/wtlink" --unattended
expect_status 0
expect_kept
expect_out "the worktree path is a symlink"
expect_out "scripts/lib/worktrees.sh remove"

# Guard function directly: worktree equal to / containing the source checkout
# (also through a symlink) and an unresolvable path are all refused.
new_case guard-source-equal-contain
g -C "$PROJ" init -q 2>/dev/null
guard() { (STAGEGATE_FROM_ISSUE_SOURCE_ONLY=1 . "$INSTALL/scripts/from-issue.sh"; auto_removal_refusal "$1" "$2") 2>&1; }
guard_says() { local want="$1"; shift; [[ "$(guard "$@")" == *"$want"* ]]; }
ln -s "$PROJ" "$CASE/srclink"
mkdir -p "$PROJ/inner" "$CASE/inner-wt"
g -C "$CASE/inner-wt" init -q -b main
g -C "$CASE/inner-wt" -c user.name=t -c user.email=t@t commit --no-gpg-sign -q --allow-empty -m x
g -C "$CASE/inner-wt" update-ref refs/remotes/origin/main HEAD
check "worktree == source refused" guard_says "is the source checkout" "$PROJ" "$PROJ"
check "worktree via symlink to source refused" guard_says "is the source checkout" "$CASE/srclink" "$PROJ"
check "worktree containing source refused" guard_says "contains the source checkout" "$CASE" "$PROJ"
check "unresolvable worktree refused" guard_says "cannot be resolved" "$CASE/nope" "$PROJ"
check "unresolvable source refused" guard_says "cannot be resolved" "$PROJ/inner" "$CASE/nope"
check "valid sibling worktree gives no refusal" test -z "$(guard "$CASE/inner-wt" "$PROJ")"

# Guard definition: a gitignored file is not an untracked file, so a pushed
# worktree holding only ignored files is removed.
new_case pr-created-ignored-file-only-removes
FAKE_PR_PHASE=created FAKE_IGNORED=1 pr_run unattended
expect_removed

# Guard definition: no remote-tracking ref at all means HEAD is unpushed.
new_case pr-created-no-remote-refs-keeps
FAKE_PR_PHASE=created FAKE_NO_REMOTE_REF=1 pr_run unattended
expect_status 0
expect_kept
expect_out "not pushed to a remote"
expect_out "scripts/lib/worktrees.sh remove"
expect_not_out "Remove worktree"
check "no remote refs in the fixture" test -z "$(g -C "$CASE/proj-issue-42" for-each-ref refs/remotes)"

# ---------------------------------------------------------------------------
# Issue 141: no-PR finalization (S-1..S-9). Fake driver leaves state COMPLETE.
# ---------------------------------------------------------------------------

NW="proj-issue-42"
RB=feat/add-widget-42
src_branch() { g -C "$PROJ" branch --show-current; }
log_has_commit() { local l; l="$(g -C "$1" log --format=%s "$RB" 2>&1)"; [[ "$l" == *"uncle: issue 42 change"* ]]; }
summary() { expect_out "Branch $RB: worktree $1; project $2."; }

new_case no-pr-switches
FAKE_UNTRACKED=1 FAKE_DIRTY=1 run_issue /dev/null 42 --worktree --unattended
expect_status 0
summary removed switched
expect_not_out "Remove worktree"
check "worktree removed" test ! -e "$CASE/$NW"
check "commit made on run branch" log_has_commit "$PROJ"
check "main switched to run branch" test "$(src_branch)" == "$RB"
check "untracked output visible in main" test -f "$PROJ/untracked-file.txt"
check "tracked change visible in main" grep -q dirty "$PROJ/hello.txt"
check "driver state not committed" bash -c '! git -C "$1" ls-tree -r --name-only "$2" | grep -q "^.uncle/workflow"' _ "$PROJ" "$RB"

new_case no-pr-clean-tree-no-commit
run_issue /dev/null 42 --worktree --unattended
expect_status 0
summary removed switched
check "main on run branch" test "$(src_branch)" == "$RB"

new_case no-pr-dirty-main-keeps
FAKE_UNTRACKED=1 FAKE_SOURCE_HOOK='echo local >> "$FAKE_SRC/hello.txt"' FAKE_SRC="$PROJ" \
    run_issue /dev/null 42 --worktree --unattended
expect_status 0
summary kept "not switched"
expect_out "git switch $RB"
expect_out "scripts/lib/worktrees.sh remove"
check "worktree kept" test -d "$CASE/$NW"
check "work committed on the branch" log_has_commit "$PROJ"
check "main not switched" test "$(src_branch)" == main

new_case no-pr-other-branch-keeps
FAKE_SOURCE_HOOK='g() { git -c commit.gpgsign=false "$@"; }; g -C "$FAKE_SRC" switch -q -c other && echo o > "$FAKE_SRC/o.txt" && g -C "$FAKE_SRC" add o.txt && g -C "$FAKE_SRC" commit --no-gpg-sign -q -m other' \
    FAKE_SRC="$PROJ" run_issue /dev/null 42 --worktree --unattended
expect_status 0
summary kept "not switched"
expect_out "git switch $RB"
check "worktree kept" test -d "$CASE/$NW"
check "main still on other" test "$(src_branch)" == other

new_case no-pr-failed-removal-keeps
FAKE_KEEP_LOCK=1 run_issue /dev/null 42 --worktree --unattended
expect_status 0
summary kept "not switched"
expect_out "scripts/lib/worktrees.sh remove"
check "worktree kept" test -d "$CASE/$NW"
check "main not switched" test "$(src_branch)" == main

new_case no-pr-switch-fails-after-removal
mkdir -p "$CASE/hooks"
printf '#!/bin/sh\n[ -e "%s" ] && exit 1\nexit 0\n' "$CASE/fail-switch" > "$CASE/hooks/post-checkout"
chmod +x "$CASE/hooks/post-checkout"
g -C "$PROJ" config core.hooksPath "$CASE/hooks"
FAKE_SOURCE_HOOK='touch "$FAKE_FLAG"' FAKE_FLAG="$CASE/fail-switch" run_issue /dev/null 42 --worktree --unattended
expect_status 0
summary removed "not switched"
expect_out "git switch $RB"
check "worktree removed" test ! -e "$CASE/$NW"
check "branch intact" branch_exists "$RB"

new_case no-pr-commit-fails-keeps
mkdir -p "$CASE/hooks"
printf '#!/bin/sh\nexit 1\n' > "$CASE/hooks/pre-commit"
chmod +x "$CASE/hooks/pre-commit"
g -C "$PROJ" config core.hooksPath "$CASE/hooks"
FAKE_UNTRACKED=1 run_issue /dev/null 42 --worktree --unattended
expect_status 0
summary kept "not switched"
expect_out "Commit failed"
expect_out "scripts/lib/worktrees.sh remove"
check "worktree kept" test -d "$CASE/$NW"
check "no commit made" bash -c '! git -C "$1" log --format=%s "$2" | grep -qx "uncle: issue 42 change"' _ "$PROJ" "$RB"

# No-PR finalization: an unreachable source (cd fails) keeps the worktree and
# prints the keep summary and remove command; nothing is committed or removed.
new_case no-pr-unreachable-source-keeps
WT="$CASE/proj-issue-42"
g -C "$PROJ" worktree add -q -b feat/unreachable-42 "$WT"
mkdir -p "$WT/.uncle/workflow"; echo "42:COMPLETE" > "$WT/.uncle/workflow/state"
echo new > "$WT/new-file.txt"
head_before="$(g -C "$WT" rev-parse HEAD)"
(STAGEGATE_FROM_ISSUE_SOURCE_ONLY=1 . "$INSTALL/scripts/from-issue.sh"
 # Only the function's own cd (same process) fails; path resolution runs in
 # command-substitution subshells and still resolves the source.
 SRC_UNREACH="$PROJ"; MAIN_SUB="$BASH_SUBSHELL"
 cd() { [[ "${1:-}" == "$SRC_UNREACH" && "$BASH_SUBSHELL" == "$MAIN_SUB" ]] && return 1; builtin cd "$@"; }
 finalize_no_pr_worktree "$WT" "$PROJ") > "$OUT" 2>&1
RC=$?
expect_status 0
check "worktree kept when source unreachable" test -d "$WT"
check "no commit made when source unreachable" test "$(g -C "$WT" rev-parse HEAD)" = "$head_before"
expect_out "the source checkout is unreachable"
expect_out "Branch feat/unreachable-42: worktree kept; project not switched."
expect_out "scripts/lib/worktrees.sh remove $WT"

# The printed manual remove command must be runnable as written.
check "scripts/lib/worktrees.sh is executable (printed command is runnable)" test -x "$ROOT/scripts/lib/worktrees.sh"

# Main checkout dirty only by an untracked file: kept, not switched, file intact.
new_case no-pr-untracked-main-keeps
FAKE_SOURCE_HOOK='echo local > "$FAKE_SRC/local-untracked.txt"' FAKE_SRC="$PROJ" \
    run_issue /dev/null 42 --worktree --unattended
expect_status 0
summary kept "not switched"
expect_out "git switch $RB"
check "worktree kept" test -d "$CASE/$NW"
check "main not switched" test "$(src_branch)" == main
check "untracked file intact" test "$(cat "$PROJ/local-untracked.txt")" == local
check "exactly one summary line" test "$(grep -c "^Branch $RB: worktree" "$OUT")" == 1

# Detached source HEAD: kept, never switched, detached position preserved.
new_case no-pr-detached-main-keeps
FAKE_SOURCE_HOOK='git -C "$FAKE_SRC" checkout -q --detach' FAKE_SRC="$PROJ" \
    run_issue /dev/null 42 --worktree --unattended
expect_status 0
summary kept "not switched"
expect_out "not on a named branch"
expect_out "git switch $RB"
check "worktree kept" test -d "$CASE/$NW"
check "source still detached" test -z "$(src_branch)"

# Source already on the run branch (worktree has nothing to commit, so the
# source stays clean): switch skipped, reported as switched, worktree removed.
new_case no-pr-already-on-run-branch
WT="$CASE/proj-issue-42"
g -C "$PROJ" worktree add -q -b "$RB" "$WT"
mkdir -p "$WT/.uncle/workflow"; echo "42:COMPLETE" > "$WT/.uncle/workflow/state"
g -C "$PROJ" switch -q --ignore-other-worktrees "$RB"
(STAGEGATE_FROM_ISSUE_SOURCE_ONLY=1 . "$INSTALL/scripts/from-issue.sh"
 finalize_no_pr_worktree "$WT" "$PROJ") > "$OUT" 2>&1
RC=$?
expect_status 0
summary removed switched
check "worktree removed" test ! -e "$WT"
check "main on run branch" test "$(src_branch)" == "$RB"
check "exactly one summary line" test "$(grep -c "^Branch $RB: worktree" "$OUT")" == 1

# No-PR run whose driver exits non-zero: status propagated, nothing finalized.
new_case no-pr-driver-fails-nothing-finalized
FAKE_UNTRACKED=1 FAKE_DRIVER_EXIT=3 run_issue /dev/null 42 --worktree --unattended
expect_status 3
expect_not_out "Branch $RB: worktree"
check "worktree kept" test -d "$CASE/$NW"
check "no commit made" bash -c '! git -C "$1" log --format=%s "$2" | grep -qx "uncle: issue 42 change"' _ "$PROJ" "$RB"
check "main not switched" test "$(src_branch)" == main

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
