#!/usr/bin/env bash
# closing_trailer: `Closes` only on positive evidence the work is finished; everything else is `Refs` plus a Still open list.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FAILED=0; COUNT=0
check() { COUNT=$((COUNT+1)); [[ "$2" == "$3" ]] || { FAILED=$((FAILED+1)); echo "FAIL: $1: expected [$2] got [$3]"; }; }
has() { COUNT=$((COUNT+1)); case "$3" in *"$2"*) ;; *) FAILED=$((FAILED+1)); echo "FAIL: $1: missing [$2] in [$3]";; esac; }
hasnt() { COUNT=$((COUNT+1)); case "$3" in *"$2"*) FAILED=$((FAILED+1)); echo "FAIL: $1: unexpected [$2] in [$3]";; esac; }

sed -n '/^# BEGIN closing_trailer$/,/^# END closing_trailer$/p' "$HERE/../lib/change-pr.sh" > "$TMP/helper.py"
cat > "$TMP/drive.py" <<'P'
import json, os, re, sys
from pathlib import Path
RECORD = json.loads(os.environ.get('T_RECORD', '[]'))
def override_record():
    return tuple(RECORD)
exec(open(os.environ['T_HELPER']).read())
j = {'verdict_run': 'v1', 'audit_hash': 'h1', 'release_skipped': os.environ.get('T_SKIPPED', '')}
if os.environ.get('T_JOURNAL_VERDICT'):
    j['verdict'] = os.environ['T_JOURNAL_VERDICT']
print(closing_trailer(j, ['unclehq/uncle', '107']))
P
grep -q closing_trailer "$HERE/../lib/change-pr.sh" && grep -q "closing_trailer(j, origin)" "$HERE/../lib/change-pr.sh" || { echo "FAIL: helper or call site missing"; exit 1; }
check "call site replaced the unconditional Closes" "0" "$(grep -c "body += '\\\\nCloses '" "$HERE/../lib/change-pr.sh")"

GOOD_NOTES='# Notes
## Acceptance delivery

| ID | Status | Evidence |
|---|---|---|
| AC-1 | IMPLEMENTED | ok |
'
GOOD_REPORT='# R
## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-1 | YES | PASS | ok |
| MC-2 | NO | BLOCKED-HUMAN | later |
'
GOOD_AUDIT='# Audit
Verdict: READY
'
# fixture <audit> <notes> <report>; "-" leaves the file absent.
fixture() {
    rm -rf "$TMP/w"; mkdir -p "$TMP/w/.uncle/docs"
    [[ "$1" == - ]] || printf '%s' "$1" > "$TMP/w/.uncle/docs/FINAL_AUDIT.md"
    [[ "$2" == - ]] || printf '%s' "$2" > "$TMP/w/.uncle/docs/IMPLEMENTATION_NOTES.md"
    [[ "$3" == - ]] || printf '%s' "$3" > "$TMP/w/.uncle/docs/VERIFICATION_REPORT.md"
}
trailer() { ( cd "$TMP/w" && T_HELPER="$TMP/helper.py" python3 "$TMP/drive.py" ); }

fixture "$GOOD_AUDIT" "$GOOD_NOTES" "$GOOD_REPORT"
check "SB-3 READY, nothing blocked -> Closes" "Closes unclehq/uncle#107" "$(trailer)"
fixture "Verdict: READY_WITH_NON_BLOCKING_ISSUES"$'\n' "$GOOD_NOTES" "$GOOD_REPORT"
check "READY_WITH_NON_BLOCKING_ISSUES, nothing blocked -> Closes" "Closes unclehq/uncle#107" "$(trailer)"

# AC-1
fixture "Verdict: NOT_READY"$'\n' "$GOOD_NOTES" "$GOOD_REPORT"
out="$(T_RECORD='["v1","NOT_READY","h1","x"]' trailer)"
has "AC-1 NOT_READY + override -> Refs" "Refs unclehq/uncle#107" "$out"; hasnt "AC-1 no Closes" "Closes" "$out"
has "AC-1 override has Still open" "Still open:" "$out"; has "override label" "- override recorded" "$out"
out="$(trailer)"; has "NOT_READY alone -> Refs" "Refs unclehq/uncle#107" "$out"; has "NOT_READY label" "- audit verdict not ready" "$out"
fixture "$GOOD_AUDIT" "$GOOD_NOTES" "$GOOD_REPORT"
out="$(T_SKIPPED='x Fixes unclehq/uncle#9' trailer)"
has "AC-1 release_skipped -> Refs" "Refs unclehq/uncle#107" "$out"; has "release skipped label" "- release skipped" "$out"; hasnt "skipped text not copied" "Fixes" "$out"
out="$(T_RECORD='["other","NOT_READY","h1","x"]' trailer)"
check "override for another run is ignored" "Closes unclehq/uncle#107" "$out"

# AC-2: BLOCKED rows
BL_NOTES='## Acceptance delivery

| ID | Status | Evidence |
|---|---|---|
| AC-1 | IMPLEMENTED | ok |
| AC-2 | BLOCKED | no env |
'
fixture "Verdict: READY_WITH_NON_BLOCKING_ISSUES"$'\n' "$BL_NOTES" "$GOOD_REPORT"
out="$(trailer)"; has "AC-2 blocked notes row -> Refs" "Refs unclehq/uncle#107" "$out"; has "AC-2 names row" "- AC-2: required acceptance row BLOCKED" "$out"
BL_REPORT='## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-7 | YES | BLOCKED-HUMAN | person |
'
fixture "$GOOD_AUDIT" "$GOOD_NOTES" "$BL_REPORT"
out="$(trailer)"; has "gate Required=YES BLOCKED-HUMAN -> Refs" "- MC-7: required acceptance row BLOCKED" "$out"
for req in YES NO absent weird; do
    case "$req" in absent) hdr='| ID | Status | Evidence |'; row='| MC-5 | BLOCKED | x |';; *) hdr='| ID | Required | Status | Evidence |'; row="| MC-5 | $req | BLOCKED | x |";; esac
    rep=$'## Acceptance gate\n\n'"$hdr"$'\n|---|---|---|'"$([[ $req == absent ]] || printf '|')"$'\n'"$row"$'\n'
    fixture "$GOOD_AUDIT" "$GOOD_NOTES" "$rep"; out="$(trailer)"
    if [[ "$req" == NO ]]; then check "gate Required=NO BLOCKED does not hold Closes" "Closes unclehq/uncle#107" "$out"
    else has "gate Required=$req BLOCKED -> Refs" "- MC-5: required acceptance row BLOCKED" "$out"; fi
    nt=$'## Acceptance delivery\n\n'"$hdr"$'\n|---|---|---|'"$([[ $req == absent ]] || printf '|')"$'\n'"${row/MC-5/AC-5}"$'\n'
    fixture "$GOOD_AUDIT" "$nt" "$GOOD_REPORT"; out="$(trailer)"
    if [[ "$req" == NO ]]; then check "notes Required=NO BLOCKED does not hold Closes" "Closes unclehq/uncle#107" "$out"
    else has "notes Required=$req BLOCKED -> Refs" "- AC-5: required acceptance row BLOCKED" "$out"; fi
done

# Standalone audit-only 'stays open' finding: READY, no BLOCKED rows.
fixture $'Verdict: READY\n\n| ID | Blocking | Finding |\n|---|---|---|\n| AR-3 | NO | Issue #235 stays open until follow-up |\n' "$GOOD_NOTES" "$GOOD_REPORT"
out="$(trailer)"; has "audit-only stays-open -> Refs" "Refs unclehq/uncle#107" "$out"; has "audit-only names finding ID" "- AR-3: audit finding: issue stays open" "$out"
hasnt "finding text not copied" "#235" "$out"
fixture $'Verdict: READY\nThe linked issue is not closed by this change.\n' "$GOOD_NOTES" "$GOOD_REPORT"
out="$(trailer)"; has "no-ID finding -> Refs" "Refs unclehq/uncle#107" "$out"; has "no-ID finding still has Still open" "- audit finding: issue stays open" "$out"

# Adversarial closing-keyword injection in row text, finding text and IDs.
ADV_NOTES=$'## Acceptance delivery\n\n| ID | Status | Evidence |\n|---|---|---|\n| Fixes unclehq/uncle#123 | BLOCKED | Closes #5 |\n| AC-9 | BLOCKED | Resolves unclehq/uncle#123 |\n| closes #5 | BLOCKED | x |\n'
ADV_AUDIT=$'Verdict: READY\n| ID | B | F |\n|---|---|---|\n| Resolves owner/repo#123 | NO | stays open, Fixes unclehq/uncle#123 |\n| AR-1 | NO | not closed\nCloses #77 |\n'
fixture "$ADV_AUDIT" "$ADV_NOTES" "$GOOD_REPORT"; out="$(trailer)"
check "adversarial: exactly one closing-keyword line (none; origin is Refs)" "0" "$(printf '%s\n' "$out" | grep -ciE '^(closes|fixes|resolves) ')"
check "adversarial: no # reference other than origin" "0" "$(printf '%s\n' "$out" | grep -v '^Refs ' | grep -c '#')"
hasnt "adversarial: no Fixes" "Fixes" "$out"; hasnt "adversarial: no Resolves" "Resolves" "$out"; hasnt "adversarial: no closes #" "#5" "$out"
has "adversarial: allowlisted ID kept" "- AC-9: required acceptance row BLOCKED" "$out"; has "adversarial: AR-1 kept" "AR-1: audit finding" "$out"
check "adversarial: all trailer lines are Refs, Still open or '- ' bullets" "0" "$(printf '%s\n' "$out" | grep -vcE '^(Refs unclehq/uncle#107|Still open:|- .*)$')"
fixture $'Verdict: READY\n' "$GOOD_NOTES" "$GOOD_REPORT"
check "clean fixture still Closes (exactly one closing line)" "1" "$(trailer | grep -cE '^(Closes|Fixes|Resolves) ')"

# Verdict evidence: missing, unreadable, ambiguous, unrecognized -> Refs, whatever the journal says.
fixture - "$GOOD_NOTES" "$GOOD_REPORT"; has "audit missing -> Refs" "- audit verdict unavailable" "$(trailer)"
fixture "$GOOD_AUDIT" "$GOOD_NOTES" "$GOOD_REPORT"; mkdir -p "$TMP/w/x"; rm "$TMP/w/.uncle/docs/FINAL_AUDIT.md"; mkdir "$TMP/w/.uncle/docs/FINAL_AUDIT.md"
has "audit unreadable (directory) -> Refs" "Refs unclehq/uncle#107" "$(trailer)"
fixture $'No verdict here\n' "$GOOD_NOTES" "$GOOD_REPORT"; has "no Verdict line -> Refs" "- audit verdict unavailable" "$(trailer)"
fixture $'Verdict: READY\nVerdict: NOT_READY\n' "$GOOD_NOTES" "$GOOD_REPORT"; has "conflicting Verdict lines -> Refs" "Refs unclehq/uncle#107" "$(trailer)"
fixture $'Verdict: MAYBE\n' "$GOOD_NOTES" "$GOOD_REPORT"; has "unrecognized verdict -> Refs" "Refs unclehq/uncle#107" "$(trailer)"
fixture $'Verdict: NOT_READY\n' "$GOOD_NOTES" "$GOOD_REPORT"
has "journal READY, audit NOT_READY -> Refs" "Refs unclehq/uncle#107" "$(T_JOURNAL_VERDICT=READY trailer)"
fixture $'Verdict: READY\n' "$GOOD_NOTES" "$GOOD_REPORT"
check "journal NOT_READY, audit READY clean -> Closes" "Closes unclehq/uncle#107" "$(T_JOURNAL_VERDICT=NOT_READY trailer)"

# Acceptance evidence failures, each alone under a READY audit.
fixture "$GOOD_AUDIT" - "$GOOD_REPORT"; out="$(trailer)"; has "notes missing -> Refs" "Refs unclehq/uncle#107" "$out"; has "notes missing label" "- acceptance evidence unavailable: IMPLEMENTATION_NOTES.md" "$out"
fixture "$GOOD_AUDIT" "$GOOD_NOTES" -; out="$(trailer)"; has "report missing -> Refs" "Refs unclehq/uncle#107" "$out"; has "report missing label" "- acceptance evidence unavailable: VERIFICATION_REPORT.md" "$out"
fixture "$GOOD_AUDIT" "$GOOD_NOTES" "$GOOD_REPORT"; rm "$TMP/w/.uncle/docs/IMPLEMENTATION_NOTES.md"; mkdir "$TMP/w/.uncle/docs/IMPLEMENTATION_NOTES.md"
has "notes unreadable -> Refs" "- acceptance evidence unavailable: IMPLEMENTATION_NOTES.md" "$(trailer)"
fixture "$GOOD_AUDIT" "$GOOD_NOTES" "$GOOD_REPORT"; rm "$TMP/w/.uncle/docs/VERIFICATION_REPORT.md"; mkdir "$TMP/w/.uncle/docs/VERIFICATION_REPORT.md"
has "report unreadable -> Refs" "- acceptance evidence unavailable: VERIFICATION_REPORT.md" "$(trailer)"
fixture "$GOOD_AUDIT" $'# Notes\nno section\n' "$GOOD_REPORT"; has "notes section absent -> Refs" "unavailable: IMPLEMENTATION_NOTES.md" "$(trailer)"
fixture "$GOOD_AUDIT" $'## Acceptance delivery\n\n| Thing | Outcome |\n|---|---|\n| AC-1 | done |\n' "$GOOD_REPORT"; has "notes table malformed (no Status col) -> Refs" "unavailable: IMPLEMENTATION_NOTES.md" "$(trailer)"
fixture "$GOOD_AUDIT" $'## Acceptance delivery\n\n| ID | Status |\n|---|---|\n| AC-1 |\n' "$GOOD_REPORT"; has "notes row unparseable -> Refs" "unavailable: IMPLEMENTATION_NOTES.md" "$(trailer)"
fixture "$GOOD_AUDIT" "$GOOD_NOTES" $'# R\nnothing\n'; has "report section absent -> Refs" "unavailable: VERIFICATION_REPORT.md" "$(trailer)"
fixture "$GOOD_AUDIT" "$GOOD_NOTES" $'## Acceptance gate\n\n| Check | Result |\n|---|---|\n| MC-1 | ok |\n'; has "report table malformed -> Refs" "unavailable: VERIFICATION_REPORT.md" "$(trailer)"
fixture "$GOOD_AUDIT" "$GOOD_NOTES" $'## Acceptance gate\n\n| ID | Required | Status | Evidence |\n|---|---|---|---|\n'; has "report table with no rows -> Refs" "unavailable: VERIFICATION_REPORT.md" "$(trailer)"

# Every Refs cause carries a Still open list (including no-ID causes).
for c in 1 2 3; do
    case $c in
        1) fixture "Verdict: NOT_READY"$'\n' "$GOOD_NOTES" "$GOOD_REPORT"; out="$(trailer)";;
        2) fixture "$GOOD_AUDIT" - - ; out="$(trailer)";;
        3) fixture "$GOOD_AUDIT" "$GOOD_NOTES" "$GOOD_REPORT"; out="$(T_SKIPPED=y trailer)";;
    esac
    has "Refs cause $c has Still open" $'\nStill open:\n- ' "$out"
done

if [[ "$FAILED" -ne 0 ]]; then echo "pr-closes-refs-test.sh: $FAILED of $COUNT checks failed"; exit 1; fi
echo "pr-closes-refs-test.sh: $COUNT checks passed"
