# Verification report

## Findings

### MC-101

- **Action:** Read handoff-export-test.py; used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-101.
- **Actual result:** Unsigned: verify exits 1 and reaches integrity checks (not 'no attestation'); its single refusal is 'required gate publication has no human approval', not an 'unauthenticated-attestation' finding. Signed: .sig listed as add, but verify was not run on the signed tree, so 'signed run exits 0' was not observed; by design (D-3) the delegated publication entry makes verify fail without a human approval. Checklist wording conflicts with the plan; not resolved here.
- **Defects:** None

### MC-102

- **Action:** Driver test run only.
- **Expected result:** See MANUAL_CHECKLIST.md MC-102.
- **Actual result:** Empty-envelopes case observed via driver tests (blocked, handoff-failed, no handoff.json). NOT READY half not executed.
- **Defects:** None

### MC-103

- **Action:** Read tests; used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-103.
- **Actual result:** Rerun keeps audited_tree and tree; normal publish refuses 'handed off to the host'; prepared journal refused (exit 1) in the engine test.
- **Defects:** None

### MC-104

- **Action:** Used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-104.
- **Actual result:** Refused with 'Attestation blocked: <path> is a symlink' (exit 3), target unchanged, no handoff.json.
- **Defects:** None

### MC-202

- **Action:** Driver test run only.
- **Expected result:** See MANUAL_CHECKLIST.md MC-202.
- **Actual result:** Empty-envelopes half observed; NOT READY and stale release_skipped cases not executed.
- **Defects:** None

### MC-203

- **Action:** Used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-203.
- **Actual result:** Refused, outside file unchanged, no handoff.json. Hash comparison not taken; content equality asserted by the test.
- **Defects:** None

### MC-204

- **Action:** Used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-204.
- **Actual result:** Both refusals observed. Checklist expects exit 3 for the publish-after-handoff refusal; the test asserts exit 1. Unchanged journal and absence of remote calls not asserted by those tests.
- **Defects:** None

### MC-206

- **Action:** Used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-206.
- **Actual result:** Tracked allowed_signers not deleted; stale tracked .sig is a delete row with no content; tampered tree fails verify. The 'new untracked allowed_signers listed add' and 'digest mismatch' wording are not asserted exactly (tampered test only checks a tree-related failure).
- **Defects:** None

### MC-207

- **Action:** None.
- **Expected result:** See MANUAL_CHECKLIST.md MC-207.
- **Actual result:** Not executed.
- **Defects:** None

### MC-302

- **Action:** Used driver result; MC-301 is not in the checklist (grouping NOT DECLARED).
- **Expected result:** See MANUAL_CHECKLIST.md MC-302.
- **Actual result:** Symlink at .json and .sig refused, outside file unchanged, no handoff.json.
- **Defects:** None

### MC-303

- **Action:** Used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-303.
- **Actual result:** Empty envelopes half observed; NOT READY half not executed.
- **Defects:** None

### MC-304

- **Action:** Used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-304.
- **Actual result:** Unaltered tree passes 'no attestation' to integrity checks (exit 1 for the missing human approval, not 0); tampered tree fails verify. Checklist's exit 0 only applies if signed and approved; not observed.
- **Defects:** None

### MC-305

- **Action:** Used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-305.
- **Actual result:** Publish refused after handoff; prepared journal refused; journal unchanged asserted only for the empty-envelope case.
- **Defects:** None

### MC-402

- **Action:** Used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-402.
- **Actual result:** Exporter exits 1 with no handoff.json. The 'Hand-off failed' wrapper text in change-pr.sh was not observed.
- **Defects:** None

### MC-405

- **Action:** Used driver result.
- **Expected result:** See MANUAL_CHECKLIST.md MC-405.
- **Actual result:** Publish refuses with 'handed off to the host'; prepared journal refused with exit 1. Attestation hashes before and after not recorded.
- **Defects:** None

### AC-10

- **Action:** Not recorded.
- **Expected result:** Not recorded.
- **Actual result:** Not recorded.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | NOT RUN | See Findings MC-101. |
| MC-102 | YES | NOT RUN | See Findings MC-102. |
| MC-103 | YES | PASS | See Findings MC-103. |
| MC-104 | YES | PASS | See Findings MC-104. |
| MC-202 | YES | NOT RUN | See Findings MC-202. |
| MC-203 | YES | PASS | See Findings MC-203. |
| MC-204 | YES | NOT RUN | See Findings MC-204. |
| MC-206 | YES | NOT RUN | See Findings MC-206. |
| MC-207 | YES | NOT RUN | See Findings MC-207. |
| MC-302 | YES | PASS | See Findings MC-302. |
| MC-303 | YES | NOT RUN | See Findings MC-303. |
| MC-304 | YES | NOT RUN | See Findings MC-304. |
| MC-305 | YES | PASS | See Findings MC-305. |
| MC-402 | YES | NOT RUN | See Findings MC-402. |
| MC-405 | YES | PASS | See Findings MC-405. |
| AC-10 | YES | FAIL | run-python-tests.sh exit 1; supervisor-test.py signing audit flags handoff-export-test.py:243. Defect D-1. |
