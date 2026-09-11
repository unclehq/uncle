#!/usr/bin/env bash
set -euo pipefail

# Fixture tests for scripts/lib/implementation-review.sh — the generated
# document the post-implementation gate shows the operator.
#
# These run against a real scratch git repository rather than a stub: the whole
# point of the library is what git reports about a working tree, so a fake git
# would test the fake.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/implementation-review.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Digest of stdin, portable: shasum on macOS, sha256sum on Linux, else openssl.
hash_stdin() {
    if command -v shasum > /dev/null 2>&1; then
        shasum -a 256
    elif command -v sha256sum > /dev/null 2>&1; then
        sha256sum
    else
        openssl dgst -sha256
    fi
}

FAILED=0
COUNT=0

fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

check_eq() {
    local name="$1" expected="$2" actual="$3"
    COUNT=$((COUNT + 1))
    if [[ "$actual" != "$expected" ]]; then
        fail "$name — expected '$expected', got '$actual'"
    fi
}

check_contains() {
    local name="$1" needle="$2" file="$3"
    COUNT=$((COUNT + 1))
    if ! grep -qF -- "$needle" "$file"; then
        fail "$name — expected to find: $needle"
    fi
}

check_not_contains() {
    local name="$1" needle="$2" file="$3"
    COUNT=$((COUNT + 1))
    if grep -qF -- "$needle" "$file"; then
        fail "$name — did not expect to find: $needle"
    fi
}

# --- workflow_artifact: the paper trail is not the change ------------------

for a in IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md CHANGE_PLAN.md \
         FINAL_AUDIT.md AUTOMATED_TEST_REPORT.md PREFLIGHT_REPORT.md TEST_REVIEW.md \
         .uncle/workflow/change.diff; do
    COUNT=$((COUNT + 1))
    if ! workflow_artifact "$a"; then
        fail "$a should be excluded from the reviewed diff"
    fi
done

for s in app/main.py scripts/thing.sh README.md notes/CHANGE_PLAN.md.bak; do
    COUNT=$((COUNT + 1))
    if workflow_artifact "$s"; then
        fail "$s is source and must appear in the reviewed diff"
    fi
done

# --- a scratch repository --------------------------------------------------

REPO="$TMP/repo"
mkdir -p "$REPO"
cd "$REPO"
git init -q .
git config user.email test@example.com
git config user.name Test

mkdir -p app
printf 'def add(a, b):\n    return a + b\n' > app/calc.py
printf 'unchanged\n' > app/other.py
git add -A
git -c commit.gpgsign=false commit -qm baseline

# Workflow paperwork alone must not count as delivered implementation.
printf '# stopped before implementation\n' > IMPLEMENTATION_NOTES.md
COUNT=$((COUNT + 1))
if implementation_has_changes; then fail "reports alone counted as implementation"; fi
printf 'new behavior\n' > feature.txt
COUNT=$((COUNT + 1))
implementation_has_changes || fail "new product file was not detected"
rm feature.txt

# The shapes an implementation stage produces: an edit, a new source file, a
# deletion, and the workflow's own reports.
printf 'def add(a, b):\n    return a - b\n' > app/calc.py
printf 'SECRET = 1\n' > app/new_module.py
rm app/other.py
printf '# notes\n' > IMPLEMENTATION_NOTES.md
printf '# tests\n' > CHANGE_TEST_REPORT.md
mkdir -p .uncle/workflow
printf 'state\n' > .uncle/workflow/state

files="$(change_diff_files | tr '\n' ' ')"
check_eq "the changed source is listed" \
    "app/calc.py app/new_module.py app/other.py " "$files"

COUNT=$((COUNT + 1))
case "$files" in
    *IMPLEMENTATION_NOTES*|*CHANGE_TEST_REPORT*|*.uncle/workflow*)
        fail "a workflow artifact leaked into the reviewed file list" ;;
esac

write_change_diff "$TMP/change.diff"

check_contains "an edit is in the diff"          "return a - b"  "$TMP/change.diff"
check_contains "a new untracked file is in the diff" "SECRET = 1" "$TMP/change.diff"
check_contains "a deletion is in the diff"       "app/other.py"  "$TMP/change.diff"
check_not_contains "the paper trail is not in the diff" "# notes" "$TMP/change.diff"

# The gate must not change the state it reports on.
check_eq "rendering an untracked file does not stage it" "" \
    "$(git diff --cached --name-only)"
check_eq "the untracked file is still untracked" "app/new_module.py" \
    "$(git ls-files --others --exclude-standard -- app)"

# --- the composed review document ------------------------------------------

printf '## Green check\n\nNo regressions.\n' > "$TMP/green.md"

write_implementation_review "$TMP/review.md" "$TMP/change.diff" "$TMP/green.md" \
    IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md MISSING_REPORT.md

check_contains "the file list is in the review"   "- app/calc.py"    "$TMP/review.md"
check_contains "the green check is in the review" "No regressions."  "$TMP/review.md"
check_contains "the agent's notes are embedded"   "# notes"          "$TMP/review.md"
check_contains "the test report is embedded"      "# tests"          "$TMP/review.md"
check_contains "the diff is in the review"        "return a - b"     "$TMP/review.md"
check_contains "an embedded document is fixed to its digest" "sha256:" "$TMP/review.md"
check_contains "a missing report is reported, not skipped" \
    "MISSING or empty" "$TMP/review.md"

# Regenerating from an unchanged tree must reproduce the same bytes: that is
# what makes the approval digest a check on the tree.
write_change_diff "$TMP/change2.diff"
write_implementation_review "$TMP/review2.md" "$TMP/change2.diff" "$TMP/green.md" \
    IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md MISSING_REPORT.md
check_eq "an unchanged tree regenerates the same document" \
    "$(hash_stdin < "$TMP/review.md")" "$(hash_stdin < "$TMP/review2.md")"

# Touching source after approval must change the document, or the gate would
# be attesting to bytes that no longer describe the tree.
printf 'def add(a, b):\n    return a * b\n' > app/calc.py
write_change_diff "$TMP/change3.diff"
write_implementation_review "$TMP/review3.md" "$TMP/change3.diff" "$TMP/green.md" \
    IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md MISSING_REPORT.md
COUNT=$((COUNT + 1))
if [[ "$(hash_stdin < "$TMP/review.md")" == "$(hash_stdin < "$TMP/review3.md")" ]]; then
    fail "editing source after approval left the review document unchanged"
fi

# --- a clean tree ----------------------------------------------------------

git checkout -q -- app/calc.py
rm -f app/new_module.py IMPLEMENTATION_NOTES.md CHANGE_TEST_REPORT.md
git checkout -q -- app/other.py

check_eq "a clean tree changes no source" "" "$(change_diff_files)"

write_change_diff "$TMP/empty.diff"
write_implementation_review "$TMP/empty-review.md" "$TMP/empty.diff" "$TMP/green.md"
check_contains "an empty change says so plainly" \
    "changed no source file" "$TMP/empty-review.md"

# --- untracked files that predate the change -------------------------------

cd "$REPO"
printf 'scratch\n' > my-notes.txt
snapshot_untracked "$TMP/untracked-before.txt"
printf 'brand new\n' > app/created_by_agent.py

check_eq "with no baseline set, every untracked file counts" \
    "app/created_by_agent.py my-notes.txt " \
    "$(change_diff_files | tr '\n' ' ')"

WORKFLOW_UNTRACKED_BASELINE="$TMP/untracked-before.txt"
check_eq "a file that predates the change is not part of it" \
    "app/created_by_agent.py " \
    "$(change_diff_files | tr '\n' ' ')"

# The snapshot is a raw record of what git saw, filtered later rather than
# here: change_diff_files removes the workflow's own artifacts on its own.
COUNT=$((COUNT + 1))
if ! grep -qxF my-notes.txt "$TMP/untracked-before.txt"; then
    fail "the snapshot must list the file that already existed"
fi

WORKFLOW_UNTRACKED_BASELINE=""
rm -f my-notes.txt app/created_by_agent.py
cd "$ROOT"

# --- a directory git knows nothing about -----------------------------------

BARE="$TMP/not-a-repo"
mkdir -p "$BARE"
cd "$BARE"
printf 'x\n' > app.py

COUNT=$((COUNT + 1))
if in_git_repo; then
    fail "a plain directory was reported as a git repository"
fi

write_change_diff "$TMP/bare.diff"
write_implementation_review "$TMP/bare-review.md" "$TMP/bare.diff" "$TMP/green.md"
check_contains "a non-repository is reported as unknown, not as empty" \
    "UNKNOWN" "$TMP/bare-review.md"
check_not_contains "a non-repository never claims nothing was built" \
    "changed no source file" "$TMP/bare-review.md"

cd "$ROOT"

if [[ "$FAILED" -ne 0 ]]; then
    echo "implementation-review-test.sh: $FAILED of $COUNT checks failed"
    exit 1
fi

echo "implementation-review-test.sh: $COUNT checks passed"
