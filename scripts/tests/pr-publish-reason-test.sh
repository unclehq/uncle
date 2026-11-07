#!/usr/bin/env bash
# change_pr_publish / change_pr_complete reason reporting (issue: no silent skipped PR).
# Engine, gh and the unit-path gates are stubbed; the AC-5 section uses the REAL
# assert_tree_matches_attested on a fixture git repo and a stub issue_close_eligible that
# reproduces the real function's hash comparison (hash of artifact arg 6 vs verdict field 3).
# Bash 3.2 compatible.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIB="$ROOT/scripts/lib/change-pr.sh"
EXTRAS="$ROOT/scripts/lib/finished_extras.py"
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }
eq() { if [[ "$2" == "$3" ]]; then ok; else bad "$1: expected [$3] got [$2]"; fi; }
has() { if grep -q -- "$3" <<<"$2"; then ok; else bad "$1: missing [$3] in [$2]"; fi; }
hasnt() { if grep -q -- "$3" <<<"$2"; then bad "$1: unexpected [$3] in [$2]"; else ok; fi; }

CANARY_TOKEN="CANARY-TOKEN-9f3a"
CANARY_URL="https://user:CANARYPASS@example.com/x.git"

# run_publish <label> : env knobs STUB_* / ORIGIN_EMPTY / VCLASS / INTERACTIVE / PRESET / REAL_ASSERT
# Results: RC OUT ERR REASON HANDOFFS ISSUES
run_publish() {
    local T; T="$(mktemp -d)"
    (
        cd "$T" || exit 99
        mkdir -p .uncle/workflow/pr .uncle/workflow/documents .uncle/docs
        if [[ "${ORIGIN_EMPTY:-0}" == 1 ]]; then : > origin; else printf 'owner/repo\t7\tgh\n' > origin; fi
        printf 'run1\t%s\thash1\n' "${VCLASS:-READY}" > verdict
        if [[ "${REAL_ASSERT:-0}" == 1 ]]; then
            git init -q . && git config user.email t@t && git config user.name t && git config commit.gpgsign false
            printf '.uncle/\norigin\nverdict\n' > .gitignore; echo a > a.txt
            git add -A && git commit -q -m init
            printf '{"audit":"json"}\n' > .uncle/workflow/documents/FINAL_AUDIT.json
            printf 'rendered markdown\n' > .uncle/docs/FINAL_AUDIT.md
            printf 'run1\t%s\t%s\n' "${VCLASS:-READY}" "$(shasum -a 256 .uncle/workflow/documents/FINAL_AUDIT.json | cut -d' ' -f1)" > verdict
        fi
        # shellcheck disable=SC1090
        source "$LIB"
        ORIGIN_FILE="$T/origin"; VERDICT_FILE="$T/verdict"; MARKER_FILE="$T/marker"; ORIGIN_BOUND=1
        STATE_DIR=".uncle/workflow"; CLOSE_ISSUE=1
        origin_field() { echo "f$2"; }
        origin_fetch_method() { echo gh; }
        issue_close_eligible() {
            echo x >> "$T/issue.calls"
            if [[ "${REAL_ASSERT:-0}" == 1 ]]; then
                local want got
                want="$(awk -F'\t' 'NR==1{print $3}' "$4")"
                got="$(shasum -a 256 "$6" 2>/dev/null | cut -d' ' -f1)"
                [[ "$want" == "$got" ]] || { echo "$6 changed after it was classified" >&2; return 1; }
                return 0
            fi
            return "${STUB_ISSUE:-0}"
        }
        if [[ "${REAL_ASSERT:-0}" != 1 ]]; then
            assert_tree_matches_attested() {
                [[ "${STUB_ASSERT:-0}" == 0 ]] && return 0
                echo "tracked file not clean: one" >&2; echo "path differs from the attested tree (M): two" >&2
                return 1
            }
        fi
        change_pr_engine() {
            case "$1" in
                validate)
                    echo v >> "$T/validate.calls"
                    echo "$CANARY_TOKEN $CANARY_URL" >&2
                    if [[ "$(wc -l < "$T/validate.calls" | tr -d ' ')" -ge 2 ]]; then return "${STUB_REVALIDATE:-0}"; fi
                    return "${STUB_VALIDATE:-0}" ;;
                verdict-override) return "${STUB_OVERRIDE:-1}" ;;
                commit-tree)
                    [[ "${STUB_TREE_FAIL:-0}" == 1 ]] && return 1
                    echo "${STUB_TREE:-abc123}" ;;
                handoff)
                    echo h >> "$T/handoff.calls"
                    echo "$CANARY_TOKEN $CANARY_URL"; echo "$CANARY_TOKEN $CANARY_URL" >&2
                    printf '{"phase":"%s","draft":%s,"url":"%s","number":"3"}\n' "${STUB_PHASE:-created}" \
                        "$([[ "${STUB_DRAFT:-0}" == 1 ]] && echo true || echo false)" "$CANARY_URL" \
                        | tee .uncle/workflow/pr/journal.json > /dev/null
                    return "${STUB_HANDOFF:-0}" ;;
                *) return 0 ;;
            esac
        }
        gh() { echo "$CANARY_TOKEN $CANARY_URL" >&2; return 1; }
        CHANGE_PR_EXTRAS_REASON="${PRESET:-}"
        change_pr_publish "${INTERACTIVE:-0}" </dev/null >"$T/out" 2>"$T/err"
        echo $? > "$T/rc"
        printf '%s' "$CHANGE_PR_EXTRAS_REASON" > "$T/reason"
    )
    RC="$(cat "$T/rc" 2>/dev/null)"; OUT="$(cat "$T/out" 2>/dev/null)"; ERR="$(cat "$T/err" 2>/dev/null)"
    REASON="$(cat "$T/reason" 2>/dev/null)"
    HANDOFFS="$(wc -l < "$T/handoff.calls" 2>/dev/null | tr -d ' ')"; HANDOFFS="${HANDOFFS:-0}"
    ISSUES="$(wc -l < "$T/issue.calls" 2>/dev/null | tr -d ' ')"; ISSUES="${ISSUES:-0}"
    rm -rf "$T"
}

# expect_nopr <label> <key> : exact key, return 0, exactly one 'PR not created' line, no leak
expect_nopr() {
    eq "$1 rc" "$RC" 0
    eq "$1 reason" "$REASON" "$2"
    eq "$1 one line" "$(grep -c '^PR not created:' <<<"$ERR")" 1
    eq "$1 keyed line" "$(grep -c "^PR not created: $2" <<<"$ERR")" 1
    local line; line="$(grep '^PR not created:' <<<"$ERR")"
    hasnt "$1 no token" "$line" "CANARY"
    hasnt "$1 no url" "$line" "://"
}

# (1) validate failures
STUB_VALIDATE=1 run_publish;                  expect_nopr "validate-1" validate-failed
eq "validate-1 no handoff" "$HANDOFFS" 0
STUB_VALIDATE=2 run_publish;                  expect_nopr "validate-2" validate-failed
STUB_VALIDATE=3 run_publish;                  expect_nopr "v3 no override" verdict-not-ready
STUB_VALIDATE=3 INTERACTIVE=1 STUB_OVERRIDE=1 run_publish; expect_nopr "v3 declined" verdict-not-ready
STUB_VALIDATE=3 UNCLE_AUTO_PUBLISH=1 STUB_OVERRIDE=1 run_publish; expect_nopr "v3 auto declined" verdict-not-ready
STUB_VALIDATE=3 INTERACTIVE=1 STUB_OVERRIDE=0 STUB_REVALIDATE=1 run_publish; expect_nopr "v3 revalidate fails" validate-failed
eq "v3 revalidate no handoff" "$HANDOFFS" 0

# (2) gates
ORIGIN_EMPTY=1 run_publish
eq "empty origin reason" "$REASON" published; eq "empty origin handoff" "$HANDOFFS" 1; eq "empty origin no issue gate" "$ISSUES" 0
hasnt "empty origin no issue-not-eligible" "$ERR" "issue-not-eligible"
VCLASS=NOT_READY STUB_VALIDATE=3 INTERACTIVE=1 STUB_OVERRIDE=0 run_publish
eq "override reason" "$REASON" published-draft-unreviewed; eq "override handoff" "$HANDOFFS" 1; eq "override issue gate not run" "$ISSUES" 0
has "override names verdict" "$ERR" "PR published as unreviewed draft: published-draft-unreviewed: verdict NOT_READY"
STUB_ISSUE=1 run_publish;                     expect_nopr "issue ineligible" issue-not-eligible
eq "issue ineligible no handoff" "$HANDOFFS" 0; eq "issue gate ran" "$ISSUES" 1
STUB_TREE_FAIL=1 STUB_ASSERT=1 run_publish;   expect_nopr "tree-mismatch" tree-mismatch
eq "tree-mismatch no handoff" "$HANDOFFS" 0
has "tree-mismatch keeps existing stderr" "$ERR" "tracked file not clean: one"
has "tree-mismatch keeps existing stderr 2" "$ERR" "path differs from the attested tree"
has "tree-mismatch keeps Publish refused" "$ERR" "Publish refused"
STUB_ASSERT=1 run_publish;                    expect_nopr "tree-mismatch attested" tree-mismatch

# (3) handoff outcomes
run_publish;                                  eq "published" "$REASON" published; eq "published rc" "$RC" 0; eq "published handoff" "$HANDOFFS" 1
hasnt "published no PR not created" "$ERR" "^PR not created:"
STUB_PHASE=created run_publish;               eq "rerun created" "$REASON" published
STUB_HANDOFF=1 run_publish;                   expect_nopr "handoff 1" handoff-failed; has "handoff 1 code" "$(grep '^PR not created:' <<<"$ERR")" "1"
STUB_HANDOFF=3 run_publish;                   expect_nopr "handoff 3" handoff-failed; has "handoff 3 code" "$(grep '^PR not created:' <<<"$ERR")" "3"
STUB_DRAFT=1 run_publish;                     has "draft stated" "$(grep '^PR published' <<<"$ERR")" "draft"
VCLASS=NOT_READY UNCLE_AUTO_PUBLISH=1 run_publish
eq "auto non-ready reason" "$REASON" published-draft-unreviewed
has "auto names verdict" "$ERR" "verdict NOT_READY"
STUB_PHASE=prepared run_publish;              expect_nopr "handoff-incomplete" handoff-incomplete

# (4) preset sentinel replaced on every path
for knobs in "STUB_VALIDATE=1" "STUB_ISSUE=1" "STUB_ASSERT=1" "STUB_HANDOFF=1" "STUB_PHASE=prepared" "STUB_PHASE=created"; do
    env "$knobs" bash -c 'true'
    eval "$knobs PRESET=SENTINEL run_publish"
    if [[ "$REASON" == SENTINEL || -z "$REASON" ]]; then bad "preset replaced on $knobs: [$REASON]"; else ok; fi
done

# (6) leak canary on a handoff-failed path and a published path
STUB_HANDOFF=3 run_publish
hasnt "canary reason" "$REASON" "CANARY"
hasnt "canary pr line" "$(grep '^PR ' <<<"$ERR")" "CANARY"

# (7) change_pr_complete table
run_complete() { # mode: unattended|headless|interactive|disabled ; STUB_REASON
    local T; T="$(mktemp -d)"
    (
        cd "$T" || exit 99
        # shellcheck disable=SC1090
        source "$LIB"
        UNATTENDED_FILE="$T/unatt"; ORIGIN_FILE="$T/origin"; CLOSE_ISSUE=1
        case "$1" in
            unattended) printf 'o/r\t1\tgh\n' > "$ORIGIN_FILE"; UNATTENDED=1 ;;
            headless)   : > "$ORIGIN_FILE"; UNATTENDED=1 ;;
            interactive) printf 'o/r\t1\tgh\n' > "$ORIGIN_FILE"; UNATTENDED=0 ;;
            disabled)   : > "$ORIGIN_FILE"; UNATTENDED=1 ;;
        esac
        change_pr_person_channel() { return 1; }
        assert_tree_matches_attested() { return 0; }
        change_pr_engine() { [[ "$1" == completed-signing-resume ]] && return "${STUB_RESUME:-0}"; return 0; }
        change_pr_publish() { CHANGE_PR_EXTRAS_REASON="${STUB_REASON:-}"; return 0; }
        change_pr_complete >/dev/null 2>&1 </dev/null
        printf '%s' "$CHANGE_PR_EXTRAS_REASON" > "$T/reason"
    )
    REASON="$(cat "$T/reason" 2>/dev/null)"; rm -rf "$T"
}
for m in unattended headless interactive; do
    STUB_REASON=tree-mismatch run_complete "$m";  eq "complete $m keeps reason" "$REASON" tree-mismatch
    STUB_REASON=published run_complete "$m";      eq "complete $m keeps published" "$REASON" published
done
for m in unattended headless; do
    STUB_REASON="" run_complete "$m";             eq "complete $m empty -> pending" "$REASON" publication-pending
done
STUB_RESUME=1 run_complete disabled;              eq "complete handoff-disabled" "$REASON" handoff-disabled

# (8) finished_extras.py labels
state="$(mktemp -d)"
pending="$(python3 -I "$EXTRAS" print --state "$state" --kind change --reason publication-pending | sed -n 2p)"
eq "pending label" "$pending" "PR: not created (publication pending)"
for key in published published-draft-unreviewed validate-failed verdict-not-ready issue-not-eligible tree-mismatch handoff-failed handoff-incomplete handoff-disabled no-base-commit not-published; do
    line="$(python3 -I "$EXTRAS" print --state "$state" --kind change --reason "$key" | sed -n 2p)"
    has "label $key prefix" "$line" "^PR: "
    if [[ "$line" == "$pending" ]]; then bad "label $key must not fall back to pending"; else ok; fi
done
for weird in "totally-unknown-key" "" "bad
value" "http://u:tok@host/x" "published; rm -rf"; do
    out="$(python3 -I "$EXTRAS" print --state "$state" --kind change --reason "$weird")"
    eq "fallback for [$weird]" "$(sed -n 2p <<<"$out")" "$pending"
    if [[ -n "$weird" ]]; then hasnt "no echo of [$weird]" "$out" "tok@host"; fi
done
rm -rf "$state"

# (9) AC-5 regression with real tree assertion and hash-checking issue gate
REAL_ASSERT=1 run_publish
eq "AC-5 reason" "$REASON" published
eq "AC-5 handoff reached" "$HANDOFFS" 1
eq "AC-5 issue gate ran" "$ISSUES" 1
hasnt "AC-5 no skip" "$ERR" "^PR not created:"
# gates not removed
grep -q 'issue_close_eligible "\$recorded"' "$LIB" && ok || bad "issue gate call missing"
grep -q 'READY|READY_WITH_NON_BLOCKING_ISSUES)' "$LIB" && ok || bad "verdict case missing"
grep -q 'assert_tree_matches_attested "\$attested" pre ||' "$LIB" && ok || bad "tree gate missing"
grep -q '|| return 0' "$LIB" && ok || bad "issue gate return missing"
# SI3: no force push anywhere in the library
if grep -nE 'push[^#]*(--force|-f[ "'"'"']|--force-with-lease)|\+refs/' "$LIB" >/dev/null; then bad "force push present"; else ok; fi

echo "pr-publish-reason-test: $PASS passed, $FAIL failed"
[[ "$FAIL" == 0 ]]
