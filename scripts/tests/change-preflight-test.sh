#!/usr/bin/env bash
# The change driver probes prerequisites like stagegate.sh: deterministic runtime probes beside implementation, collected before the implementation gate.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CW="$ROOT/scripts/change-workflow.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }

fn() { awk -v n="$1" '$0 ~ "^"n"\\(\\) \\{" {p=1} p {print} p && /^}/ {exit}' "$CW"; }
FUNCS="$(fn change_preflight_run; fn change_preflight_collect)"
[[ -n "$FUNCS" ]] || bad "could not extract the functions"

n=0
newproject() {
    project="$work/p$((++n))"; mkdir -p "$project/.uncle/workflow/documents" "$project/.uncle/workflow/logs" "$project/.uncle/docs"
}
run_in() {   # <project> <script> [PATH override via ENVPATH]
    local project="$1"; shift
    ( cd "$project" && env -i PATH="${ENVPATH:-$PATH}" HOME="$HOME" "$(command -v bash)" --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='.uncle/workflow'; LOG_DIR='.uncle/workflow/logs'
        verify_commands() { cat commands.txt; }
        snapshot_preflight_capabilities() { echo snapshot >> .uncle/workflow/events; }
        record_nonblocking_failure() { echo \"nonblocking:\$1\" >> .uncle/workflow/events; }
        supervision_validation_failed() { echo \"supervision:\$1\" >> .uncle/workflow/events; }
        $FUNCS
        $*" 2>&1 )
}
result() { python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$1/.uncle/workflow/documents/PREFLIGHT_REPORT.json"; }

# --- the probe passes for commands whose runtimes exist, with no model call -----------------------------------------------------------------
newproject; printf 'echo hello\ntrue\n' > "$project/commands.txt"
out="$(run_in "$project" 'change_preflight_run; echo rc=$?')"
grep -q 'rc=0' <<< "$out" || bad "the probe failed for commands that need nothing: $out"
eq "the report passes" "$(result "$project")" PASS
[[ -s "$project/.uncle/docs/PREFLIGHT_REPORT.md" ]] || bad "the report was not rendered"

# --- a missing runtime is a BLOCKED-SETUP row for the audit, not a crash -------------------------------------------------------------------
newproject; printf 'node build.js\n' > "$project/commands.txt"
bindir="$work/bin$n"; mkdir -p "$bindir"; for t in python3 tr cat rm awk sed; do ln -sf "$(command -v $t)" "$bindir/$t"; done
out="$(ENVPATH="$bindir" run_in "$project" 'change_preflight_run; echo rc=$?')"
grep -q 'rc=0' <<< "$out" || bad "an unresolved probe must still leave a valid report: $out"
eq "a missing runtime is BLOCKED-SETUP" "$(result "$project")" BLOCKED-SETUP
grep -q 'Missing runtime: node' "$project/.uncle/workflow/documents/PREFLIGHT_REPORT.json" || bad "the report does not say which runtime is missing"

# --- no verification commands: nothing to probe, and that is not a failure ------------------------------------------------------------------
newproject; : > "$project/commands.txt"
run_in "$project" 'change_preflight_run' > /dev/null
eq "an empty command list is N/A" "$(python3 -c "import json;print(json.load(open('$project/.uncle/workflow/documents/PREFLIGHT_REPORT.json'))['rows'][0]['status'])")" 'N/A'

# --- collection: a pass is quiet, anything else is ledgered for the audit and never stops the run ----------------------------------------
newproject; printf 'true\n' > "$project/commands.txt"
run_in "$project" 'change_preflight_run' > /dev/null
: > "$project/.uncle/workflow/preflight-backgrounded"; echo 0 > "$project/.uncle/workflow/preflight-bg.status"
out="$(run_in "$project" 'change_preflight_collect; echo rc=$?')"
grep -q 'Prerequisites confirmed' <<< "$out" && grep -q 'rc=0' <<< "$out" || bad "a passing probe should be confirmed: $out"
grep -q 'nonblocking' "$project/.uncle/workflow/events" && bad "a pass was ledgered as a failure"
grep -q snapshot "$project/.uncle/workflow/events" || bad "the capabilities were not published for the checklist"
[[ ! -e "$project/.uncle/workflow/preflight-backgrounded" ]] || bad "the background marker was left behind"

newproject; printf 'node build.js\n' > "$project/commands.txt"
ENVPATH="$bindir" run_in "$project" 'change_preflight_run' > /dev/null
: > "$project/.uncle/workflow/preflight-backgrounded"; echo 0 > "$project/.uncle/workflow/preflight-bg.status"
out="$(run_in "$project" 'change_preflight_collect; echo rc=$?')"
grep -q 'rc=0' <<< "$out"                                    || bad "an unconfirmed probe must not stop the run: $out"
grep -q 'nonblocking:PREFLIGHT_REPORT.json' "$project/.uncle/workflow/events" || bad "an unconfirmed probe was not ledgered for the audit"
grep -q 'supervision:preflight' "$project/.uncle/workflow/events" || bad "an unconfirmed probe was not reported to the supervisor"

newproject
out="$(run_in "$project" 'change_preflight_collect; echo rc=$?')"
grep -q 'rc=0' <<< "$out" && [[ ! -e "$project/.uncle/workflow/events" ]] || bad "with no probe started there is nothing to collect: $out"

# --- the driver runs the probe after plan approval and before implementation, and collects it at the gate ------------------------------
grep -q 'set_state PREFLIGHT$' "$CW" || bad "plan approval does not go to PREFLIGHT"
pf="$(awk '/^        PREFLIGHT\)/{p=1;next} p&&/^        [A-Z_]+\)$/{exit} p{print}' "$CW")"
grep -q 'set_state MODULE_INTERFACES' <<< "$pf" || bad "PREFLIGHT does not lead on to MODULE_INTERFACES"
grep -q 'change_preflight_run' <<< "$pf" || bad "PREFLIGHT does not run the probe"
awk '/^        WAIT_IMPLEMENT_APPROVAL\)/{p=1;next} p&&/^        [A-Z_]+\)$/{exit} p{print}' "$CW" | grep -q 'change_preflight_collect' || bad "the implementation gate does not collect the probe"
[[ $fail == 0 ]] && echo "change-preflight-test.sh: ok"
exit $fail
