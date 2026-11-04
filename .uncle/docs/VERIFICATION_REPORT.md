# Verification report

## Findings

### MC-101

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. Classifications code defect, requirement gap, owner decision, none, plus non-recovery tool bug; typed /report.
- **Expected result:** Refusal, no draft/gh, no banner hint
- **Actual result:** Refusal line printed, nothing armed, no draft, no gh, no chat. No /report hint exists in any banner (uncle_tui.py:4137,5002).
- **Defects:** None

### MC-104

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. /report then `no`, empty, `/resume`.
- **Expected result:** Cancelled, no create, draft kept, not forwarded, triage-issue unchanged
- **Actual result:** All cancel with one-line message; zero gh create; draft kept; chat not called; hash unchanged.
- **Defects:** None

### MC-105

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. /report then `YES` (input is stripped by the composer).
- **Expected result:** One create with --repo/--title/--body-file, URL shown, draft kept
- **Actual result:** One create, URL issues/999 shown after extra output, draft kept.
- **Defects:** None

### MC-106

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. yes with gh absent, auth failing, create exiting 0 with no URL.
- **Expected result:** Each case: draft kept, copyable gh issue create command; (c) says may already exist
- **Actual result:** (a),(b) pass. (c) message is 'Saved ... The issue may already exist; check github.com/unclehq/uncle/issues before filing again.' with no copyable command; one create, no retry. Literal text of expected result unmet for (c); the omission may be deliberate (avoids duplicates).
- **Defects:** D-2

### MC-201

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. Same classification sweep as MC-101.
- **Expected result:** Refusals, and banner offers /report only for tool bug
- **Actual result:** Refusals pass. The banner never offers /report, even for tool bug (grep of uncle_tui.py finds /report only in the error string at line 4903).
- **Defects:** D-3

### MC-204

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. yes with gh absent and with auth failing.
- **Expected result:** No create, draft saved, copyable command, triage-issue identical
- **Actual result:** All met in both cases.
- **Defects:** None

### MC-205

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. /report then `YES`; then /report then `y`.
- **Expected result:** One create and URL; draft kept; y cancels with no gh
- **Actual result:** All met.
- **Defects:** None

### MC-206

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. Armed then /clear; armed then /report; armed then empty input.
- **Expected result:** No publish; /clear clears; /report re-arms with fresh draft; empty cancels; no chat
- **Actual result:** All met (/clear stubbed _clear_build, saw normal clear; second draft created). Real Enter-key path covered by tests in bug-report-test.py.
- **Defects:** None

### MC-301

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. gh absent and gh auth failing, answer yes. Declared dependency MC-300 is not in the checklist, so the driver grouping was NOT DECLARED; run serially.
- **Expected result:** No issue, draft saved, shell-quoted command, no crash
- **Actual result:** Same as MC-204: met in both cases.
- **Defects:** None

### MC-302

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. Ineligible and no classification.
- **Expected result:** No banner hint, fixed refusal, nothing armed, no draft
- **Actual result:** Refusal, nothing armed, no draft. No hint present.
- **Defects:** None

### MC-401

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. Only the /report refusal for non-tool-bug classification ran.
- **Expected result:** Recovery chat opens, /do N and /resume work as before, /report refused
- **Actual result:** /report refusal with no draft observed. Real recovery chat auto-open, /do N and /resume were not executed.
- **Defects:** None

### MC-402

- **Action:** Not executed: needs a live TUI with real human stop, decline and clean exit. Setup action: run the TUI in a sandbox project.
- **Expected result:** Triage does not auto-open on those stops
- **Actual result:** Not run.
- **Defects:** None

### MC-403

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. /report, `no`; /report, `why did this fail?`; ordinary message.
- **Expected result:** Two cancels, no create, only post-cancel message reaches chat
- **Actual result:** Two cancel lines, zero creates, exactly one chat call (the final message), two drafts.
- **Defects:** None

### MC-404

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. /report, cancel, /report with auth failing, yes; hash triage-issue-1.md before and after.
- **Expected result:** Hash identical; separate bug-report-N drafts
- **Actual result:** Hash identical; bug-report-1.md and bug-report-2.md.
- **Defects:** None

### MC-405

- **Action:** Headless drive of real UncleTUI._triage_command with fake gh on PATH, patched _triage_turn and _project_root, scratch project. Armed, /clear, then `yes`.
- **Expected result:** Cancel and normal clear; later yes ordinary, publishes nothing
- **Actual result:** Pending cancelled, clear ran, no gh call, `yes` reached chat as ordinary input.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | NO | PASS | mc.py run, exit 0 |
| MC-104 | NO | PASS | mc.py run, exit 0 |
| MC-105 | NO | PASS | mc.py run, exit 0 |
| MC-106 | NO | FAIL | Case (c) message lacks copyable command. D-2 |
| MC-201 | NO | FAIL | No banner offer for tool bug. D-3 |
| MC-204 | NO | PASS | mc.py run, exit 0 |
| MC-205 | NO | PASS | mc.py run, exit 0 |
| MC-206 | NO | PASS | mc.py run, exit 0 |
| MC-301 | YES | PASS | mc.py run, exit 0 |
| MC-302 | YES | PASS | mc.py run, exit 0 |
| MC-401 | YES | NOT | Only /report refusal ran; /do N and /resume not run |
| MC-402 | YES | BLOCKED-HUMAN | Needs a live TUI session and a person. Waiting on Brian to run it |
| MC-403 | YES | PASS | mc.py run, exit 0 |
| MC-404 | YES | PASS | mc.py run, exit 0 |
| MC-405 | YES | PASS | mc.py run, exit 0 |
