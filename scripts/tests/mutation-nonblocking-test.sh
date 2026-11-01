#!/usr/bin/env bash
# Mutation (defect-injection) checks are documented and never block: a failing one is its own class, not a regression; it is in the
# report and the ledger; the NEGATIVE row does not decide the acceptance verdict; and the evidence-reconcile detour is off.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }
. "$ROOT/scripts/lib/green-check.sh"

# --- classification -----------------------------------------------------------------------------------------------------------
printf '0\tnpm test\n1\tnpx playwright test\n1\tnode tests/mutations/run.mjs\n1\tnpm run inject-defects\n0\tnode tests/mutation-list.test.js\n' > "$work/cur"
green_classify "" "$work/cur" > "$work/class"
eq "a passing command" "$(awk -F'\t' '$2=="npm test"{print $1}' "$work/class")" PASS
eq "a failing browser suite is still a regression" "$(awk -F'\t' '$2=="npx playwright test"{print $1}' "$work/class")" REGRESSION
eq "a failing mutation runner is its own class" "$(awk -F'\t' '$2=="node tests/mutations/run.mjs"{print $1}' "$work/class")" MUTATION
eq "a failing inject command too" "$(awk -F'\t' '$2=="npm run inject-defects"{print $1}' "$work/class")" MUTATION
eq "a passing mutation command is just a pass" "$(awk -F'\t' '$2=="node tests/mutation-list.test.js"{print $1}' "$work/class")" PASS
eq "only the real regression is counted" "$(green_regressions "$work/class")" 1
printf '0\tnpm test\n1\tnode tests/mutations/run.mjs\n' > "$work/cur2"
green_classify "" "$work/cur2" > "$work/class2"
eq "mutation failure alone is no regression" "$(green_regressions "$work/class2")" 0
printf '1\tnode tests/mutations/run.mjs\n' > "$work/base"; printf '1\tnode tests/mutations/run.mjs\n' > "$work/cur3"
green_classify "$work/base" "$work/cur3" > "$work/class3"
eq "a mutation failure that also failed before is still a mutation failure" "$(cut -f1 "$work/class3")" MUTATION

# --- the report and the ledger -------------------------------------------------------------------------------------------------
STATE_DIR="$work/state"; mkdir -p "$STATE_DIR"
record_nonblocking_failure() { printf '%s\t%s\n' "$1" "$2" >> "$STATE_DIR/nonblocking-test-failures.tsv"; }
green_report "$work/class2" "$work/green.md" .uncle/docs/PLAN.md "$work/log" 1
grep -q 'Mutation checks failed (documented; they never block the run)' "$work/green.md" || bad "the report does not document the mutation failure"
grep -q 'node tests/mutations/run.mjs' "$work/green.md" || bad "the report does not name the failing mutation command"
grep -q 'No regressions' "$work/green.md" || bad "a mutation failure must leave the report saying no regressions"
grep -q 'mutation check failed (documented, not blocking): node tests/mutations/run.mjs' "$STATE_DIR/nonblocking-test-failures.tsv" || bad "the ledger has no mutation entry"
green_report "$work/class2" "$work/green.md" .uncle/docs/PLAN.md "$work/log" 1
eq "the ledger entry is recorded once" "$(grep -c 'mutation check failed' "$STATE_DIR/nonblocking-test-failures.tsv")" 1
green_report "$work/class" "$work/green2.md" .uncle/docs/PLAN.md "$work/log" 1
grep -q 'regressed' "$work/green2.md" || bad "a real regression must still be reported as one"

# --- the NEGATIVE row is informational ------------------------------------------------------------------------------------------
review() {   # status of NEGATIVE
    python3 - "$work/review.json" "$1" <<'PY'
import json, sys
rows = [{'id': i, 'required': True, 'status': 'PASS', 'evidence': 'ok'} for i in ('COVERAGE', 'INTEGRITY', 'ASSERTIONS', 'ORACLE', 'RESULTS')]
rows.append({'id': 'NEGATIVE', 'required': True, 'status': sys.argv[2], 'evidence': 'no mutation evidence'})
json.dump({'schema': 'uncle.artifact/v1', 'kind': 'acceptance-report', 'rows': rows}, open(sys.argv[1], 'w'))
PY
    python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$work/review.json" COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS
}
for status in FAIL 'NOT RUN' BLOCKED-SETUP PASS; do eq "NEGATIVE $status does not decide the verdict" "$(review "$status")" PASS; done
python3 - "$work/review.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d['rows'][0]['status'] = 'FAIL'; json.dump(d, open(sys.argv[1], 'w'))
PY
eq "another row still does" "$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" "$work/review.json" COVERAGE INTEGRITY ASSERTIONS ORACLE NEGATIVE RESULTS)" REPAIR
eq "NEGATIVE is not listed as a blocker" "$(python3 -B "$ROOT/scripts/lib/acceptance_json.py" --ids "$work/review.json" FAIL)" COVERAGE

# --- the detour and the prompts -------------------------------------------------------------------------------------------------
[[ "$(grep -c 'WORKFLOW_MUTATION_EVIDENCE_REPAIR:-0' "$ROOT/scripts/stagegate.sh")" == 2 ]] || bad "the mutation-evidence reconcile is not opt-in at both sites"
for p in prompts/test-review.md prompts/change/test-review.md prompts/final-audit.md prompts/change/final-audit.md prompts/change/final-audit-review-worker.md; do
    grep -q 'Mutation checks are informational' "$ROOT/$p" || bad "$p does not say mutation checks are informational"
done
[[ $fail == 0 ]] && echo "mutation-nonblocking-test.sh: ok"
exit $fail
