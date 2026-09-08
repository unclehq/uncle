#!/usr/bin/env bash
# Providing a blocked prerequisite at the gate.
#
# Driven the way the TUI drives it: answers arrive on the driver's stdin, one
# line per question, because the TUI renders each unterminated prompt as a
# dialog and writes the reply into that pipe. A test that needed a terminal
# would be testing something no uncle run actually does.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/acceptance.sh"
. "$ROOT/scripts/lib/human-input.sh"
gate_prompt() { printf '%s' "$1"; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"
fail() { echo "FAIL: $1" >&2; exit 1; }

cat > PREFLIGHT_REPORT.md <<'MD'
## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| G-1 | YES | PASS | python3 3.14.7 found |
| G-9 | YES | BLOCKED-SETUP | .uncle/workflow/preflight-evidence/SOURCE_REVIEW_APPROVAL.md absent |
| G-10 | YES | BLOCKED-SETUP | tests/fixtures/links_expected.json absent (ls tests/fixtures) |
MD

# --- a statement, and a file, both taken from the prompts --------------------
mkdir -p elsewhere
printf '{"links": []}\n' > elsewhere/links_expected.json
collect_human_inputs PREFLIGHT_REPORT.md records.tsv G-9 G-10 > log.txt <<'ANSWERS'
s

Brian approved the source-to-oracle mapping on 2026-09-07, by email.
f

elsewhere/links_expected.json
ANSWERS
[ -s records.tsv ] || fail "nothing was collected"

# The blank answers above accepted the suggested paths, which is the whole
# point of suggesting rather than retyping.
grep -q $'G-9\tstatement\t.uncle/workflow/preflight-evidence/SOURCE_REVIEW_APPROVAL.md\t' records.tsv \
    || fail "the suggested path was not taken from the evidence: $(cat records.tsv)"
grep -q $'G-10\tcopy\ttests/fixtures/links_expected.json\telsewhere/links_expected.json' records.tsv \
    || fail "the copy record is wrong: $(cat records.tsv)"

# --- applying them puts the files where the next run looks ------------------
apply_human_inputs records.tsv > applied.txt || fail "applying should report success"
[ -s .uncle/workflow/preflight-evidence/SOURCE_REVIEW_APPROVAL.md ] \
    || fail "the statement was not written"
grep -q "Brian approved the source-to-oracle mapping" \
    .uncle/workflow/preflight-evidence/SOURCE_REVIEW_APPROVAL.md \
    || fail "the statement text was not kept"
# Provenance is the point: a later stage and the audit must be able to see that
# a person entered this at the gate, not that a tool established it.
grep -q "Recorded by the operator at the preflight gate" \
    .uncle/workflow/preflight-evidence/SOURCE_REVIEW_APPROVAL.md \
    || fail "the statement must say who recorded it and where"
grep -qE "^When: 20[0-9]{2}-" .uncle/workflow/preflight-evidence/SOURCE_REVIEW_APPROVAL.md \
    || fail "the statement must be dated"
cmp -s elsewhere/links_expected.json tests/fixtures/links_expected.json \
    || fail "the file was not copied into place"

# --- skipping ---------------------------------------------------------------
rm -f records2.tsv
if collect_human_inputs PREFLIGHT_REPORT.md records2.tsv G-9 G-10 > /dev/null <<'ANSWERS'


ANSWERS
then fail "skipping everything must report that nothing was provided"; fi
[ ! -s records2.tsv ] || fail "skipping must record nothing"

# A chosen action with no path and no suggestion is a skip, not a write to "".
cat > NOPATH.md <<'MD'
## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| G-1 | YES | PASS | ok |
| G-7 | YES | BLOCKED-SETUP | a reviewer has not confirmed the arrangement |
MD
# A statement is offered too, so the run reaches the point where a record
# would be written. Without the empty-path guard it writes one with no
# destination, which apply then silently ignores -- an answer accepted and
# quietly dropped is worse than one refused.
if collect_human_inputs NOPATH.md records3.tsv G-7 > /dev/null <<'ANSWERS'
s

Brian said it was fine
ANSWERS
then fail "no path and no suggestion must not count as provided"; fi
[ ! -s records3.tsv ] || fail "no path must record nothing: $(cat records3.tsv)"

# --- a copy from a source that does not exist is refused, not faked ---------
printf 'G-10\tcopy\ttests/fixtures/other.json\tno/such/file.json\n' > records4.tsv
if apply_human_inputs records4.tsv > out4.txt 2>&1; then
    fail "copying a missing source must not report success"
fi
[ ! -e tests/fixtures/other.json ] || fail "a missing source must not create a target"

# --- the three ways a real run went wrong ------------------------------------
# Observed: an operator answered "." for the path on all three blockers. It was
# taken literally, the write failed on a directory, and because one failure
# aborted the whole apply the answers already given for the other two were
# discarded. Each part is its own bug.

# 1. A directory is refused and re-asked, not accepted.
rm -f rec5.tsv
mkdir -p somedir
collect_human_inputs PREFLIGHT_REPORT.md rec5.tsv G-9 > log5.txt <<'ANSWERS' \
    || fail "three bad paths then a good one should still record: $(cat log5.txt 2>/dev/null)"
s
.
somedir/
somedir
.uncle/workflow/preflight-evidence/APPROVAL.md
y
Brian approved it by email on 2026-09-07
ANSWERS
grep -q "is a directory" log5.txt || fail "a directory answer must be refused: $(cat log5.txt)"
grep -q "is an existing directory" log5.txt || fail "an existing directory must be refused"
grep -q $'G-9	statement	.uncle/workflow/preflight-evidence/APPROVAL.md	' rec5.tsv     || fail "the fourth answer should have been accepted: $(cat rec5.tsv)"

# It gives up after a few tries rather than looping on a stubborn answer.
rm -f rec6.tsv
if collect_human_inputs PREFLIGHT_REPORT.md rec6.tsv G-9 > log6.txt <<'ANSWERS'
s
.
.
.
.
.
ANSWERS
then fail "repeated directory answers must end in a skip, not a record"; fi
grep -q "no usable path given" log6.txt || fail "it must say it gave up: $(cat log6.txt)"

# 2. One unwritable record must not discard the others.
printf 'A-1	statement	somedir	into a directory, which cannot work
' > rec7.tsv
printf 'A-2	statement	kept/approval.md	this one is fine
' >> rec7.tsv
apply_human_inputs rec7.tsv > log7.txt 2>&1 || fail "a partly-good batch must report success"
[ -s kept/approval.md ] || fail "the good record must still be applied"
grep -q "A-1" log7.txt || fail "the bad record must be reported"

# 3. A statement aimed at a file that plainly wants content asks first.
rm -f rec8.tsv
if collect_human_inputs PREFLIGHT_REPORT.md rec8.tsv G-10 > log8.txt <<'ANSWERS'
s
sample.pdf
y
n
ANSWERS
then fail "declining the confirmation must not count as provided"; fi
grep -q "looks like a file to supply" log8.txt     || fail "writing prose into a .pdf must be questioned: $(cat log8.txt)"
[ ! -s rec8.tsv ] || fail "declining the confirmation must record nothing"

# ...and still allows it when the operator means it.
rm -f rec9.tsv
collect_human_inputs PREFLIGHT_REPORT.md rec9.tsv G-10 > /dev/null <<'ANSWERS' \
    || fail "a confirmed statement must count as provided"
s
notes.json
y
y
the oracle was agreed verbally; this records that
ANSWERS
grep -q $'G-10	statement	notes.json	' rec9.tsv || fail "a confirmed statement must be recorded"

# 4. A bare filename in the evidence is offered as a suggestion.
cat > BARE.md <<'MD'
## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| G-1 | YES | PASS | ok |
| B-9 | YES | BLOCKED | no links_expected.json or evidence link files in tree |
MD
rm -f rec10.tsv
collect_human_inputs BARE.md rec10.tsv B-9 > log10.txt <<'ANSWERS' \
    || fail "accepting a bare-filename suggestion must count as provided: $(cat log10.txt 2>/dev/null)"
f

elsewhere/links_expected.json
ANSWERS
grep -q "links_expected.json\]" log10.txt     || fail "a bare filename in the evidence should be suggested: $(cat log10.txt)"
grep -q $'B-9	copy	links_expected.json	elsewhere/links_expected.json' rec10.tsv     || fail "accepting the bare suggestion should record it: $(cat rec10.tsv)"

# 5. A path unrelated to the blocker is questioned. Observed: an operator typed
# "s21" for a blocker naming tests/fixtures/links_expected.json, so a statement
# was written to ./s21 -- resolving nothing. The next probe blocked on the same
# prerequisite, offered the dialog again, and the gate looped.
rm -f rec11.tsv
if collect_human_inputs PREFLIGHT_REPORT.md rec11.tsv G-10 > log11.txt <<'ANSWERS'
s
s21
n
ANSWERS
then fail "declining the divergence must record nothing"; fi
grep -q "names tests/fixtures/links_expected.json, not s21" log11.txt \
    || fail "it must say what the blocker asked for: $(cat log11.txt)"
[ ! -e s21 ] || fail "declining must not create the file"

# Accepting the suggestion asks nothing extra.
rm -f rec12.tsv
collect_human_inputs PREFLIGHT_REPORT.md rec12.tsv G-10 > log12.txt <<'ANSWERS' \
    || fail "taking the suggestion must record"
f

elsewhere/links_expected.json
ANSWERS
grep -q "names" log12.txt && fail "taking the suggestion must not ask about divergence"

# 6. The same blockers twice means the dialog stops asking.
# Observed: three prerequisites, three statements written to unrelated paths,
# preflight re-probed, the same three came back, the dialog opened again --
# indefinitely. One attempt per distinct set.
state="$work/state"
mkdir -p "$state"
human_input_repeating "$state" P-3 P-11 P-13 \
    && fail "the first time a set is seen must not count as repeating"
human_input_repeating "$state" P-3 P-11 P-13 \
    || fail "the same set a second time must be recognised as repeating"
human_input_repeating "$state" P-13 P-3 P-11 \
    || fail "order must not make the same set look new"

# A different set gets its turn.
human_input_repeating "$state" P-3 P-11 \
    && fail "a set with one blocker resolved must not be treated as repeating"
human_input_repeating "$state" P-3 P-11 \
    || fail "that set repeating must then be recognised"

# And progress clears the memory.
human_input_reset "$state"
human_input_repeating "$state" P-3 P-11 \
    && fail "a reset must give the next set a turn"

# The driver wires all three together.
grep -q "human_input_repeating" "$ROOT/scripts/stagegate.sh" \
    || fail "the driver must check for a repeating blocker set"
grep -q "human_input_reset" "$ROOT/scripts/stagegate.sh" \
    || fail "the driver must clear the memory when preflight moves on"

echo 'human-input-test.sh: statements recorded with provenance, files copied, paths corrected and validated, partial batches applied, skips and bad sources refused, and a repeating blocker set stops the dialog'
