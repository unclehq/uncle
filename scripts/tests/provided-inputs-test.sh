#!/usr/bin/env bash
# A prerequisite handed over at the gate settles the row, without re-running.
#
# The behaviour under test is a trade: the driver marks the row itself instead
# of paying for another preflight stage to rediscover a file the operator just
# named. That is only safe while the marking stays narrow, so most of what
# follows is about what it must refuse to touch.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/lib/sha256.sh"
MARK="$ROOT/scripts/lib/mark-provided.py"
. "$ROOT/scripts/lib/acceptance.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PASS=0
fail() { echo "FAIL: $1" >&2; exit 1; }
ok() { PASS=$((PASS + 1)); }

fresh() {
    rm -rf "$WORK/case"
    mkdir -p "$WORK/case/tests/fixtures"
    cd "$WORK/case"
    printf '{"links":[]}\n' > tests/fixtures/oracle.json
    printf 'Brian approved the mapping on 2026-09-08.\n' > SOURCE_REVIEW_APPROVAL.md
    cat > PREFLIGHT_REPORT.md <<'MD'
# Preflight

A prose line | carrying a pipe, which is not a table row.

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| P-1 | YES | PASS | python3 3.13 found |
| P-2 | YES | BLOCKED-SETUP | tests/fixtures/oracle.json absent |
| P-3 | YES | BLOCKED-SETUP | SOURCE_REVIEW_APPROVAL.md absent |
| P-4 | YES | BLOCKED-HUMAN | awaiting reviewer signature |
| P-5 | NO | N/A | no credentials required |
MD
}

# --- marking what was provided ---------------------------------------------

fresh
python3 "$MARK" PREFLIGHT_REPORT.md \
    P-2=tests/fixtures/oracle.json P-3=SOURCE_REVIEW_APPROVAL.md \
    || fail "marking two provided prerequisites should succeed"
ok
grep -q '^| P-2 | YES | PASS | provided at the preflight gate' PREFLIGHT_REPORT.md \
    || fail "P-2 was not marked: $(grep '^| P-2' PREFLIGHT_REPORT.md)"
ok
# The evidence has to carry provenance, or a later reader cannot tell a row the
# operator supplied from one preflight probed for itself.
grep -q 'recorded by the operator, not observed by preflight' PREFLIGHT_REPORT.md \
    || fail "the rewritten evidence does not say where it came from"
ok
grep -q 'sha256 [0-9a-f]\{12\}' PREFLIGHT_REPORT.md \
    || fail "the evidence must name the digest of what was provided"
ok

# The whole point: the verdict must now let implementation start.
[[ "$(acceptance_result PREFLIGHT_REPORT.md)" == BLOCKED-HUMAN ]] \
    || fail "expected BLOCKED-HUMAN once the setup rows are settled, got $(acceptance_result PREFLIGHT_REPORT.md)"
ok
[[ -z "$(acceptance_blocked_ids PREFLIGHT_REPORT.md BLOCKED-SETUP)" ]] \
    || fail "setup blockers remain after marking: $(acceptance_blocked_ids PREFLIGHT_REPORT.md BLOCKED-SETUP)"
ok

# --- what it must not touch -------------------------------------------------

# A row nobody provided keeps its status. Marking one blocker must never sweep
# the rest of the table along with it.
grep -q '^| P-4 | YES | BLOCKED-HUMAN | awaiting reviewer signature |$' PREFLIGHT_REPORT.md \
    || fail "an unrelated blocked row was altered"
ok
grep -q '^| P-5 | NO | N/A | no credentials required |$' PREFLIGHT_REPORT.md \
    || fail "an optional row was altered"
ok
grep -q '^| P-1 | YES | PASS | python3 3.13 found |$' PREFLIGHT_REPORT.md \
    || fail "an already-passing row was rewritten"
ok
grep -q '^A prose line | carrying a pipe, which is not a table row.$' PREFLIGHT_REPORT.md \
    || fail "prose outside the table was not preserved"
ok

# An id with no blocked row is a mistake, not a licence to add one: the report
# must come back untouched so the caller cannot half-apply a batch.
fresh
before="$(hash_file PREFLIGHT_REPORT.md)"
if python3 "$MARK" PREFLIGHT_REPORT.md P-99=SOURCE_REVIEW_APPROVAL.md 2>/dev/null; then
    fail "marking an id with no blocked row should fail"
fi
ok
[[ "$(hash_file PREFLIGHT_REPORT.md)" == "$before" ]] \
    || fail "a failed marking must leave the report byte-identical"
ok

# A row that already passed is not blocked, so it is not markable either.
if python3 "$MARK" PREFLIGHT_REPORT.md P-1=SOURCE_REVIEW_APPROVAL.md 2>/dev/null; then
    fail "marking an already-passing row should fail"
fi
ok

# The file has to be there. Recording that an absent input was provided is the
# exact failure this whole path exists to avoid.
if python3 "$MARK" PREFLIGHT_REPORT.md P-2=tests/fixtures/nothing.json 2>/dev/null; then
    fail "a missing input must be refused"
fi
ok
: > tests/fixtures/empty.json
if python3 "$MARK" PREFLIGHT_REPORT.md P-2=tests/fixtures/empty.json 2>/dev/null; then
    fail "an empty input must be refused"
fi
ok
[[ "$(hash_file PREFLIGHT_REPORT.md)" == "$before" ]] \
    || fail "a refused input must leave the report unchanged"
ok

# --- the table stays parseable ----------------------------------------------

# A pipe in a path would split the row and corrupt the table for every later
# reader, so it is stripped rather than written through.
fresh
# Exercise evidence escaping on every platform without asking the filesystem
# to represent a name that Win32 forbids. Only the digest I/O is substituted.
python3 - "$MARK" <<'PYTEST'
import importlib.util
import sys
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('mark_provided', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with patch.object(module, 'digest', return_value='a' * 64) as digest:
    assert module.mark('PREFLIGHT_REPORT.md', {'P-2': 'tests/fixtures/od|d/oracle.json'}) == 0
    digest.assert_called_once_with('tests/fixtures/od|d/oracle.json')
PYTEST
ok
[[ "$(awk -F'|' '/^\| P-2 /{print NF}' PREFLIGHT_REPORT.md)" == 6 ]] \
    || fail "the marked row does not have six fields"
ok
[[ "$(acceptance_result PREFLIGHT_REPORT.md)" == BLOCKED-SETUP ]] \
    || fail "the table stopped parsing after marking"
ok

# Also exercise real digest I/O where the native Python filesystem API can
# use pipe names. MSYS mkdir can succeed on Windows via filename translation
# even though native Python cannot open that same path.
if python3 -c 'import os, sys; sys.exit(1 if os.name == "nt" else 0)'; then
    fresh
    mkdir -p 'tests/fixtures/od|d'
    printf 'x\n' > 'tests/fixtures/od|d/oracle.json'
    python3 "$MARK" PREFLIGHT_REPORT.md 'P-2=tests/fixtures/od|d/oracle.json' \
        || fail "a path containing a pipe should still mark"
    ok
    [[ "$(awk -F'|' '/^\| P-2 /{print NF}' PREFLIGHT_REPORT.md)" == 6 ]] \
        || fail "the real-file marked row does not have six fields"
    ok
else
    echo "SKIP: native Windows cannot open pipe filenames; evidence escaping tested separately."
fi

cd "$ROOT"
echo "provided-inputs-test.sh: $PASS checks passed -- provided rows are marked with provenance, everything else is left alone, and a refusal changes nothing"
