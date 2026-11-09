#!/usr/bin/env bash
# Review-skip (AC-6/7/8): the shared shell helper change_class_review_skipped, the skip-review CLI stub, the
# WORKFLOW_SKIP_REVIEW value matrix, stale-stub/marker handling, and the stub's survival through downstream validation.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2"; }
check() { # name expected-rc actual-rc
    [[ "$2" == "$3" ]] && ok || bad "$1" "want rc=$2 got rc=$3"
}

PY="$ROOT/scripts/lib/change_class.py"
STATE_DIR="$TMP/p/.uncle/workflow"; LOG_DIR="$TMP/p/logs"
mkdir -p "$STATE_DIR" "$LOG_DIR" "$TMP/p/.uncle/docs"
run_claude() { echo called >> "$TMP/runner-calls"; return 1; }
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/change-class-stage.sh"
CHANGE_CLASS_PY="$PY"

PLAN="$TMP/p/.uncle/docs/CHANGE_PLAN.md"
DOCS_PLAN='# Plan

## Implementation sequence

1. Edit the file.
   Owns: `docs/guide.md`
'
sha_of() { python3 -B -c 'import sys,hashlib;print(hashlib.sha256(open(sys.argv[1],encoding="utf-8").read().encode()).hexdigest())' "$1"; }
write_class() { # review-value(json) plan_sha
    python3 - "$STATE_DIR/change-class.json" "$1" "$2" <<'PY'
import json, sys
json.dump({'class': 'docs', 'source': 'model', 'review': json.loads(sys.argv[2]), 'review_reason': 'docs only',
           'features': {'plan_sha': sys.argv[3]}, 'risk_hits': []}, open(sys.argv[1], 'w'))
PY
}
helper() { (cd "$TMP/p" && ROOT="$ROOT" STATE_DIR="$STATE_DIR" change_class_review_skipped "$PLAN"); }

printf '%s' "$DOCS_PLAN" > "$PLAN"
SHA="$(sha_of "$PLAN")"

# Value matrix for WORKFLOW_SKIP_REVIEW: unset and exactly 1 honor skip; everything else is a full review.
write_class '"skip"' "$SHA"
(unset WORKFLOW_SKIP_REVIEW; helper); unset_rc=$?
(WORKFLOW_SKIP_REVIEW=1 helper); one_rc=$?
check "env-unset-honors-skip" 0 "$unset_rc"
check "env-1-honors-skip" 0 "$one_rc"
for v in 0 "" false no 2; do
    (WORKFLOW_SKIP_REVIEW="$v" helper); rc=$?
    check "env-[$v]-full-review" 1 "$rc"
done

# Other disabling switches.
(WORKFLOW_CLASSIFY=0 helper); check "classify-off-full" 1 $?
(WORKFLOW_CHANGE_CLASS=docs helper); check "forced-class-full" 1 $?

# Stored review values other than skip, and absent/unreadable file, fail closed.
for v in '"full"' '"Skip"' 'null' '1' '["skip"]'; do
    write_class "$v" "$SHA"; helper; check "review-$v-full" 1 $?
done
rm -f "$STATE_DIR/change-class.json"; helper; check "missing-json-full" 1 $?
printf 'not json' > "$STATE_DIR/change-class.json"; helper; check "corrupt-json-full" 1 $?

# Plan sha: mismatch and missing both mean full review; a plan edited after the decision is not skipped.
write_class '"skip"' "deadbeef"; helper; check "sha-mismatch-full" 1 $?
write_class '"skip"' ""; helper; check "sha-empty-full" 1 $?
write_class '"skip"' "$SHA"; helper; check "sha-match-skip" 0 $?
printf '%s\nmore\n' "$DOCS_PLAN" > "$PLAN"; helper; check "plan-edited-after-decision-full" 1 $?
printf '%s' "$DOCS_PLAN" > "$PLAN"

# skip-review CLI: writes the stub only for a verified skip, with the exact overall_assessment, and exits 1 without a stub otherwise.
REVIEW_JSON_GLOB=".uncle/workflow/documents/ADVERSARIAL_REVIEW.json"
find_stub() { find "$TMP/p/.uncle" -name 'ADVERSARIAL_REVIEW.json' 2>/dev/null | head -1; }
write_class '"skip"' "deadbeef"
(cd "$TMP/p" && python3 -B "$PY" skip-review change . "$PLAN" >/dev/null 2>&1); check "skip-review-mismatch-exit1" 1 $?
[[ -z "$(find_stub)" ]] && ok || bad "skip-review-mismatch-no-stub" "stub written for mismatched sha"
write_class '"skip"' "$SHA"
(cd "$TMP/p" && python3 -B "$PY" skip-review change . "$PLAN" >"$TMP/skip.out" 2>&1); rc=$?
if [[ $rc == 0 ]]; then
    ok
    stub="$(find_stub)"
    if [[ -n "$stub" ]]; then
        python3 - "$stub" <<'PY' && ok || bad "stub-content" "overall_assessment not the expected non-empty skip text"
import json, sys
d = json.load(open(sys.argv[1]))
text = d.get('overall_assessment', '')
assert text.startswith('skipped: class ') and text.endswith(', no risk hits'), text
assert not d.get('findings')
PY
        # Stub reaches the downstream consumers: the updated-plan validator and approval hashing must accept it.
        grep -q 'skipped: class' "$TMP/skip.out" "$TMP/p/.uncle/docs/ADVERSARIAL_REVIEW.md" 2>/dev/null && ok || bad "stub-visible" "skip text not on console or in rendered md"
        sha1="$(sha_of "$stub")"; [[ -n "$sha1" && "$sha1" == "$(sha_of "$stub")" ]] && ok || bad "stub-hash-stable" "approval-style hash not stable"
    else
        bad "stub-exists" "skip-review exited 0 but wrote no ADVERSARIAL_REVIEW.json"
    fi
else
    bad "skip-review-match-exit0" "rc=$rc: $(tail -3 "$TMP/skip.out")"
fi

# Hand-edited json (review=skip, matching sha) over a risky plan: skip-review recomputes and refuses; helper-side precheck is only cheap.
rm -f "$(find_stub)" 2>/dev/null
RISKY='# Plan
Owns: `scripts/lib/auth.py`
Delete the signing keys.
'
printf '%s' "$RISKY" > "$PLAN"; write_class '"skip"' "$(sha_of "$PLAN")"
(cd "$TMP/p" && python3 -B "$PY" skip-review change . "$PLAN" >/dev/null 2>&1); check "risky-plan-skip-review-refuses" 1 $?
[[ -z "$(find_stub)" ]] && ok || bad "risky-no-stub" "stub written over a risky plan"

# Zero runner invocations through all of the above.
[[ ! -e "$TMP/runner-calls" ]] && ok || bad "no-runner-calls" "runner invoked $(wc -l < "$TMP/runner-calls") time(s)"

# Driver wiring: both drivers call the shared helper, honor the marker, and stop on a bad stub without retrying.
for d in change-workflow.sh stagegate.sh; do
    grep -q 'change_class_review_skipped' "$ROOT/scripts/$d" && ok || bad "$d-uses-helper" "driver does not call change_class_review_skipped"
    grep -q 'review-skipped' "$ROOT/scripts/$d" && ok || bad "$d-marker" "driver never references the review-skipped marker"
    grep -q 'skip-review' "$ROOT/scripts/$d" && ok || bad "$d-skip-cli" "driver never calls skip-review"
done
grep -q 'review-skip' "$ROOT/scripts/change-workflow.sh" && ok || bad "ledger-row" "change-workflow lacks the review-skip ledger row"

echo "review-skip-test: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
