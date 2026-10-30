#!/usr/bin/env bash
# --unattended: the gates pass without a person, and the run says so.
#
# The point of these checks is not that the flag works. It is that the flag
# stays honest: an unattended gate must still attest to the real bytes, must
# leave a record that nobody read them, and must never turn a waived check
# into a passing one. A flag that quietly produced clean-looking runs would be
# worse than no flag at all.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PASS=0
FAIL=0

ok()   { PASS=$((PASS + 1)); }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2" >&2; }
check() { # check <name> <expected> <actual>
    if [[ "$2" == "$3" ]]; then ok; else bad "$1" "expected '$2', got '$3'"; fi
}

. "$ROOT/scripts/tests/workflow_fixture.sh"

# --- argument handling ------------------------------------------------------

check "sg-version-flag" "0.1.0" "$(bash "$ROOT/scripts/stagegate.sh" --version)"
if bash "$ROOT/scripts/stagegate.sh" --unattended --bogus > /dev/null 2>&1; then
    bad "sg-unknown-arg" "an unknown argument after --unattended was accepted"
else
    ok
fi
for driver in stagegate change-workflow; do
    if bash "$ROOT/scripts/$driver.sh" --help | grep -q -- "--unattended"; then ok
    else bad "$driver-help" "--unattended is not documented in --help"; fi
done

# --- stagegate review_and_approve -------------------------------------------

sg="$WORK/sg"
mkdir -p "$sg/.uncle/workflow/approvals"
extract_fns "$ROOT/scripts/stagegate.sh" "$sg/driver-fns.sh" require_file canonical_artifact_path approval_artifact_path review_and_approve
workflow_fixture_write "$sg/fns.sh" "$ROOT/scripts/lib/prompt-io.sh" "$ROOT/scripts/lib/prompt-io-app.sh" "$ROOT/scripts/lib/workflow-records.sh" "$sg/driver-fns.sh"
cat > "$sg/gate.sh" <<'HARNESS'
#!/usr/bin/env bash
set -euo pipefail
STATE_DIR="$PWD/.uncle/workflow"
APPROVAL_DIR="$STATE_DIR/approvals"
UNATTENDED_FILE="$STATE_DIR/unattended-gates"
hash_file() { shasum -a 256 "$1" | awk '{print $1}'; }
cancel_speculation() { echo "CANCEL_SPECULATION"; }
. ./fns.sh
review_and_approve "$@"
echo "GATE_RETURNED"
HARNESS
cp "$sg/fns.sh" "$sg/fns.sh.bak"
printf 'plan body\n' > "$sg/PLAN.md"

# Unattended, with stdin closed. Closed stdin is the real unattended
# condition: if any read survived, this hangs or exits down the decline path.
out="$(cd "$sg" && ROOT="$ROOT" UNATTENDED=1 bash gate.sh PLAN.md PROJECT_PLAN approve < /dev/null 2>&1)"
case "$out" in
    *GATE_RETURNED*) ok ;;
    *) bad "sg-unattended-returns" "gate did not return: $out" ;;
esac
case "$out" in
    *"no human review"*) ok ;;
    *) bad "sg-unattended-says-so" "output does not say it was unreviewed: $out" ;;
esac
# The recorded digest must be the file's real digest: later stages compare
# against it, and an approval attesting to nothing is worse than no approval.
want="$(shasum -a 256 "$sg/PLAN.md" | awk '{print $1}')"
check "sg-digest-real" "$want" "$(cat "$sg/.uncle/workflow/approvals/PROJECT_PLAN.sha256")"
if grep -q "PROJECT_PLAN" "$sg/.uncle/workflow/unattended-gates"; then ok
else bad "sg-ledger" "the gate was not written to the unattended ledger"; fi

# The prompt must never appear: a run nobody is watching should not be waiting.
case "$out" in
    *"HUMAN REVIEW REQUIRED"*) bad "sg-no-prompt" "the human prompt was printed anyway" ;;
    *) ok ;;
esac

# Attended runs are untouched, and write no ledger.
rm -f "$sg/.uncle/workflow/unattended-gates" "$sg/.uncle/workflow/approvals/PROJECT_PLAN.sha256"
out="$(cd "$sg" && ROOT="$ROOT" UNATTENDED=0 bash gate.sh PLAN.md PROJECT_PLAN approve <<< "$(printf '\ny\n')" 2>&1)"
case "$out" in
    *"HUMAN REVIEW REQUIRED"*) ok ;;
    *) bad "sg-attended-prompts" "the human gate did not prompt: $out" ;;
esac
if [[ -e "$sg/.uncle/workflow/unattended-gates" ]]; then
    bad "sg-attended-ledger" "an attended approval was written to the unattended ledger"
else ok; fi

# --- waivers ----------------------------------------------------------------

wv="$WORK/wv"
mkdir -p "$wv/.uncle/workflow"
# The waiver writers moved to a shared lib so both drivers use one copy.
# Keep the two modules explicit while the driver functions await extraction.
extract_fns "$ROOT/scripts/lib/waivers.sh" "$wv/fns-waivers.sh" write_waivers record_waiver
workflow_fixture_write "$wv/fns.sh" "$ROOT/scripts/lib/prompt-io.sh" "$ROOT/scripts/lib/workflow-records.sh" "$wv/fns-waivers.sh"
cat > "$wv/gate.sh" <<'HARNESS'
#!/usr/bin/env bash
set -euo pipefail
ROOT="/nonexistent-so-the-popup-is-skipped"
STATE_DIR="$PWD/.uncle/workflow"
UNATTENDED_FILE="$STATE_DIR/unattended-gates"
# One-liner in the driver, so it is restated rather than extracted.
waive_file() { printf '%s/waivers/%s' "$STATE_DIR" "$1"; }
. ./fns.sh
record_waiver "$@"
echo "WAIVER_RETURNED"
HARNESS
printf '# report\n' > "$wv/REPORT.md"

out="$(cd "$wv" && ROOT="$ROOT" UNATTENDED=1 bash gate.sh REPORT.md PR-09 PR-10 < /dev/null 2>&1)"
case "$out" in
    *WAIVER_RETURNED*) ok ;;
    *) bad "wv-returns" "record_waiver did not return: $out" ;;
esac
for id in PR-09 PR-10; do
    f="$wv/.uncle/workflow/waivers/$id"
    if [[ -s "$f" ]]; then ok; else bad "wv-file-$id" "no waiver written for $id"; continue; fi
    # The reason must name the unattended run. An audit reading this later has
    # to be able to tell "nobody assessed it" from "someone decided it was ok".
    if grep -q "unattended run" "$f"; then ok
    else bad "wv-reason-$id" "waiver does not say it was unattended: $(cat "$f")"; fi
    if grep -q "^id: $id" "$f"; then ok; else bad "wv-id-$id" "waiver does not name its id"; fi
done
# A waiver is not a pass, and nothing here may claim otherwise.
if grep -rqi "pass" "$wv/.uncle/workflow/waivers/"; then
    bad "wv-not-a-pass" "a waiver file uses the word pass"
else ok; fi

# --- change-workflow human_gate ---------------------------------------------

cw="$WORK/cw"
mkdir -p "$cw/.uncle/workflow/approvals"
extract_fns "$ROOT/scripts/change-workflow.sh" "$cw/driver-fns.sh" require_file canonical_artifact_path approval_artifact_path human_gate
workflow_fixture_write "$cw/fns.sh" "$ROOT/scripts/lib/prompt-io.sh" "$ROOT/scripts/lib/prompt-io-change.sh" "$ROOT/scripts/lib/workflow-records.sh" "$cw/driver-fns.sh"
cat > "$cw/gate.sh" <<'HARNESS'
#!/usr/bin/env bash
set -euo pipefail
STATE_DIR="$PWD/.uncle/workflow"
APPROVAL_DIR="$STATE_DIR/approvals"
UNATTENDED_FILE="$STATE_DIR/unattended-gates"
hash_file() { shasum -a 256 "$1" | awk '{print $1}'; }
show_spend() { :; }
. ./fns.sh
human_gate "$@"
echo "GATE_RETURNED"
HARNESS
printf 'spec body\n' > "$cw/SPEC.md"
printf 'plan body\n' > "$cw/PLAN.md"

out="$(cd "$cw" && ROOT="$ROOT" UNATTENDED=1 bash gate.sh APPROVE SPEC.md CHANGE_SPEC PLAN.md CHANGE_PLAN < /dev/null 2>&1)"
case "$out" in
    *GATE_RETURNED*) ok ;;
    *) bad "cw-returns" "human_gate did not return: $out" ;;
esac
# Multi-document gates must record every document, not just the first.
for pair in "SPEC.md:CHANGE_SPEC" "PLAN.md:CHANGE_PLAN"; do
    f="${pair%%:*}"; n="${pair##*:}"
    want="$(shasum -a 256 "$cw/$f" | awk '{print $1}')"
    check "cw-digest-$n" "$want" "$(cat "$cw/.uncle/workflow/approvals/$n.sha256" 2>/dev/null || echo MISSING)"
    if grep -q "$n" "$cw/.uncle/workflow/unattended-gates"; then ok
    else bad "cw-ledger-$n" "$n missing from the unattended ledger"; fi
done

# --- change-workflow implementation_incomplete_choice -----------------------
# Mid-IMPLEMENT gates, not the well-known start-of-run plan approvals -- the
# regression this covers had no test at all, so `--unattended` blocked here
# with stdin closed instead of continuing the run.

ic="$WORK/ic"
mkdir -p "$ic/.uncle/workflow/approvals"
extract_fns "$ROOT/scripts/change-workflow.sh" "$ic/driver-fns.sh" implementation_incomplete_choice
extract_fns "$ROOT/scripts/lib/waivers.sh" "$ic/fns-waivers.sh" write_waivers record_waiver
workflow_fixture_write "$ic/fns.sh" "$ROOT/scripts/lib/prompt-io.sh" "$ROOT/scripts/lib/workflow-records.sh" "$ic/driver-fns.sh" "$ic/fns-waivers.sh"
cat > "$ic/gate.sh" <<'HARNESS'
#!/usr/bin/env bash
set -euo pipefail
ROOT="/nonexistent-so-the-popup-is-skipped"
STATE_DIR="$PWD/.uncle/workflow"
APPROVAL_DIR="$STATE_DIR/approvals"
UNATTENDED_FILE="$STATE_DIR/unattended-gates"
waive_file() { printf '%s/waivers/%s' "$STATE_DIR" "$1"; }
envelope_invalidate() { :; }
set_state() { :; }
. ./fns.sh
status=0
implementation_incomplete_choice || status=$?
echo "CHOICE_RETURNED $status"
HARNESS

# Prompt #1: an unevaluable (malformed) acceptance contract. Unattended must
# repair it (return 3) rather than wait -- the rebuilt spec/plan still pass
# through human_gate's own unattended path, so nothing here skips review.
printf 'not a well formed row\n' > "$ic/.uncle/workflow/implementation-completion.txt"
touch "$ic/.uncle/workflow/approvals/CHANGE_SPEC.sha256" "$ic/.uncle/workflow/approvals/CHANGE_PLAN.sha256"
out="$(cd "$ic" && ROOT="$ROOT" UNATTENDED=1 bash gate.sh < /dev/null 2>&1)"
check "ic-malformed-returns" "CHOICE_RETURNED 3" "$(printf '%s' "$out" | grep CHOICE_RETURNED)"
if [[ -e "$ic/.uncle/workflow/approvals/CHANGE_SPEC.sha256" ]]; then
    bad "ic-malformed-clears-approval" "the stale CHANGE_SPEC approval was not cleared"
else ok; fi
case "$out" in
    *"repair"*"the acceptance contract"*"[repair/stop]"*) bad "ic-malformed-no-prompt" "the human prompt was printed anyway" ;;
    *) ok ;;
esac
if grep -q "implementation-incomplete" "$ic/.uncle/workflow/unattended-gates" 2>/dev/null; then ok
else bad "ic-malformed-ledger" "the repair decision was not written to the unattended ledger"; fi

# Prompt #2: well-formed rows rejected after one automatic repair already ran.
# Unattended must waive (return 2, terminating) rather than auto-retry, which
# would hit this same unbounded choice again next time with nobody there.
rm -f "$ic/.uncle/workflow/unattended-gates"
printf 'AC-1: requires IMPLEMENTED, changed code, and observed targeted verification; got missing\n' \
    > "$ic/.uncle/workflow/implementation-completion.txt"
out="$(cd "$ic" && ROOT="$ROOT" UNATTENDED=1 bash gate.sh < /dev/null 2>&1)"
check "ic-rejected-returns" "CHOICE_RETURNED 2" "$(printf '%s' "$out" | grep CHOICE_RETURNED)"
case "$out" in
    *"Retry the implementation, waive"*) bad "ic-rejected-no-prompt" "the human prompt was printed anyway" ;;
    *) ok ;;
esac
w="$ic/.uncle/workflow/waivers/AC-1"
if [[ -s "$w" ]]; then ok; else bad "ic-waiver-file" "no waiver written for AC-1"; fi
if grep -q "unattended run" "$w" 2>/dev/null; then ok
else bad "ic-waiver-reason" "waiver does not say it was unattended"; fi

# issue 97: a lettered sub-criterion (AC-4b) is an ordinary rejected row, not
# a malformed contract -- it must waive (return 2) the same as AC-1 above, not
# fall into the "cannot be evaluated" full-restart branch (return 3).
rm -f "$ic/.uncle/workflow/unattended-gates" "$ic/.uncle/workflow/waivers/AC-1"
printf 'AC-4b: requires IMPLEMENTED, changed code, and observed targeted verification; got missing\n' \
    > "$ic/.uncle/workflow/implementation-completion.txt"
out="$(cd "$ic" && ROOT="$ROOT" UNATTENDED=1 bash gate.sh < /dev/null 2>&1)"
check "ic-lettered-id-returns" "CHOICE_RETURNED 2" "$(printf '%s' "$out" | grep CHOICE_RETURNED)"
case "$out" in
    *"cannot be evaluated"*) bad "ic-lettered-id-not-malformed" "AC-4b was wrongly treated as a malformed contract" ;;
    *) ok ;;
esac
if [[ -s "$ic/.uncle/workflow/waivers/AC-4b" ]]; then ok
else bad "ic-lettered-id-waiver-file" "no waiver written for AC-4b"; fi

# Prompt #3: no rejected rows at all -- the implementation delivered nothing,
# so implementation-completion.txt was never written. There is nothing on the
# record to waive. Unattended used to call record_waiver with no ids, which
# died on bash 3.2's `ids[@]: unbound variable`; it must stop pending instead.
rm -rf "$ic/.uncle/workflow/unattended-gates" "$ic/.uncle/workflow/waivers" \
    "$ic/.uncle/workflow/implementation-completion.txt"
out="$(cd "$ic" && ROOT="$ROOT" UNATTENDED=1 bash gate.sh < /dev/null 2>&1)" || true
check "ic-no-rows-returns" "CHOICE_RETURNED 1" "$(printf '%s' "$out" | grep CHOICE_RETURNED)"
case "$out" in
    *"unbound variable"*) bad "ic-no-rows-crash" "the empty waiver crashed the driver" ;;
    *"waiving rejected rows"*) bad "ic-no-rows-no-waiver" "an empty set of rows was announced as waived" ;;
    *) ok ;;
esac
if [[ -e "$ic/.uncle/workflow/waivers" ]]; then bad "ic-no-rows-no-waiver-file" "a waiver was written with no rows"
else ok; fi

# --- the issue stays open ---------------------------------------------------

# Closing the originating issue announces outside the repository that this
# change was accepted. Unattended, nobody accepted it.
if grep -q 'the issue remains open' "$ROOT/scripts/change-workflow.sh"; then ok
else bad "cw-issue-open" "completion must leave the issue open"; fi

# --- Issue 107: unattended COMPLETE is dialog-free and publishes nothing ----
# Run each driver's production COMPLETE arm with stdin closed. git and gh are
# PATH shims that record the call and fail: any commit/push/PR attempt is a defect.
for driver in stagegate change-workflow; do
    d="$WORK/fin-$driver"
    mkdir -p "$d/.uncle/workflow" "$d/bin"
    for tool in git gh; do
        printf '#!/bin/sh\n[ "$1" = rev-parse ] && exit 0\necho "$0 $*" >> "%s/calls.log"\nexit 1\n' "$d" > "$d/bin/$tool"
        chmod +x "$d/bin/$tool"
    done
    if [[ "$driver" == stagegate ]]; then col=1; else col=2; fi
    extract_fns "$ROOT/scripts/$driver.sh" "$d/driver-fns.sh" completed_verdict
    workflow_fixture_write "$d/fns.sh" "$ROOT/scripts/lib/workflow-records.sh" "$d/driver-fns.sh"
    arm="$d/arm.sh"
    awk '/^        COMPLETE\)$/ {p = 1; next} p && /^        \*\)$/ {exit} p {print}' "$ROOT/scripts/$driver.sh" > "$arm"
    cat > "$d/run.sh" <<HARNESS
set -uo pipefail
ROOT='$ROOT'
PROJECT_ROOT='$d'
STATE_DIR='$d/.uncle/workflow'
VERDICT_FILE="\$STATE_DIR/audit-verdict"
UNATTENDED_FILE="\$STATE_DIR/unattended-gates"
AUDIT_OVERRIDE_FILE="\$STATE_DIR/audit-override"
GREEN_OVERRIDE_FILE="\$STATE_DIR/green-override"
LEDGER_FILE="\$STATE_DIR/ledger"
ORIGIN_FILE="\$STATE_DIR/origin"
DIFF_FILE=DIFF
GREEN_MD=GREEN
UNATTENDED=\${UNATTENDED:-0}
triage_print_actions() { :; }
change_pr_complete() { echo "change_pr_complete CALLED"; git commit --no-gpg-sign; }
. "\$(dirname "\$0")/fns.sh"
$(cat "$arm")
HARNESS
    printf '%s\tNOT_READY\tabc\n' "x" > "$d/.uncle/workflow/audit-verdict"
    if [[ "$col" == 1 ]]; then printf 'NOT_READY\tabc\n' > "$d/.uncle/workflow/audit-verdict.original"
    else printf -- '-\tNOT_READY\tabc\n' > "$d/.uncle/workflow/audit-verdict.original"; fi
    if [[ "$col" == 1 ]]; then printf 'READY\tabc\n' > "$d/.uncle/workflow/audit-verdict"
    else printf -- '-\tREADY\tabc\n' > "$d/.uncle/workflow/audit-verdict"; fi
    for id in FA-1 FA-2; do
        printf '2026-01-01T00:00:00Z\taudit-finding-skipped\t%s accepted without human review (audit abc)\n' "$id" >> "$d/.uncle/workflow/unattended-gates"
    done
    out="$(cd "$d" && UNATTENDED=1 PATH="$d/bin:$PATH" python3 "$ROOT/scripts/tests/run_with_timeout.py" 60 bash "$d/run.sh" < /dev/null 2>&1)"; rc=$?
    check "$driver-unattended-complete-rc" "0" "$rc"
    if grep -qF "Finished build: verdict=READY skipped=2 path=$d" <<< "$out"; then ok
    else bad "$driver-finished-line" "golden Finished line missing: $out"; fi
    if grep -qF "READY - 2 blocking findings WAIVED WITHOUT HUMAN REVIEW (the auditor said NOT READY)" <<< "$out"; then ok
    else bad "$driver-not-ready-marker" "marker missing: $out"; fi
    if [[ "$driver" == change-workflow ]]; then
        # Issue 107 follow-up: an unattended change run hands off to the PR
        # publisher, which publishes with no dialog (a draft unless READY).
        if grep -q "change_pr_complete CALLED" <<< "$out" && grep -q "Built in $d" <<< "$out"; then ok
        else bad "cw-unattended-publishes" "unattended change run did not reach the PR publisher or say where it built: $out"; fi
    elif [[ -e "$d/calls.log" ]] || grep -q "CALLED" <<< "$out"; then
        bad "$driver-no-publish" "git/gh/PR handoff invoked unattended: $(cat "$d/calls.log" 2>/dev/null) $out"
    else ok; fi
    # Attended: no Finished line; the PR handoff still runs (change-workflow).
    out="$(cd "$d" && UNATTENDED=0 PATH="$d/bin:$PATH" python3 "$ROOT/scripts/tests/run_with_timeout.py" 60 bash "$d/run.sh" < /dev/null 2>&1)" || true
    if grep -q "Finished build:" <<< "$out"; then bad "$driver-attended-silent" "attended run printed the unattended line"; else ok; fi
    if [[ "$driver" == change-workflow ]]; then
        if grep -q "change_pr_complete CALLED" <<< "$out"; then ok
        else bad "cw-attended-handoff" "attended run no longer reaches the PR handoff: $out"; fi
    fi
done

# Source-level guard: the unattended audit branch passes the flag and closes stdin.
for driver in stagegate change-workflow; do
    if grep -q 'audit-findings.py" "$STATE_DIR/documents/FINAL_AUDIT.json" "$STATE_DIR" --unattended --ledger "$UNATTENDED_FILE" </dev/null' "$ROOT/scripts/$driver.sh"; then ok
    else bad "$driver-audit-flag" "unattended audit branch missing"; fi
done

# An attended run with nobody setting WORKFLOW_AUTO_REPAIR_ATTEMPTS stays at
# 0 (stop and let the person decide); unattended has nobody to ask, so the
# first ordinary code defect must not end the run for good with zero attempt
# to self-heal.
snippet="$(sed -n '/^WORKFLOW_CONTINUE_ON_TEST_FAILURE=/,/^esac$/p' "$ROOT/scripts/stagegate.sh")"
for case in "0 0" "1 2"; do
    set -- $case
    out="$(UNATTENDED="$1" bash -c "$snippet"$'\n''echo "$WORKFLOW_AUTO_REPAIR_ATTEMPTS"')"
    check "auto-repair-attempts-default-unattended=$1" "$2" "$out"
done
# An explicit setting is never overridden by the unattended default.
out="$(UNATTENDED=1 WORKFLOW_AUTO_REPAIR_ATTEMPTS=5 bash -c "$snippet"$'\n''echo "$WORKFLOW_AUTO_REPAIR_ATTEMPTS"')"
check "auto-repair-attempts-explicit-setting-kept" "5" "$out"

# test-review, manual-checklist, and execute-checklist exist to route a real
# defect back to REPAIR, not to be rubber-stamped at the end -- an unattended
# NOT READY audit must spend its bounded repair budget once before
# audit-findings.py --unattended gets anywhere near waiving a finding nobody
# looked at. But unattended mode has no person to do manual/visual testing by
# definition, so a NOT READY whose only cause is that absence (no driver-
# observed regression, just an unobserved human-only check) is not a defect a
# repair pass could fix; that one still goes straight to the existing waiver.
d="$WORK/audit-repair-routes-first"
mkdir -p "$d/.uncle/workflow/documents"
echo '{"schema":"uncle.artifact/v1","kind":"final-audit","verdict":"NOT READY","findings":[
    {"id":"FA-1","severity":"CRITICAL","evidence":"crash","required_correction":"fix it","blocks":"YES"}]}' \
    > "$d/.uncle/workflow/documents/FINAL_AUDIT.json"
cp "$ROOT/scripts/lib/audit-verdict.sh" "$d/fns.sh"
arm="$d/arm.sh"
awk '/^        WAIT_AUDIT_OVERRIDE\)$/ {p = 1; next} p && /^        COMPLETE\)$/ {exit} p {print}' \
    "$ROOT/scripts/stagegate.sh" > "$arm"
for scenario in first-attempt budget-exhausted human-only; do
    d2="$d/$scenario"; mkdir -p "$d2/.uncle/workflow/documents"
    cp "$d/.uncle/workflow/documents/FINAL_AUDIT.json" "$d2/.uncle/workflow/documents/"
    hash="$(cd "$d2" && . "$ROOT/scripts/lib/sha256.sh" && hash_file .uncle/workflow/documents/FINAL_AUDIT.json)"
    printf 'NOT_READY\t%s\n' "$hash" > "$d2/.uncle/workflow/audit-verdict"
    [[ "$scenario" == budget-exhausted ]] && printf '1' > "$d2/.uncle/workflow/repair-count"
    # A clean driver-executed suite (no REGRESSION rows): the only thing
    # NOT READY could be citing is something nobody automated could check.
    if [[ "$scenario" == human-only ]]; then
        printf 'PASS\tnpm test\n' > "$d2/.uncle/workflow/green-check.tsv"
    else
        printf 'REGRESSION\tnpm test\n' > "$d2/.uncle/workflow/green-check.tsv"
    fi
    cat > "$d2/run.sh" <<HARNESS
set -uo pipefail
ROOT='$ROOT'
STATE_DIR='$d2/.uncle/workflow'
VERDICT_FILE="\$STATE_DIR/audit-verdict"
STATE_FILE="\$STATE_DIR/state"
UNATTENDED_FILE="\$STATE_DIR/unattended-gates"
AUDIT_OVERRIDE_FILE="\$STATE_DIR/audit-override"
GREEN_CHECK=1
GREEN_CLASS="\$STATE_DIR/green-check.tsv"
WORKFLOW_AUTO_REPAIR=1
WORKFLOW_AUTO_REPAIR_ATTEMPTS=1
UNATTENDED=1
. "\$ROOT/scripts/lib/sha256.sh"
. "\$ROOT/scripts/lib/green-check.sh"
require_file() { [[ -s "\$1" ]] || { echo "MISSING: \$1"; exit 1; }; }
set_state() { echo "SET_STATE \$1"; }
. "$d/fns.sh"
# The real driver's \`continue\` returns to \`case "\$state" in\` in an
# enclosing \`while true\`; this isolated arm has no such loop, so a bare
# \`continue\` here would be a no-op and fall straight into the code the
# routing decision was meant to skip. One real iteration gives it a loop
# to actually continue out of, matching what \`continue\` does for real.
# The extracted arm's own trailing ;; needs a case around it, same as it
# has in the real state machine, not just the loop.
for __once in once; do
case 1 in
1)
$(cat "$arm")
esac
done
HARNESS
    out="$(cd "$d2" && python3 "$ROOT/scripts/tests/run_with_timeout.py" 30 bash "$d2/run.sh" < /dev/null 2>&1)"
    if [[ "$scenario" == first-attempt ]]; then
        if grep -q '^SET_STATE REPAIR$' <<< "$out"; then ok
        else bad "audit-repair-routes-first" "did not route to REPAIR on a driver-observed regression: $out"; fi
        if [[ "$(cat "$d2/.uncle/workflow/repair-source" 2>/dev/null)" == .uncle/docs/FINAL_AUDIT.md ]]; then ok
        else bad "audit-repair-source" "repair-source was not set to FINAL_AUDIT.md"; fi
        if grep -q 'WAIVED WITHOUT HUMAN REVIEW' <<< "$out"; then
            bad "audit-repair-no-waiver-yet" "waived before spending the repair budget: $out"
        else ok; fi
    elif [[ "$scenario" == budget-exhausted ]]; then
        if grep -q '^SET_STATE REPAIR$' <<< "$out"; then
            bad "audit-repair-budget-exhausted" "routed to REPAIR again after the budget was spent: $out"
        else ok; fi
        if grep -q 'SET_STATE COMPLETE' <<< "$out"; then ok
        else bad "audit-repair-falls-back-to-waiver" "did not fall back to the unattended waiver once repair was spent: $out"; fi
    else
        if grep -q '^SET_STATE REPAIR$' <<< "$out"; then
            bad "audit-repair-skips-human-only" "routed a human-testing-only NOT READY to REPAIR with no driver-observed regression: $out"
        else ok; fi
        if grep -q 'SET_STATE COMPLETE' <<< "$out"; then ok
        else bad "audit-human-only-still-completes" "a NOT READY with no driver-observed regression did not still reach COMPLETE: $out"; fi
    fi
done

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "unattended-test.sh: $FAIL of $((PASS + FAIL)) checks FAILED"
    exit 1
fi
echo "unattended-test.sh: $PASS checks passed -- gates pass without a person, attest to real bytes, record what went unreviewed, and never read as passes"
