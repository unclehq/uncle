#!/usr/bin/env bash
set -uo pipefail

# Hermetic coverage of the Y/N human-approval gates:
#
#   G1  scripts/workflow.sh    approve_file        (real script, temp checkout)
#   G2  scripts/change-workflow.sh human_gate      (extracted function harness)
#   G3  scripts/stagegate.sh   review_and_approve  (extracted function harness)
#   G4  prompt styling (non-TTY / TERM=dumb / PTY)
#   G5  whitespace strictness
#
# change-workflow.sh and stagegate.sh are state machines that need agent CLIs,
# a lock, and an origin binding before they reach a gate, and neither exposes a
# source-only test hook. Rather than add one (that would widen the change
# surface), G2 and G3 lift the gate function verbatim out of the script with
# awk and run it against the same argument lists as the real call sites. The
# extraction is asserted non-empty and `bash -n`-clean, so a silent extraction
# failure fails the suite instead of passing vacuously.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/sha256.sh"   # hash_file, portable across platforms

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAILED=0
COUNT=0
NOTRUN=0
CASE_NAME=""
CASE=""
REPO=""
OUT=""
RC=0

fail() {
    echo "FAIL [$CASE_NAME] $1"
    FAILED=$((FAILED + 1))
}

notrun() {
    echo "NOT RUN [$CASE_NAME] $1"
    NOTRUN=$((NOTRUN + 1))
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
    if ! grep -qF "$1" "$OUT"; then
        fail "expected output to contain: $1"
        sed 's/^/    /' < "$OUT"
    fi
}

expect_not_out() {
    COUNT=$((COUNT + 1))
    if grep -qF "$1" "$OUT"; then
        fail "expected output NOT to contain: $1"
        sed 's/^/    /' < "$OUT"
    fi
}

# The approval file must hold the exact shasum of the given file's bytes.
expect_hash_of() {
    COUNT=$((COUNT + 1))
    local approval="$1" src="$2" want have
    want="$(hash_file "$src")"
    have="$(cat "$approval" 2>/dev/null)"
    if [[ "$have" != "$want" ]]; then
        fail "approval $approval: expected $want, got '${have}'"
    fi
}

expect_hash_literal() {
    COUNT=$((COUNT + 1))
    local approval="$1" want="$2" have
    have="$(cat "$approval" 2>/dev/null)"
    if [[ "$have" != "$want" ]]; then
        fail "approval $approval: expected $want, got '${have}'"
    fi
}

expect_no_approval() {
    COUNT=$((COUNT + 1))
    if [[ -e "$1" ]]; then
        fail "expected no approval file at $1, got '$(cat "$1")'"
    fi
}

expect_no_ansi() {
    COUNT=$((COUNT + 1))
    if LC_ALL=C grep -q $'\033' "$OUT"; then
        fail "expected no ANSI escape bytes in output"
        LC_ALL=C sed -n 's/\x1b/<ESC>/gp' "$OUT" | sed 's/^/    /'
    fi
}

# ---------------------------------------------------------------------------
# Function extraction harness
# ---------------------------------------------------------------------------

# extract_fns <script> <outfile> <fn>...
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
    if ! grep -q "^${1}() {" "$out"; then
        echo "FATAL: extraction from $script produced no function bodies"
        exit 2
    fi
    for fn in "$@"; do
        if ! grep -q "^${fn}() {" "$out"; then
            echo "FATAL: could not extract $fn from $script"
            exit 2
        fi
    done
    if ! bash -n "$out"; then
        echo "FATAL: extracted functions from $script are not valid bash"
        exit 2
    fi
}

# new_case <name> — scratch working tree with the gated documents present.
new_case() {
    CASE_NAME="$1"
    CASE="$TMP/$1"
    REPO="$CASE/repo"
    OUT="$CASE/out.txt"
    RC=0

    mkdir -p "$REPO/scripts" "$REPO/.uncle/workflow/approvals"
    : > "$OUT"

    local doc
    for doc in BASELINE_REPORT.md CHANGE_SPEC.md CHANGE_PLAN.md \
               ADVERSARIAL_REVIEW.md UPDATED_CHANGE_PLAN.md \
               REQUIREMENTS_INTERPRETATION.md PROJECT_PLAN.md \
               UPDATED_PROJECT_PLAN.md; do
        printf 'content of %s for case %s\n' "$doc" "$1" > "$REPO/$doc"
    done
}

# The harness redefines hash_file as a fault-injection wrapper around the real
# shasum call: with MUTATE_AFTER_HASH_CALL=N the gated file is modified
# immediately after the Nth digest is computed. That is the only way to hit the
# prompt/response and response/recording races deterministically. The digest
# returned is always the real one for the bytes present at the time of the call.
HARNESS_PRELUDE=$(cat <<'PRELUDE'
: "${MUTATE_AFTER_HASH_CALL:=0}"
HASH_COUNT_FILE="$PWD/.hash-calls"
printf '0' > "$HASH_COUNT_FILE"
hash_file() {
    local n digest
    n=$(( $(cat "$HASH_COUNT_FILE") + 1 ))
    printf '%s' "$n" > "$HASH_COUNT_FILE"
    if command -v shasum > /dev/null 2>&1; then
        digest="$(shasum -a 256 "$1" | awk '{print $1}')"
    elif command -v sha256sum > /dev/null 2>&1; then
        digest="$(sha256sum "$1" | awk '{print $1}')"
    else
        digest="$(openssl dgst -sha256 "$1" | awk '{print $NF}')"
    fi
    if [[ "$MUTATE_AFTER_HASH_CALL" != "0" && "$MUTATE_AFTER_HASH_CALL" == "$n" ]]; then
        printf 'raced\n' >> "$1"
    fi
    printf '%s\n' "$digest"
}
PRELUDE
)

write_cw_harness() {
    extract_fns "$ROOT/scripts/change-workflow.sh" "$CASE/fns.sh" \
        gate_prompt legacy_word_notice require_file human_gate
    cat > "$REPO/gate.sh" <<HARNESS
#!/usr/bin/env bash
set -euo pipefail
APPROVAL_DIR="\$PWD/.uncle/workflow/approvals"
show_spend() { :; }
. "$CASE/fns.sh"
$HARNESS_PRELUDE
human_gate "\$@"
echo "GATE_ACCEPTED"
HARNESS
}

write_sg_harness() {
    extract_fns "$ROOT/scripts/stagegate.sh" "$CASE/fns.sh" \
        gate_prompt legacy_word_notice upper lower require_file \
        review_and_approve
    cat > "$REPO/gate.sh" <<HARNESS
#!/usr/bin/env bash
set -euo pipefail
APPROVAL_DIR="\$PWD/.uncle/workflow/approvals"
cancel_speculation() { echo "CANCEL_SPECULATION"; }
. "$CASE/fns.sh"
$HARNESS_PRELUDE
review_and_approve "\$@"
echo "GATE_ACCEPTED"
HARNESS
}

# run_gate <stdin text> [VAR=VAL ...] -- <args...>
run_gate() {
    local input="$1"
    shift
    local -a envs=()
    while [[ "$#" -gt 0 && "$1" != "--" ]]; do
        envs+=("$1")
        shift
    done
    shift
    ( cd "$REPO" && printf '%b' "$input" | env TERM=dumb "${envs[@]+"${envs[@]}"}" \
        bash gate.sh "$@" ) > "$OUT" 2>&1
    RC=$?
}

# run_workflow <stdin text> <subcommand>
run_workflow() {
    ( cd "$REPO" && printf '%b' "$1" | env TERM=dumb bash scripts/workflow.sh "$2" ) \
        > "$OUT" 2>&1
    RC=$?
}

# run_workflow_racing <mutate-file> <subcommand> — send the response only after
# the prompt has appeared, mutating the gated file in between.
run_workflow_racing() {
    local target="$1" sub="$2" i
    mkfifo "$CASE/in"
    ( cd "$REPO" && env TERM=dumb bash scripts/workflow.sh "$sub" < "$CASE/in" \
        > "$OUT" 2>&1; echo $? > "$CASE/rc" ) &
    local writer=$!
    exec 9> "$CASE/in"
    for i in $(seq 1 200); do
        grep -qF '[Y/N]' "$OUT" && break
        sleep 0.05
    done
    printf 'raced\n' >> "$REPO/$target"
    printf 'y\n' >&9
    exec 9>&-
    wait "$writer"
    RC="$(cat "$CASE/rc")"
    rm -f "$CASE/in"
}

echo "== G1: scripts/workflow.sh approve_file =="

setup_workflow() {
    new_case "$1"
    cp "$ROOT/scripts/workflow.sh" "$REPO/scripts/workflow.sh"
    # workflow.sh sources the portable sha256 helper and the workflow-directory
    # migration, so the fake checkout needs them too — the same way a real one
    # has them.
    mkdir -p "$REPO/scripts/lib"
    cp "$ROOT/scripts/lib/sha256.sh" "$REPO/scripts/lib/sha256.sh"
    cp "$ROOT/scripts/lib/workflow-directory.sh" "$REPO/scripts/lib/workflow-directory.sh"
}

for answer in y Y; do
    setup_workflow "g1-accept-$answer"
    run_workflow "$answer\n" approve-plan
    expect_status 0
    expect_out "Ready to approve PROJECT_PLAN.md? [Y/N]"
    expect_out "Approved PROJECT_PLAN.md"
    expect_hash_of "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256" "$REPO/PROJECT_PLAN.md"
done

# The digest printed at the prompt is the digest that gets recorded.
setup_workflow "g1-digest-shown"
run_workflow "y\n" approve-plan
expect_out "SHA-256: $(hash_file "$REPO/PROJECT_PLAN.md")"

for answer in "n" "N" "foo" "" "APPROVE" "ACKNOWLEDGE"; do
    setup_workflow "g1-decline-${answer:-empty}"
    run_workflow "$answer\n" approve-plan
    expect_status 1
    expect_out "Approval cancelled."
    expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"
done

for answer in APPROVE ACKNOWLEDGE approve acknowledge; do
    setup_workflow "g1-legacy-$answer"
    run_workflow "$answer\n" approve-plan
    expect_status 1
    expect_out "requires 'y' to approve"
    expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"
done

setup_workflow "g1-eof"
run_workflow "" approve-plan
expect_status 1
expect_out "Approval cancelled."
expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"

setup_workflow "g1-other-subcommands"
run_workflow "y\n" approve-review
expect_status 0
expect_out "Ready to approve ADVERSARIAL_REVIEW.md? [Y/N]"
expect_hash_of "$REPO/.uncle/workflow/approvals/ADVERSARIAL_REVIEW.sha256" "$REPO/ADVERSARIAL_REVIEW.md"

setup_workflow "g1-updated-plan"
run_workflow "y\n" approve-updated-plan
expect_status 0
expect_hash_of "$REPO/.uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256" \
    "$REPO/UPDATED_PROJECT_PLAN.md"

# Mutating the file after the prompt is shown must decline, not record the
# bytes nobody read.
setup_workflow "g1-race"
run_workflow_racing PROJECT_PLAN.md approve-plan
expect_status 1
expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"

echo "== G2: scripts/change-workflow.sh human_gate =="

# Every real call site, verbatim.
CW_SITES_VERB=(acknowledge approve acknowledge approve)
CW_SITES_ARGS=(
    "ACKNOWLEDGE BASELINE_REPORT.md BASELINE_REPORT CHANGE_SPEC.md CHANGE_SPEC CHANGE_PLAN.md CHANGE_PLAN ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW"
    "APPROVE BASELINE_REPORT.md BASELINE_REPORT CHANGE_SPEC.md CHANGE_SPEC"
    "ACKNOWLEDGE CHANGE_PLAN.md CHANGE_PLAN ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW"
    "APPROVE UPDATED_CHANGE_PLAN.md UPDATED_CHANGE_PLAN"
)
CW_SITES_FILES=(
    "BASELINE_REPORT.md CHANGE_SPEC.md CHANGE_PLAN.md ADVERSARIAL_REVIEW.md"
    "BASELINE_REPORT.md CHANGE_SPEC.md"
    "CHANGE_PLAN.md ADVERSARIAL_REVIEW.md"
    "UPDATED_CHANGE_PLAN.md"
)
CW_SITES_NAMES=(
    "BASELINE_REPORT CHANGE_SPEC CHANGE_PLAN ADVERSARIAL_REVIEW"
    "BASELINE_REPORT CHANGE_SPEC"
    "CHANGE_PLAN ADVERSARIAL_REVIEW"
    "UPDATED_CHANGE_PLAN"
)

for s in 0 1 2 3; do
    verb="${CW_SITES_VERB[$s]}"
    read -r -a site_args <<< "${CW_SITES_ARGS[$s]}"
    read -r -a site_files <<< "${CW_SITES_FILES[$s]}"
    read -r -a site_names <<< "${CW_SITES_NAMES[$s]}"

    new_case "g2-site$s-accept"
    write_cw_harness
    run_gate "\ny\n" -- "${site_args[@]}"
    expect_status 0
    expect_out "GATE_ACCEPTED"
    expect_out "Ready to $verb "
    expect_out "? [Y/N]"
    for i in "${!site_files[@]}"; do
        expect_out "${site_files[$i]}"
        expect_hash_of "$REPO/.uncle/workflow/approvals/${site_names[$i]}.sha256" \
            "$REPO/${site_files[$i]}"
    done

    new_case "g2-site$s-decline"
    write_cw_harness
    run_gate "\nn\n" -- "${site_args[@]}"
    expect_status 0
    expect_out "Gate not accepted. Workflow remains paused."
    expect_not_out "GATE_ACCEPTED"
    for i in "${!site_names[@]}"; do
        expect_no_approval "$REPO/.uncle/workflow/approvals/${site_names[$i]}.sha256"
    done
done

# Prompt names every gated file, joined, with the lowercased action verb.
new_case "g2-prompt-text"
write_cw_harness
run_gate "\nn\n" -- ACKNOWLEDGE \
    BASELINE_REPORT.md BASELINE_REPORT \
    CHANGE_SPEC.md CHANGE_SPEC \
    CHANGE_PLAN.md CHANGE_PLAN \
    ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW
expect_out "Ready to acknowledge BASELINE_REPORT.md, CHANGE_SPEC.md, CHANGE_PLAN.md, ADVERSARIAL_REVIEW.md? [Y/N]"
expect_not_out "exactly to continue"

new_case "g2-prompt-text-single"
write_cw_harness
run_gate "\nn\n" -- APPROVE UPDATED_CHANGE_PLAN.md UPDATED_CHANGE_PLAN
expect_out "Ready to approve UPDATED_CHANGE_PLAN.md? [Y/N]"

new_case "g2-accept-upper-Y"
write_cw_harness
run_gate "\nY\n" -- APPROVE UPDATED_CHANGE_PLAN.md UPDATED_CHANGE_PLAN
expect_status 0
expect_out "GATE_ACCEPTED"
expect_hash_of "$REPO/.uncle/workflow/approvals/UPDATED_CHANGE_PLAN.sha256" \
    "$REPO/UPDATED_CHANGE_PLAN.md"

for answer in "N" "foo" "" "APPROVE" "ACKNOWLEDGE"; do
    new_case "g2-decline-${answer:-empty}"
    write_cw_harness
    run_gate "\n$answer\n" -- APPROVE UPDATED_CHANGE_PLAN.md UPDATED_CHANGE_PLAN
    expect_status 0
    expect_out "Gate not accepted. Workflow remains paused."
    expect_not_out "GATE_ACCEPTED"
    expect_no_approval "$REPO/.uncle/workflow/approvals/UPDATED_CHANGE_PLAN.sha256"
done

for answer in APPROVE ACKNOWLEDGE; do
    new_case "g2-legacy-$answer"
    write_cw_harness
    run_gate "\n$answer\n" -- APPROVE UPDATED_CHANGE_PLAN.md UPDATED_CHANGE_PLAN
    expect_out "requires 'y' to approve"
done

# EOF at the Y/N read: the ENTER line is consumed, then stdin closes.
new_case "g2-eof-at-yn"
write_cw_harness
run_gate "\n" -- APPROVE UPDATED_CHANGE_PLAN.md UPDATED_CHANGE_PLAN
expect_status 0
expect_out "Gate not accepted. Workflow remains paused."
expect_no_approval "$REPO/.uncle/workflow/approvals/UPDATED_CHANGE_PLAN.sha256"

# AR-001: EOF at the preliminary "Press ENTER" read must not trip `set -e`.
for site in 0 3; do
    read -r -a site_args <<< "${CW_SITES_ARGS[$site]}"
    new_case "g2-eof-preliminary-site$site"
    write_cw_harness
    run_gate "" -- "${site_args[@]}"
    expect_status 0
    expect_out "Gate not accepted. Workflow remains paused."
    expect_not_out "GATE_ACCEPTED"
    expect_no_approval "$REPO/.uncle/workflow/approvals/BASELINE_REPORT.sha256"
    expect_no_approval "$REPO/.uncle/workflow/approvals/UPDATED_CHANGE_PLAN.sha256"
done

# A gated file mutated between the prompt digest and the response must decline.
new_case "g2-race"
write_cw_harness
run_gate "\ny\n" MUTATE_AFTER_HASH_CALL=1 -- ACKNOWLEDGE \
    CHANGE_PLAN.md CHANGE_PLAN \
    ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW
expect_status 0
expect_not_out "GATE_ACCEPTED"
expect_no_approval "$REPO/.uncle/workflow/approvals/CHANGE_PLAN.sha256"
expect_no_approval "$REPO/.uncle/workflow/approvals/ADVERSARIAL_REVIEW.sha256"

echo "== G3: scripts/stagegate.sh review_and_approve =="

SG_SITES_VERB=(approve approve acknowledge approve)
SG_SITES_ARGS=(
    "REQUIREMENTS_INTERPRETATION.md REQUIREMENTS_INTERPRETATION approve"
    "PROJECT_PLAN.md PROJECT_PLAN approve"
    "ADVERSARIAL_REVIEW.md ADVERSARIAL_REVIEW acknowledge"
    "UPDATED_PROJECT_PLAN.md UPDATED_PROJECT_PLAN approve"
)
SG_SITES_FILE=(
    REQUIREMENTS_INTERPRETATION.md
    PROJECT_PLAN.md
    ADVERSARIAL_REVIEW.md
    UPDATED_PROJECT_PLAN.md
)
SG_SITES_NAME=(
    REQUIREMENTS_INTERPRETATION
    PROJECT_PLAN
    ADVERSARIAL_REVIEW
    UPDATED_PROJECT_PLAN
)

for s in 0 1 2 3; do
    verb="${SG_SITES_VERB[$s]}"
    file="${SG_SITES_FILE[$s]}"
    name="${SG_SITES_NAME[$s]}"
    read -r -a site_args <<< "${SG_SITES_ARGS[$s]}"

    new_case "g3-site$s-accept"
    write_sg_harness
    run_gate "\ny\n" -- "${site_args[@]}"
    expect_status 0
    expect_out "GATE_ACCEPTED"
    expect_out "Ready to $verb $file? [Y/N]"
    expect_hash_of "$REPO/.uncle/workflow/approvals/${name}.sha256" "$REPO/$file"

    new_case "g3-site$s-decline"
    write_sg_harness
    run_gate "\nn\n" -- "${site_args[@]}"
    expect_status 0
    expect_out "Gate not accepted. Workflow paused."
    expect_not_out "GATE_ACCEPTED"
    expect_no_approval "$REPO/.uncle/workflow/approvals/${name}.sha256"
done

# The default wording is still `approve`.
new_case "g3-default-wording"
write_sg_harness
run_gate "\nn\n" -- PROJECT_PLAN.md PROJECT_PLAN
expect_out "Ready to approve PROJECT_PLAN.md? [Y/N]"
expect_not_out "exactly to continue"

new_case "g3-accept-upper-Y"
write_sg_harness
run_gate "\nY\n" -- PROJECT_PLAN.md PROJECT_PLAN approve
expect_status 0
expect_out "GATE_ACCEPTED"
expect_hash_of "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256" "$REPO/PROJECT_PLAN.md"

for answer in "N" "foo" "" "APPROVE" "ACKNOWLEDGE"; do
    new_case "g3-decline-${answer:-empty}"
    write_sg_harness
    run_gate "\n$answer\n" -- PROJECT_PLAN.md PROJECT_PLAN approve
    expect_status 0
    expect_out "Gate not accepted. Workflow paused."
    expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"
done

for answer in APPROVE ACKNOWLEDGE; do
    new_case "g3-legacy-$answer"
    write_sg_harness
    run_gate "\n$answer\n" -- PROJECT_PLAN.md PROJECT_PLAN approve
    expect_out "requires 'y' to approve"
done

new_case "g3-eof-at-yn"
write_sg_harness
run_gate "\n" -- PROJECT_PLAN.md PROJECT_PLAN approve
expect_status 0
expect_out "Gate not accepted. Workflow paused."
expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"

new_case "g3-eof-preliminary"
write_sg_harness
run_gate "" -- PROJECT_PLAN.md PROJECT_PLAN approve
expect_status 0
expect_out "Gate not accepted. Workflow paused."
expect_not_out "GATE_ACCEPTED"
expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"

# I-3: edited during review — the gate re-opens and speculation is cancelled.
# The second pass then approves the bytes actually read.
new_case "g3-reopen-on-edit"
write_sg_harness
run_gate "\ny\n\ny\n" MUTATE_AFTER_HASH_CALL=1 -- PROJECT_PLAN.md PROJECT_PLAN approve
expect_status 0
expect_out "changed while you were reviewing it."
expect_out "CANCEL_SPECULATION"
expect_out "GATE_ACCEPTED"
expect_hash_of "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256" "$REPO/PROJECT_PLAN.md"

# AR-003: edited between the validating compare and the recording step. The
# recorded digest must be the validated one, not a re-read of the new bytes.
new_case "g3-race-after-response"
write_sg_harness
SG_PRE_RACE_DIGEST="$(hash_file "$REPO/PROJECT_PLAN.md")"
run_gate "\ny\n" MUTATE_AFTER_HASH_CALL=2 -- PROJECT_PLAN.md PROJECT_PLAN approve
expect_status 0
expect_hash_literal "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256" "$SG_PRE_RACE_DIGEST"
COUNT=$((COUNT + 1))
if [[ "$(cat "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256" 2>/dev/null)" == \
      "$(hash_file "$REPO/PROJECT_PLAN.md")" ]]; then
    fail "approval recorded the post-race bytes instead of the reviewed bytes"
fi

echo "== G4: prompt styling =="

new_case "g4-piped"
setup_workflow "g4-piped"
run_workflow "y\n" approve-plan
expect_no_ansi

new_case "g4-dumb-harness"
write_cw_harness
run_gate "\nn\n" -- APPROVE UPDATED_CHANGE_PLAN.md UPDATED_CHANGE_PLAN
expect_no_ansi

new_case "g4-sg-piped"
write_sg_harness
run_gate "\nn\n" -- PROJECT_PLAN.md PROJECT_PLAN approve
expect_no_ansi

# PTY: `script` argument order differs between BSD and GNU. Try both; if
# neither produces the prompt, record NOT RUN — never relax it into a pass.
setup_workflow "g4-pty"
CASE_NAME="g4-pty"
PTY_OUT="$CASE/pty.txt"
(
    cd "$REPO" || exit 1
    printf 'n\n' | script -q /dev/null env TERM=xterm bash scripts/workflow.sh approve-plan
) > "$PTY_OUT" 2>/dev/null
if ! grep -qF '[Y/N]' "$PTY_OUT" 2>/dev/null; then
    (
        cd "$REPO" || exit 1
        printf 'n\n' | script -q -c "env TERM=xterm bash scripts/workflow.sh approve-plan" /dev/null
    ) > "$PTY_OUT" 2>/dev/null
fi
if ! grep -qF '[Y/N]' "$PTY_OUT" 2>/dev/null; then
    notrun "PTY capture unavailable on this host; covered manually by M-1/M-5"
else
    OUT="$PTY_OUT"
    COUNT=$((COUNT + 1))
    if ! LC_ALL=C grep -q $'\033\[1m' "$PTY_OUT"; then
        fail "expected bold escape before the prompt under a PTY"
    fi
    COUNT=$((COUNT + 1))
    if ! LC_ALL=C grep -q $'\033\[0m' "$PTY_OUT"; then
        fail "expected reset escape after the prompt under a PTY"
    fi
fi

# TERM=dumb under a PTY must stay clean.
setup_workflow "g4-pty-dumb"
CASE_NAME="g4-pty-dumb"
PTY_OUT="$CASE/pty.txt"
(
    cd "$REPO" || exit 1
    printf 'n\n' | script -q /dev/null env TERM=dumb bash scripts/workflow.sh approve-plan
) > "$PTY_OUT" 2>/dev/null
if ! grep -qF '[Y/N]' "$PTY_OUT" 2>/dev/null; then
    (
        cd "$REPO" || exit 1
        printf 'n\n' | script -q -c "env TERM=dumb bash scripts/workflow.sh approve-plan" /dev/null
    ) > "$PTY_OUT" 2>/dev/null
fi
if ! grep -qF '[Y/N]' "$PTY_OUT" 2>/dev/null; then
    notrun "PTY capture unavailable on this host; covered manually by M-5"
else
    OUT="$PTY_OUT"
    expect_no_ansi
fi

echo "== G5: whitespace strictness =="

setup_workflow "g5-leading-space-workflow"
run_workflow " y\n" approve-plan
expect_status 1
expect_out "Approval cancelled."
expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"

setup_workflow "g5-trailing-space-workflow"
run_workflow "y \n" approve-plan
expect_status 1
expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"

new_case "g5-leading-space-cw"
write_cw_harness
run_gate "\n y\n" -- APPROVE UPDATED_CHANGE_PLAN.md UPDATED_CHANGE_PLAN
expect_status 0
expect_not_out "GATE_ACCEPTED"
expect_no_approval "$REPO/.uncle/workflow/approvals/UPDATED_CHANGE_PLAN.sha256"

new_case "g5-leading-space-sg"
write_sg_harness
run_gate "\n y\n" -- PROJECT_PLAN.md PROJECT_PLAN approve
expect_status 0
expect_not_out "GATE_ACCEPTED"
expect_no_approval "$REPO/.uncle/workflow/approvals/PROJECT_PLAN.sha256"

echo
if [[ "$FAILED" -gt 0 ]]; then
    echo "gate-prompt-test.sh: $FAILED of $COUNT checks FAILED ($NOTRUN not run)"
    exit 1
fi
echo "gate-prompt-test.sh: $COUNT checks passed ($NOTRUN not run)"
