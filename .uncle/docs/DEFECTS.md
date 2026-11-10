# Defects

## MC-101

- **Status:** NOT RUN
- **Evidence:** See Findings MC-101.
- **Expected result:** See MANUAL_CHECKLIST.md MC-101.
- **Actual result:** Unsigned: verify exits 1 and reaches integrity checks (not 'no attestation'); its single refusal is 'required gate publication has no human approval', not an 'unauthenticated-attestation' finding. Signed: .sig listed as add, but verify was not run on the signed tree, so 'signed run exits 0' was not observed; by design (D-3) the delegated publication entry makes verify fail without a human approval. Checklist wording conflicts with the plan; not resolved here.

## MC-102

- **Status:** NOT RUN
- **Evidence:** See Findings MC-102.
- **Expected result:** See MANUAL_CHECKLIST.md MC-102.
- **Actual result:** Empty-envelopes case observed via driver tests (blocked, handoff-failed, no handoff.json). NOT READY half not executed.

## MC-202

- **Status:** NOT RUN
- **Evidence:** See Findings MC-202.
- **Expected result:** See MANUAL_CHECKLIST.md MC-202.
- **Actual result:** Empty-envelopes half observed; NOT READY and stale release_skipped cases not executed.

## MC-204

- **Status:** NOT RUN
- **Evidence:** See Findings MC-204.
- **Expected result:** See MANUAL_CHECKLIST.md MC-204.
- **Actual result:** Both refusals observed. Checklist expects exit 3 for the publish-after-handoff refusal; the test asserts exit 1. Unchanged journal and absence of remote calls not asserted by those tests.

## MC-206

- **Status:** NOT RUN
- **Evidence:** See Findings MC-206.
- **Expected result:** See MANUAL_CHECKLIST.md MC-206.
- **Actual result:** Tracked allowed_signers not deleted; stale tracked .sig is a delete row with no content; tampered tree fails verify. The 'new untracked allowed_signers listed add' and 'digest mismatch' wording are not asserted exactly (tampered test only checks a tree-related failure).

## MC-207

- **Status:** NOT RUN
- **Evidence:** See Findings MC-207.
- **Expected result:** See MANUAL_CHECKLIST.md MC-207.
- **Actual result:** Not executed.

## MC-303

- **Status:** NOT RUN
- **Evidence:** See Findings MC-303.
- **Expected result:** See MANUAL_CHECKLIST.md MC-303.
- **Actual result:** Empty envelopes half observed; NOT READY half not executed.

## MC-304

- **Status:** NOT RUN
- **Evidence:** See Findings MC-304.
- **Expected result:** See MANUAL_CHECKLIST.md MC-304.
- **Actual result:** Unaltered tree passes 'no attestation' to integrity checks (exit 1 for the missing human approval, not 0); tampered tree fails verify. Checklist's exit 0 only applies if signed and approved; not observed.

## MC-402

- **Status:** NOT RUN
- **Evidence:** See Findings MC-402.
- **Expected result:** See MANUAL_CHECKLIST.md MC-402.
- **Actual result:** Exporter exits 1 with no handoff.json. The 'Hand-off failed' wrapper text in change-pr.sh was not observed.

## AC-10

- **Status:** FAIL
- **Evidence:** run-python-tests.sh exit 1; supervisor-test.py signing audit flags handoff-export-test.py:243. Defect D-1.
- **Expected result:** Not recorded.
- **Actual result:** Not recorded.
