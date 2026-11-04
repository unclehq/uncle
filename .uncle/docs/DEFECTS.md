# Defects

## D-2

- **Status:** FAIL
- **Evidence:** Case (c) message lacks copyable command. D-2
- **Expected result:** Each case: draft kept, copyable gh issue create command; (c) says may already exist
- **Actual result:** (a),(b) pass. (c) message is 'Saved ... The issue may already exist; check github.com/unclehq/uncle/issues before filing again.' with no copyable command; one create, no retry. Literal text of expected result unmet for (c); the omission may be deliberate (avoids duplicates).

## D-3

- **Status:** FAIL
- **Evidence:** No banner offer for tool bug. D-3
- **Expected result:** Refusals, and banner offers /report only for tool bug
- **Actual result:** Refusals pass. The banner never offers /report, even for tool bug (grep of uncle_tui.py finds /report only in the error string at line 4903).

## MC-401

- **Status:** NOT
- **Evidence:** Only /report refusal ran; /do N and /resume not run
- **Expected result:** Recovery chat opens, /do N and /resume work as before, /report refused
- **Actual result:** /report refusal with no draft observed. Real recovery chat auto-open, /do N and /resume were not executed.

## MC-402

- **Status:** BLOCKED-HUMAN
- **Evidence:** Needs a live TUI session and a person. Waiting on Brian to run it
- **Expected result:** Triage does not auto-open on those stops
- **Actual result:** Not run.
