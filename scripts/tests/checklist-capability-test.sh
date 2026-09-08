#!/usr/bin/env bash
# The gate that stops before a checklist its runner cannot execute.
#
# The property under test is that it never waves a stage through on a
# capability the runner does not have, and never blocks one it does: a false
# stop costs a run, a false pass costs a report full of BLOCKED rows that no
# repair can clear.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/stage-config.sh"
. "$ROOT/scripts/lib/checklist-capability.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
STATE_DIR="$work/workflow"
mkdir -p "$STATE_DIR/checklist-groups"
RES="$STATE_DIR/checklist-groups/resources.tsv"
UNCLE_CONFIG="$work/config"
: > "$UNCLE_CONFIG"

fail() { echo "FAIL: $1" >&2; exit 1; }
eq() { [ "$2" = "$3" ] || fail "$1: expected '$3', got '$2'"; }

# --- what a token means ------------------------------------------------------
for token in port:8000 port-8000 localhost:3000 server socket bind http; do
    eq "$token is a port need" "$(checklist_capability_of "$token")" port
done
for token in browser:system browser:safari chrome-user-profile gui display \
             screen clipboard keyboard print-dialog mail-client window zoom; do
    eq "$token is a gui need" "$(checklist_capability_of "$token")" gui
done
for token in reviewer:brian human sign-off approval; do
    eq "$token needs a person" "$(checklist_capability_of "$token")" human
done
# Ordinary state is isolated by the grouping and asks nothing of the machine.
for token in db mutate-runner tree:worktree git-clone-dir fixture; do
    eq "$token needs no capability" "$(checklist_capability_of "$token")" ""
done

# --- what a runner can do ----------------------------------------------------
checklist_runner_provides port codex false  && fail 'sandboxed codex cannot bind'
checklist_runner_provides port codex true   || fail 'codex with network can bind'
checklist_runner_provides gui  codex true   && fail 'no setting gives codex a screen'
for runner in claude cline kimi; do
    checklist_runner_provides port "$runner" false || fail "$runner can bind"
    checklist_runner_provides gui  "$runner" false || fail "$runner can drive a gui"
done
checklist_runner_provides human claude false && fail 'no runner is a person'

# --- the gaps a real checklist produces --------------------------------------
{
    printf 'port:8000\tMC-1,MC-2,MC-18\n'
    printf 'browser:system\tMC-1,MC-2\n'
    printf 'reviewer:brian\tMC-26\n'
    printf 'mutate-runner\tMC-29\n'
} > "$RES"

gaps="$(checklist_capability_gaps "$RES" codex false)"
grep -q '^port' <<< "$gaps"  || fail 'a sandboxed codex stage must report the port gap'
grep -q '^gui'  <<< "$gaps"  || fail 'a codex stage must report the gui gap'
grep -q 'human' <<< "$gaps"  && fail 'a human row is never a gap: no runner can close it'
grep -q 'mutate-runner' <<< "$gaps" && fail 'ordinary state is not a capability gap'
# The count is distinct checks, not tokens: three checks need the port.
eq "port gap counts checks" "$(grep '^port' <<< "$gaps" | cut -f2)" 3

gaps="$(checklist_capability_gaps "$RES" codex true)"
grep -q '^port' <<< "$gaps" && fail 'network true closes the port gap'
grep -q '^gui'  <<< "$gaps" || fail 'network true does not give codex a screen'

eq "an unsandboxed runner has no gaps" "$(checklist_capability_gaps "$RES" claude false)" ""

# --- the dialog --------------------------------------------------------------
gate_prompt() { printf '%s' "$1"; }

printf 'execute-checklist.runner codex\n' > "$UNCLE_CONFIG"
out="$(ensure_checklist_runner execute-checklist < /dev/null 2>&1)" && status=0 || status=$?
[ "$status" != 0 ] || fail 'EOF must leave the run pending, not run the stage'
grep -q 'needs more than this stage.s runner can do' <<< "$out" || fail 'the dialog must say what is wrong'
grep -q 'MC-1' <<< "$out" || fail 'the dialog must name the checks that cannot run'
grep -q 'Configure' <<< "$out" || fail 'the dialog must say where to change it'

out="$(ensure_checklist_runner execute-checklist <<< 'stop' 2>&1)" && status=0 || status=$?
[ "$status" != 0 ] || fail 'declining must leave the run pending'

# 'run' is an explicit override: the operator wants the BLOCKED rows recorded.
out="$(ensure_checklist_runner execute-checklist <<< 'run' 2>&1)" && status=0 || status=$?
[ "$status" = 0 ] || fail "'run' must proceed"
grep -q 'record BLOCKED' <<< "$out" || fail "'run' must say what it is accepting"

# 're-read' is the path the dialog exists for: the operator changes the runner
# in another window, and the answer comes from the file, not from this loop.
cat > "$work/fix.sh" <<'FIX'
printf 'execute-checklist.runner claude\n' > "$UNCLE_CONFIG"
FIX
printf 'execute-checklist.runner codex\n' > "$UNCLE_CONFIG"
out="$( { printf 'r\n'; . "$work/fix.sh"; printf 'r\n'; } | ensure_checklist_runner execute-checklist 2>&1 )" \
    && status=0 || status=$?
[ "$status" = 0 ] || fail 're-reading a fixed config must run the stage'
grep -q 'need a person' <<< "$out" || fail 'the human-only rows must still be announced'

# A runner that can do everything is not interrupted at all.
printf 'execute-checklist.runner claude\n' > "$UNCLE_CONFIG"
out="$(ensure_checklist_runner execute-checklist < /dev/null 2>&1)" || fail 'a capable runner must not be gated'
grep -q 'needs more than' <<< "$out" && fail 'a capable runner must not see the dialog'

# codex plus the network setting: the port gap closes, the gui gap does not.
printf 'execute-checklist.runner codex\nexecute-checklist.network true\n' > "$UNCLE_CONFIG"
out="$(ensure_checklist_runner execute-checklist < /dev/null 2>&1)" && status=0 || status=$?
[ "$status" != 0 ] || fail 'the gui gap must still stop a codex stage'
grep -q 'no screen' <<< "$out" || fail 'the dialog must explain the gui gap'
grep -q 'must bind a local port' <<< "$out" && fail 'the port gap is closed by network true'

# --- other people's machines -------------------------------------------------
# This has to run on Windows, and on a Mac without Chrome. The platform probe
# and the app probe are the two things that vary, so override them and check
# the conclusions rather than the machine this test happens to run on.

installed=""            # the set of apps the fake machine has
checklist_app_present() {
    local candidate
    for candidate in "$@"; do
        case " $installed " in *" $candidate "*) return 0 ;; esac
    done
    return 1
}

# A stock Mac: Safari and the opener, no Chrome.
checklist_platform() { printf 'macos'; }
installed="open /Applications/Safari.app"
eq "stock mac opener" "$(checklist_browser_opener)" open
checklist_browser_present system || fail 'the opener is the system browser'
checklist_browser_present safari || fail 'a Mac has Safari'
checklist_browser_present chrome && fail 'Chrome is a download, not a given'

# The same Mac once Chrome is installed.
installed="open /Applications/Safari.app /Applications/Google Chrome.app"
checklist_browser_present chrome || fail 'an installed Chrome is found'

# Windows: `start` is the opener, Edge is there, Safari can never be.
checklist_platform() { printf 'windows'; }
installed="start msedge.exe"
eq "windows opener" "$(checklist_browser_opener)" start
checklist_browser_present system || fail 'start is the system browser on Windows'
checklist_browser_present edge   || fail 'Edge is present'
checklist_browser_present chrome && fail 'Windows does not ship Chrome'
checklist_browser_present safari && fail 'Safari has never shipped on Windows'
grep -q 'does not exist on this platform' <<< "$(checklist_browser_advice safari)"     || fail 'the advice for Safari off macOS must say it cannot be installed'
grep -q 'CDP' <<< "$(checklist_browser_advice chrome)"     || fail 'the advice for Chrome must name the harness that needs it'

# Linux: xdg-open, and Safari is still impossible.
checklist_platform() { printf 'linux'; }
installed="xdg-open firefox"
eq "linux opener" "$(checklist_browser_opener)" xdg-open
checklist_browser_present firefox || fail 'firefox on the path is found'
checklist_browser_present safari  && fail 'no Safari on Linux'

# --- what a checklist naming an absent browser reports -----------------------
{
    printf 'browser:system\tMC-1,MC-2\n'
    printf 'chrome-user-profile\tMC-1,MC-3\n'
    printf 'browser:safari\tMC-28\n'
} > "$RES"
checklist_platform() { printf 'windows'; }
installed="start msedge.exe"
missing="$(checklist_missing_browsers "$RES")"
grep -q '^chrome' <<< "$missing" || fail 'an absent Chrome must be reported'
grep -q '^safari' <<< "$missing" || fail 'an impossible Safari must be reported'
grep -q '^system' <<< "$missing" && fail 'the opener is present, so system is not missing'
grep -q 'MC-28' <<< "$missing" || fail 'the report must name the checks that cannot run'

# A missing browser alone never blocks the stage: no runner change installs a
# browser, and stopping forever is worse than a report saying which rows fail.
printf 'execute-checklist.runner claude\n' > "$UNCLE_CONFIG"
out="$(ensure_checklist_runner execute-checklist < /dev/null 2>&1)" \
    || fail 'a missing browser must not block a capable runner'
grep -q 'chrome is missing' <<< "$out" || fail 'it must still say what is missing'
grep -q 'not reproducible' <<< "$out" || fail 'it must warn that the default browser is per-user'

# With a real gap, one stop reports both.
printf 'execute-checklist.runner codex\n' > "$UNCLE_CONFIG"
out="$(ensure_checklist_runner execute-checklist <<< 'stop' 2>&1)" && status=0 || status=$?
[ "$status" != 0 ] || fail 'the runner gap still stops the stage'
grep -q 'safari is not installed' <<< "$out" || fail 'the gap dialog must also report missing browsers'

unset -f checklist_platform checklist_app_present
. "$ROOT/scripts/lib/checklist-capability.sh"

# --- nothing declared, nothing to check --------------------------------------
rm -f "$RES"
printf 'execute-checklist.runner codex\n' > "$UNCLE_CONFIG"
ensure_checklist_runner execute-checklist < /dev/null > /dev/null \
    || fail 'a checklist with no declarations cannot be gated on them'

echo 'checklist-capability-test.sh: token classification, runner capability, gaps, and the dialog passed'
