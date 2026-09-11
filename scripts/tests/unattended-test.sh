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

extract_fns() {
    local script="$1" out="$2"
    shift 2
    : > "$out"
    local fn
    for fn in "$@"; do
        awk -v fn="$fn" '
            $0 == fn "() {" { p = 1 }
            p { print }
            p && /^\}$/ { exit }
        ' "$script" >> "$out"
        printf '\n' >> "$out"
    done
    for fn in "$@"; do
        grep -q "^${fn}() {" "$out" || { echo "FATAL: could not extract $fn"; exit 2; }
    done
}

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
extract_fns "$ROOT/scripts/stagegate.sh" "$sg/fns.sh" \
    gate_prompt legacy_word_notice upper lower require_file \
    record_unattended_gate review_and_approve
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
out="$(cd "$sg" && UNATTENDED=1 bash gate.sh PLAN.md PROJECT_PLAN approve < /dev/null 2>&1)"
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
out="$(cd "$sg" && UNATTENDED=0 bash gate.sh PLAN.md PROJECT_PLAN approve <<< "$(printf '\ny\n')" 2>&1)"
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
extract_fns "$ROOT/scripts/stagegate.sh" "$wv/fns.sh" \
    gate_prompt record_unattended_gate write_waivers record_waiver
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

out="$(cd "$wv" && UNATTENDED=1 bash gate.sh REPORT.md PR-09 PR-10 < /dev/null 2>&1)"
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
extract_fns "$ROOT/scripts/change-workflow.sh" "$cw/fns.sh" \
    gate_prompt legacy_word_notice require_file record_unattended_gate human_gate
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

out="$(cd "$cw" && UNATTENDED=1 bash gate.sh APPROVE SPEC.md CHANGE_SPEC PLAN.md CHANGE_PLAN < /dev/null 2>&1)"
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

# --- the issue stays open ---------------------------------------------------

# Closing the originating issue announces outside the repository that this
# change was accepted. Unattended, nobody accepted it.
if grep -q 'the issue remains open' "$ROOT/scripts/change-workflow.sh"; then ok
else bad "cw-issue-open" "completion must leave the issue open"; fi

echo
if [[ "$FAIL" -gt 0 ]]; then
    echo "unattended-test.sh: $FAIL of $((PASS + FAIL)) checks FAILED"
    exit 1
fi
echo "unattended-test.sh: $PASS checks passed -- gates pass without a person, attest to real bytes, record what went unreviewed, and never read as passes"
