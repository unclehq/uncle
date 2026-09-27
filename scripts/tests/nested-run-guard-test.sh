# worktree-run-test.sh drives worktree creation and from-issue.sh -- the very
# machinery a build runs on. Inside an uncle-builds-uncle run it exercises that
# against a checkout the live run owns and is midway through changing, so the
# result answers nothing: a pass means the machinery worked while being
# rewritten, and a failure cannot be told from the build's own half-applied
# edits. It also hangs to the harness's 600s timeout, which is how the problem
# first showed up.
#
# The detection is environmental, and two earlier attempts were wrong in ways
# that failed silently rather than loudly:
#
#   .uncle/workflow/lock  change-workflow.sh defines acquire_lock() and never
#                         calls it, so that path is never created.
#   UNCLE_PROJECT_ROOT    stripped from the environment before a stage runs.
#
# So this pins the signals that do exist, and pins the negative cases just as
# hard: a suite that skips when it could have run is a test nobody notices has
# stopped testing anything.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUITE="$ROOT/scripts/tests/worktree-run-test.sh"
work="$(mktemp -d)"
LIVE=""
trap 'if [[ -n "$LIVE" ]]; then kill "$LIVE" 2>/dev/null; fi; rm -rf "$work"' EXIT

FAILED=0
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
note() { echo "  ok: $1"; }
fail() { echo "  FAIL: $1" >&2; FAILED=1; }

# The guard exits before the suite does any work, so proving it let something
# through needs only a couple of seconds -- not a full battery run, which would
# call a loaded machine a failure.
verdict() {
    local code
    env -u UNCLE_UNATTENDED -u UNCLE_STATUS_STAGE -u UNCLE_TEST_ALLOW_NESTED "$@" \
        timeout 6 bash "$SUITE" > "$work/out" 2>&1
    code=$?
    if [[ "$code" == 77 ]]; then echo skipped; else echo ran; fi
}

# Set by both drivers, unconditionally, for the life of a build.
[[ "$(verdict UNCLE_UNATTENDED=0)" == skipped ]] \
    && note 'UNCLE_UNATTENDED skips' || fail 'UNCLE_UNATTENDED did not skip'
# Note 0, not 1: an attended build is still a build, and the value carries no
# meaning here beyond "a driver set this".
[[ "$(verdict UNCLE_UNATTENDED=1)" == skipped ]] \
    && note 'UNCLE_UNATTENDED=1 skips too' || fail 'unattended build did not skip'

# Set whenever a stage starts, by both drivers.
[[ "$(verdict UNCLE_STATUS_STAGE=change-plan)" == skipped ]] \
    && note 'UNCLE_STATUS_STAGE skips' || fail 'UNCLE_STATUS_STAGE did not skip'

env -u UNCLE_UNATTENDED -u UNCLE_TEST_ALLOW_NESTED UNCLE_STATUS_STAGE=change-plan \
    timeout 6 bash "$SUITE" > "$work/out" 2>&1
grep -q 'stage change-plan' "$work/out" \
    && note 'the message names the stage' || fail 'message does not name the stage'
grep -q 'UNCLE_TEST_ALLOW_NESTED=1' "$work/out" \
    && note 'the message names the override' || fail 'message hides the override'
grep -q 'mean nothing' "$work/out" \
    && note 'the message says why, not just that' || fail 'message gives no reason'

# The override wins over both signals.
[[ "$(verdict UNCLE_UNATTENDED=0 UNCLE_TEST_ALLOW_NESTED=1)" == ran ]] \
    && note 'UNCLE_TEST_ALLOW_NESTED=1 forces a run' || fail 'the override did not force a run'

# A developer's shell has no UNCLE_ variables, and must not be skipped -- a
# suite that skips when it could have run stops testing anything, quietly.
[[ "$(verdict)" == ran ]] \
    && note 'a plain shell runs the suite' || fail 'a plain shell was skipped'

# Neither signal can be left behind by a killed run: both live in the process
# environment. An unrelated UNCLE_ variable is not evidence of a live build.
[[ "$(verdict UNCLE_LIB_DIR=/tmp/whatever)" == ran ]] \
    && note 'an unrelated UNCLE_ variable does not skip' || fail 'skipped on an unrelated variable'

if [[ "$FAILED" == 0 ]]; then
    echo 'nested-run-guard-test.sh: skipped only while a build drives, and never otherwise'
else
    echo 'nested-run-guard-test.sh: FAILED' >&2
fi
exit "$FAILED"
