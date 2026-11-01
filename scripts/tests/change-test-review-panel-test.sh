#!/usr/bin/env bash
# The change driver's test review is the lens panel stagegate.sh runs: investigation per lens, finalize per lens, collation by the driver, one-lens retry.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CW="$ROOT/scripts/change-workflow.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
fail=0
bad() { echo "FAIL: $1" >&2; fail=1; }

fn() { awk -v n="$1" '$0 ~ "^"n"\\(\\) \\{" {p=1} p {print} p && /^}/ {exit}' "$CW"; }
FUNCS="$(fn change_test_review_lenses; fn change_test_review_prompt; fn change_run_test_review_investigate; fn change_run_test_review_panel)"
[[ -n "$FUNCS" ]] || bad "could not extract the functions"

n=0
newproject() {
    project="$work/p$((++n))"; mkdir -p "$project/.uncle/workflow/documents" "$project/.uncle/workflow/logs" "$project/.uncle/docs" "$project/src"
    printf 'PASS\tnpm ci\nPASS\tnpx vitest run\n' > "$project/.uncle/workflow/green-check.tsv"
    echo 'x' > "$project/src/a.js"
    : > "$project/.uncle/workflow/calls"
}
run_in() {   # <project> <script>; BAD_LENS=<lens> makes that lens's first answer garbage
    local project="$1"; shift
    ( cd "$project" && env -i PATH="$PATH" HOME="$HOME" ${ENVX:-X=1} bash --norc --noprofile -c "
        ROOT='$ROOT'; STATE_DIR='.uncle/workflow'; LOG_DIR='.uncle/workflow/logs'
        change_class_panel() { printf '%s' \"\$2\"; }
        workflow_model_capacity() { echo 3; }
        run_codex() {   # prompt output name effort
            echo \"\$3\" >> .uncle/workflow/calls; cp \"\$1\" \".uncle/workflow/prompt-\$3.md\"
            case \"\$3\" in
                *-investigate) if [[ \"\$3\" == *\"\${JUNK_LENS:-none}\"* ]]; then printf '{\"rows\":[]}' > \"\$2\"; else printf '# Investigation\n\nlooked at the tests\n' > \"\$2\"; fi ;;
                test-review-worker-*)
                    lens=\"\${3#test-review-worker-}\"; lens=\"\${lens%-retry}\"
                    if [[ \"\$lens\" == \"\${BAD_LENS:-none}\" && \"\$3\" != *-retry ]]; then echo 'sorry, no' > \"\$2\"; return 0; fi
                    if [[ \$lens == oracle ]]; then rows='{\"id\":\"ORACLE\",\"status\":\"PASS\",\"evidence\":\"grounded\"},{\"id\":\"NEGATIVE\",\"status\":\"PASS\",\"evidence\":\"killed\"}'
                    else u=\$(printf '%s' \$lens | tr a-z A-Z); rows=\"{\\\"id\\\":\\\"\$u\\\",\\\"status\\\":\\\"PASS\\\",\\\"evidence\\\":\\\"ok\\\"}\"; fi
                    printf '{\"schema\":\"uncle.artifact/v1\",\"kind\":\"test-review-worker-packet\",\"rows\":[%s]}' \"\$rows\" > \"\$2\" ;;
            esac
        }
        $FUNCS
        $*" 2>&1 )
}

# --- the panel judges from the driver's results and writes the canonical review ------------------------------------------------------------
newproject
out="$(run_in "$project" 'change_run_test_review_panel; echo rc=$?')"
grep -q 'rc=0' <<< "$out"                                 || bad "the panel failed: $out"
[[ -s "$project/.uncle/workflow/documents/TEST_REVIEW.json" && -s "$project/.uncle/docs/TEST_REVIEW.md" ]] || bad "no review was written"
eq() { [[ "$2" == "$3" ]] || bad "$1: got '$2', want '$3'"; }
eq "one investigation per lens" "$(grep -c -- '-investigate$' "$project/.uncle/workflow/calls")" 3
eq "one finalize per lens" "$(grep -c '^test-review-worker-[a-z]*$' "$project/.uncle/workflow/calls")" 3
eq "the review has every row" "$(python3 -c "import json;print(' '.join(sorted(r['id'] for r in json.load(open('$project/.uncle/workflow/documents/TEST_REVIEW.json'))['rows'])))")" "ASSERTIONS COVERAGE INTEGRITY NEGATIVE ORACLE RESULTS"
eq "INTEGRITY is the driver's, from the green check" "$(python3 -c "import json;print([r['status'] for r in json.load(open('$project/.uncle/workflow/documents/TEST_REVIEW.json'))['rows'] if r['id']=='INTEGRITY'][0])")" PASS
[[ -s "$project/.uncle/workflow/documents/TEST_REVIEW_WORKERS.json" ]] || bad "TEST_REVIEW_WORKERS.json was not written"
p="$project/.uncle/workflow/prompt-test-review-worker-coverage.md"
grep -q 'CHANGE_TEST_REPORT.md' "$p" || bad "the worker prompt does not read the change test report"
grep -q 'AUTOMATED_TEST_REPORT\|UPDATED_PROJECT_PLAN' "$p" "$project/.uncle/workflow/prompt-test-review-worker-coverage-investigate.md" && bad "a worker prompt names new-application documents"
grep -q 'CHANGE_PLAN.md' "$project/.uncle/workflow/prompt-test-review-worker-coverage-investigate.md" || bad "the investigation does not read the change plan"
grep -q 'looked at the tests' "$p" || bad "the investigation was not handed to the finalize pass"
grep -q 'Focus only on \*\*ORACLE\*\* and \*\*NEGATIVE\*\*' "$project/.uncle/workflow/prompt-test-review-worker-oracle.md" || bad "the oracle lens does not own NEGATIVE"

# --- the investigation is not repeated for an unchanged tree, and is for a changed one ------------------------------------------------------
before="$(wc -l < "$project/.uncle/workflow/calls" | tr -d ' ')"
run_in "$project" 'change_run_test_review_investigate; wait' > /dev/null
eq "an unchanged tree is not investigated again" "$(wc -l < "$project/.uncle/workflow/calls" | tr -d ' ')" "$before"
echo 'y' >> "$project/src/a.js"
run_in "$project" 'change_run_test_review_investigate; wait' > /dev/null
[[ "$(wc -l < "$project/.uncle/workflow/calls" | tr -d ' ')" -gt "$before" ]] || bad "a repaired tree must be investigated afresh"

# --- one bad lens is retried alone ------------------------------------------------------------------------------------------------------------
newproject
out="$(ENVX=BAD_LENS=assertions run_in "$project" 'change_run_test_review_panel; echo rc=$?')"
grep -q 'rc=0' <<< "$out"                                 || bad "a single bad lens sank the panel: $out"
grep -q 'worker assertions returned an invalid packet; retrying that worker once' <<< "$out" || bad "the retry was not announced"
eq "only that lens was retried" "$(grep -c -- '-retry$' "$project/.uncle/workflow/calls")" 1
grep -q 'test-review-worker-assertions-retry' "$project/.uncle/workflow/calls" || bad "the wrong lens was retried"

# --- an investigation that is not a Markdown report is never pasted into the finalize prompt ----------------------------------------------
newproject
ENVX=JUNK_LENS=assertions run_in "$project" 'change_run_test_review_panel' > /dev/null
grep -q 'No usable investigation' "$project/.uncle/workflow/prompt-test-review-worker-assertions.md" || bad "a junk investigation was trusted"
grep -q 'looked at the tests' "$project/.uncle/workflow/prompt-test-review-worker-coverage.md" || bad "a good investigation was dropped"

# --- switches ------------------------------------------------------------------------------------------------------------------------------------------
newproject
out="$(ENVX=WORKFLOW_TEST_REVIEW_PANEL=0 run_in "$project" 'change_run_test_review_panel; echo rc=$?')"
grep -q 'rc=0' <<< "$out" && [[ ! -s "$project/.uncle/workflow/calls" ]]   || bad "WORKFLOW_TEST_REVIEW_PANEL=0 still ran the panel"
newproject
ENVX=WORKFLOW_TEST_REVIEW_PRESTART=0 run_in "$project" 'change_run_test_review_investigate; echo' > /dev/null
[[ ! -s "$project/.uncle/workflow/calls" ]]                                || bad "WORKFLOW_TEST_REVIEW_PRESTART=0 still started the investigation"

# --- the driver uses the panel first and the single reviewer only as a fallback ------------------------------------------------------------
tr_block="$(awk '/^        TEST_REVIEW\)/{p=1;next} p&&/^        [A-Z_]+\)$/{exit} p{print}' "$CW")"
grep -q 'change_run_test_review_investigate' <<< "$tr_block" || bad "TEST_REVIEW does not start the investigation early"
printf '%s\n' "$tr_block" | awk '/change_run_test_review_investigate/{a=NR} /wait_green_check_bg/{b=NR} END{exit !(a && b && a<b)}' || bad "the investigation must start before waiting for the green check"
grep -q 'change_run_test_review_panel &&' <<< "$tr_block" || bad "TEST_REVIEW does not run the panel"
grep -q 'test-review \\' <<< "$tr_block" || bad "the single-reviewer fallback was lost"
[[ $fail == 0 ]] && echo "change-test-review-panel-test.sh: ok"
exit $fail
