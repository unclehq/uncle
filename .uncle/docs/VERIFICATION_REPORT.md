# Verification report

## Findings

### MC-901

- **Action:** Static source trace (no execution) of change_implementation_incomplete_choice (scripts/lib/implementation-gates.sh:23-108, wrapped by implementation-gates-change.sh:4), both callers in scripts/change-workflow.sh (4592-4599 and 4635-4642), the producer implementation_complete (change-workflow.sh:3911-4017) and scripts/lib/implementation-completion.py, for three unattended cases.
- **Expected result:** Under AC-4/SI-4 only review-delivery gaps with all acceptance rows delivered yield 'review incomplete' and driver exit 3; missing acceptance rows keep their existing behavior and are never classified review incomplete.
- **Actual result:** Classification logic is correct for the inputs it can see, but the review branch cannot be reached from the real producer. Case 3 (missing AC row + review): a review line is a non-AC line so ids stays empty, and the review branch also requires no AC row line (implementation-gates.sh:76-78), so it is skipped. The next branch (85-92) returns 1, so the caller takes '*)' and exits 1 (not 3). It is not classified review incomplete, as required. Without a review line, a missing AC row gives ids='AC-n', waive, return 2, and the caller continues (existing behavior). Cases 1 and 2 (all AC rows delivered, review missing or rejected): implementation-completion.py is the only writer of implementation-completion.txt (change-workflow.sh:3929). It emits only 'AC-n: requires IMPLEMENTED,...', 'Acceptance IDs must match ...' and format errors, and none of its output contains 'review' (grep of the file finds no review problem line). With all rows delivered it exits 0, so implementation_complete returns 0 (3930), the choice function is not called, and no exit 3 occurs. The branch at implementation-gates.sh:76-84 (grep -qiE '^[[:space:]]*review', return 4, caller 'exit 3' at 4597/4640) only fires if the completion file contains a line starting with 'review', which nothing in the driver produces. So the 'missing review' and 'rejected review' cases never reach exit 3 through the real flow. The scripts/tests/review-incomplete-exit-test.sh checks only grep strings and would not catch this.
- **Defects:** Proposed: the review-incomplete branch (implementation-gates.sh:76-84) matches '^review' text that no driver component writes, so review-delivery gaps cannot reach exit status 3 (AC-4/SI-4). Not yet recorded in DEFECTS.md; this worker does not edit it.

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-901 | YES | FAIL | implementation-gates.sh:76-84 (condition and return 4); change-workflow.sh:4592-4597 and 4635-4640 (case 4 -> echo 'Exit status 3: review incomplete (unattended).'; exit 3); change-workflow.sh:3928-3931 (sole writer of completion file, returns 0 when producer succeeds); Grep of implementation-completion.py for 'review' finds only a docstring at line 5, and line 216 is the 'Acceptance IDs' message. No live run performed; this is a source trace. |
