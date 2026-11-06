# Defects

## None. Setup needed: an operator runs a docs-only change through change-workflow.sh in a scratch project with a real classifier configured, then reruns this lane.

- **Status:** BLOCKED-SETUP
- **Evidence:** None captured. Automated skip-path coverage, if any, belongs to the driver green-check and is not claimed here.
- **Expected result:** No review panel launched; console prints `Adversarial review skipped: class docs, no risk hits`; run proceeds to validation and approval gate.
- **Actual result:** Not executed live. No console transcript was captured.

## None. Setup needed: complete MC-101 and stop at the review approval gate.

- **Status:** BLOCKED-SETUP
- **Evidence:** None.
- **Expected result:** Rendered review shows zero findings and `skipped: class <class>, no risk hits`; change-class.json records review=skip with review_reason; marker exists.
- **Actual result:** Not executed; prerequisite MC-101 blocked.

## None. Setup needed: reach the skipped-review gate (MC-101/MC-102), then a human declines it.

- **Status:** BLOCKED-SETUP
- **Evidence:** None.
- **Expected result:** Run does not stop; ADVERSARIAL_REVIEW reruns as a full panel; stub and marker removed before the panel starts; skip not re-applied.
- **Actual result:** Not executed; prerequisite MC-102 blocked. This check also needs a human decline action at the gate.

## None

- **Status:** NOT RUN
- **Evidence:** review-skip-test: 36 passed, 0 failed (env-[0]/[]/[false]-full-review and classify-off-full checks). The script is not in green-check.commands or green-check.md, so this was a narrow run, not a cited driver result.
- **Expected result:** Every one of these runs launches a full review panel and prints no skip line.
- **Actual result:** The skip-decision helper change_class_review_skipped returned 'full review' (rc 1) for WORKFLOW_SKIP_REVIEW=0, empty, false, no and 2, and for WORKFLOW_CLASSIFY=0. Unset and =1 still honored the skip. The script ended with 36 passed, 0 failed, and the runner-calls file confirmed zero runner invocations. No live docs-only driver run was made, so I did not observe a console transcript showing the panel launching and no skip line. That needs a real reviewer panel run (agent/Codex invocation) that this lane cannot start.

## None

- **Status:** NOT RUN
- **Evidence:** review-skip-test.sh lines 65-68 (sha cases) pass. Lines 114-120 only grep for marker references. No before/after listing of artifacts was captured.
- **Expected result:** The stale stub, its rendered md and the marker are discarded and the skip decision is recomputed against the new plan; a stale or missing plan sha yields a full panel review.
- **Actual result:** The stale or missing plan sha half is covered at helper level: sha-mismatch-full and sha-empty-full both returned full review, and sha-match returned skip. Discarding the stale stub, its rendered md and the marker on re-entry was NOT observed. The script only greps the drivers for the 'review-skipped' marker and has no behavioral test for the discard. Doing it live needs a driver run to the review stage, an edit of the plan, and re-entry, which this lane cannot do.

## None

- **Status:** NOT RUN
- **Evidence:** The green-check shows no regressions (bash scripts/run-shell-tests.sh and run-python-tests.sh, PREEXISTING). The review-skip-test.sh corrupt-json-full check covers only a corrupt change-class.json, not the corrupted ADVERSARIAL_REVIEW.json stub. No live evidence exists for this row.
- **Expected result:** Run stops immediately with nonzero exit, no retry, no model invocation, no fallback to full review when the skip stub is corrupt.
- **Actual result:** Not executed. Reaching the driver's validation state with a corrupted stub requires a live stagegate.sh run with an approved plan and a classifier outcome, which was not set up in this worker.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No live transcript was captured. Automated coverage is limited to the driver green-check, which reports no regressions.
- **Expected result:** Review panel not launched, skip line shown, human gate appears, and the updated-plan stage accepts the zero-finding review and continues.
- **Actual result:** Not executed. The row needs a real classifier model answering review: skip and an interactive human approval gate, which are not available to this isolated worker.

## None

- **Status:** NOT RUN
- **Evidence:** None. The driver green-check and scripts/tests/review-skip-test.sh may cover the skip logic with stubs, but this worker did not run or read them. They are not a substitute for the live run the row requires.
- **Expected result:** Full adversarial review panel runs; no 'Adversarial review skipped' line appears and no review-skipped marker exists (SI-1).
- **Actual result:** Not executed. No console output or marker state was observed.

## None

- **Status:** NOT RUN
- **Evidence:** review-skip-test: 36 passed, 0 failed; driver green-check reports no regressions. This is not a substitute for the live console transcript.
- **Expected result:** Console shows skip line; no panel; gate shows zero-finding stub with 'skipped: class <class>, no risk hits'; change-class.json review=skip; marker exists.
- **Actual result:** Helper/CLI-level test passed 36/0 (stub written only for verified skip, exact overall_assessment, zero runner invocations, drivers reference the helper and marker). The live end-to-end driver run with a real classifier was not performed in this worker.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No transcript. Depends on MC-201 live run, and on a person declining the gate.
- **Expected result:** Run continues; stub and marker removed; full panel review runs; skip never re-applied.
- **Actual result:** Not executed. The test script only partly covers the stale/marker handling.

## None

- **Status:** NOT RUN
- **Evidence:** None. Nothing was run or inspected for this row, so there is no evidence of the behavior either way.
- **Expected result:** Each run performs a full review; skip is honored only when the variable is unset or exactly 1 (SI-4).
- **Actual result:** Not executed. No console output was observed for any of the three values.

## None

- **Status:** NOT RUN
- **Evidence:** review-skip-test: 36 passed (includes plan sha mismatch/edit cases), cited as partial only.
- **Expected result:** Stale stub, rendered md and marker discarded after a plan edit; decision recomputed against the new plan.
- **Actual result:** Not executed end to end in the driver; depends on MC-201 live state.

## None

- **Status:** NOT RUN
- **Evidence:** Static wiring grep checks passed in review-skip-test.sh; no runtime exit-code observation.
- **Expected result:** Each driver stops immediately with nonzero exit on a corrupt stub, with no retry, no fallback and no model call.
- **Actual result:** Not executed against stagegate.sh or change-workflow.sh with a corrupted stub.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** No transcript. Depends on MC-201 live run and on human gate approvals.
- **Expected result:** Plan approval gate and final audit run normally on the zero-finding stub; updated-plan stage accepts it.
- **Actual result:** Not executed.

## None

- **Status:** NOT RUN
- **Evidence:** None. No runtime observation was made, and the driver green-check does not cover this live end-to-end behavior.
- **Expected result:** No review panel runs; console shows `Adversarial review skipped: class docs, no risk hits`; the human review gate shows the stub with that reason and zero findings.
- **Actual result:** Not executed. The check needs a full change-workflow.sh run with a real model classifier in a scratch project, taken to an interactive human review gate. A compact worker has no budget or gate access for that.

## None

- **Status:** NOT RUN
- **Evidence:** None. The MC-300 prerequisite was not run, so there was nothing to decline.
- **Expected result:** Declining the skipped review at the gate reruns ADVERSARIAL_REVIEW as a full panel review, removes the stub and review-skipped marker before the panel starts, and does not re-take the skip.
- **Actual result:** Not executed. It needs the MC-300 gate state and a human decline action at an interactive approval gate.

## None

- **Status:** NOT RUN
- **Evidence:** None for the live run.
- **Expected result:** Full adversarial review runs with no skip stub and no review-skipped marker.
- **Actual result:** Not performed. Related automated coverage of risky-path floors is in review-skip-test.py, but it does not substitute for the live transcript this check requires.

## None

- **Status:** NOT RUN
- **Evidence:** review-skip-test: 36 passed, 0 failed. Cases env-[0]-full-review and env-[false]-full-review pass.
- **Expected result:** Both runs (WORKFLOW_SKIP_REVIEW=0 and =false) perform a full panel review with no skip stub, even if the classifier answered skip.
- **Actual result:** At the helper level, with a stored class review=skip and a matching plan sha, WORKFLOW_SKIP_REVIEW=0 and =false both return 1 (full review); only unset and =1 honor the skip. The suite reported 36 passed, 0 failed. No full-driver transcript showing the panel being invoked was captured.

## None

- **Status:** NOT RUN
- **Evidence:** Cases sha-mismatch-full, sha-empty-full and skip-review-mismatch-no-stub pass in the 36/36 run. There is no stale-stub removal evidence.
- **Expected result:** After the plan is edited, the stale stub, its rendered md and the marker are discarded, and the skip decision is recomputed against the new plan.
- **Actual result:** The suite covers sha-mismatch, sha-empty and mismatched-sha skip-review, and each gives a full review with no stub written. It does not cover removal of an existing stub, its rendered md or the marker after a plan edit. The required before/after file listing was not produced.

## None

- **Status:** NOT RUN
- **Evidence:** I did not run scripts/tests/review-skip-test.sh. The driver green-check owns automated commands, and I did not read it, so I make no claim that it covers this row.
- **Expected result:** Each driver stops immediately with nonzero exit, no retry, no model invocation, and no fallback to a full review.
- **Actual result:** Not performed. No live observation of either driver's behavior on a corrupted ADVERSARIAL_REVIEW.json.

## None

- **Status:** BLOCKED-SETUP
- **Evidence:** None. The human approval gate cannot be signed or observed by this worker. Setup needed: a real classifier and a scratch-app-small project, plus a person to reach the gate.
- **Expected result:** No panel runs; the stub shows `skipped: class small, no risk hits` at the gate; the marker is written; the human approval gate still appears.
- **Actual result:** Not performed. No gate transcript or marker listing was captured.

## None

- **Status:** NOT RUN
- **Evidence:** change-class.json class=risky; adversarial-review-panel/{requirements,regression,security,testability}.json; ls .uncle/workflow | grep -i skip returned nothing. scripts/tests/review-skip-test.sh covers the helper and CLI refusal logic, but I did not run it and the driver green-check is not cited here.
- **Expected result:** Full reviewer panel runs as before; no skip stub is written and no review-skipped marker exists.
- **Actual result:** Observed only for this run: the classifier labelled the plan risky, all four lens packets (requirements, regression, security, testability) exist plus a synthesis, and no skip marker file is in .uncle/workflow. This is incidental evidence, not the dedicated risky-plan scenario with the plan text the check names (data deletion / auth-secret path). Not independently exercised.

## None

- **Status:** NOT RUN
- **Evidence:** None. scripts/tests/review-skip-test.sh has a value-matrix section for the disabling switches, but I did not execute it.
- **Expected result:** Both runs launch the full review panel with every lens; disabled classification or a non-reducible class never skips.
- **Actual result:** Not performed; no observation was made of either scenario.

## None

- **Status:** NOT RUN
- **Evidence:** change-workflow.sh:3964-3965 removes only the markers; the stagegate.sh:5480 path looks similar. The human decline interaction was not performed.
- **Expected result:** Declining a skipped review reruns ADVERSARIAL_REVIEW as a full panel review with the stub and review-skipped marker removed. A plan edit discards the stale stub and recomputes the decision.
- **Actual result:** Plan-edit half: the test passed (plan-edited-after-decision-full and sha-mismatch-full both force a full review). Decline half: the code removes the review-skipped and review-skip-declined markers and falls through to the panel. I found no code removing the stub ADVERSARIAL_REVIEW.json on decline, and the decline gate was not exercised live, so that half is unverified.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** scripts/tests/review-skip-test.sh lines 114-120 are static greps of the drivers. No live run was performed.
- **Expected result:** Same skip text appears at the gate, the review-skipped marker exists, and the remaining stages and human gates behave unchanged.
- **Actual result:** Not executed. A live run through stagegate.sh needs the approval gates signed by a person and the downstream stages run with a model. The existing test only greps the drivers for the helper, marker and skip-review references, which is not behavioral evidence.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** scripts/tests/review-skip-test.sh line 63 (corrupt-json-full covers change-class.json, not the review stub) and lines 111 and 114-120 (static greps). No live resume was performed.
- **Expected result:** The run stops immediately with a nonzero exit, with no retry, no model invocation, and no fallback to full review.
- **Actual result:** Not executed. It needs a staged run in each of change-workflow.sh and stagegate.sh with a skip stub, which needs an approved earlier gate that only a person can supply. The test suite only greps for the helper, marker and skip-review references. The 'no-runner-calls' check covers the helper's value matrix, not a driver resume.
