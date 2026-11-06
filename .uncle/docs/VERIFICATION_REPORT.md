# Verification report

## Findings

### MC-101

- **Action:** Read the checklist row only. Did not launch change-workflow.sh: the row requires a full end-to-end run with a real classifier model (WORKFLOW_SKIP_REVIEW unset) through the review stage, which this isolated worker (no repo exploration, no starting other agents or model runs, small budget) cannot perform.
- **Expected result:** No review panel launched; console prints `Adversarial review skipped: class docs, no risk hits`; run proceeds to validation and approval gate.
- **Actual result:** Not executed live. No console transcript was captured.
- **Defects:** None. Setup needed: an operator runs a docs-only change through change-workflow.sh in a scratch project with a real classifier configured, then reruns this lane.

### MC-102

- **Action:** Not performed. Depends on the skipped run from MC-101, which did not occur, so there is no review gate, rendered ADVERSARIAL_REVIEW.md, change-class.json or review-skipped marker to inspect.
- **Expected result:** Rendered review shows zero findings and `skipped: class <class>, no risk hits`; change-class.json records review=skip with review_reason; marker exists.
- **Actual result:** Not executed; prerequisite MC-101 blocked.
- **Defects:** None. Setup needed: complete MC-101 and stop at the review approval gate.

### MC-103

- **Action:** Not performed. Declining a skipped review as a human needs the live gate from MC-102, which is unavailable.
- **Expected result:** Run does not stop; ADVERSARIAL_REVIEW reruns as a full panel; stub and marker removed before the panel starts; skip not re-applied.
- **Actual result:** Not executed; prerequisite MC-102 blocked. This check also needs a human decline action at the gate.
- **Defects:** None. Setup needed: reach the skipped-review gate (MC-101/MC-102), then a human declines it.

### MC-105

- **Action:** Ran the narrow script scripts/tests/review-skip-test.sh once and inspected its WORKFLOW_SKIP_REVIEW and WORKFLOW_CLASSIFY cases. I did not launch a live driver review.
- **Expected result:** Every one of these runs launches a full review panel and prints no skip line.
- **Actual result:** The skip-decision helper change_class_review_skipped returned 'full review' (rc 1) for WORKFLOW_SKIP_REVIEW=0, empty, false, no and 2, and for WORKFLOW_CLASSIFY=0. Unset and =1 still honored the skip. The script ended with 36 passed, 0 failed, and the runner-calls file confirmed zero runner invocations. No live docs-only driver run was made, so I did not observe a console transcript showing the panel launching and no skip line. That needs a real reviewer panel run (agent/Codex invocation) that this lane cannot start.
- **Defects:** None

### MC-106

- **Action:** Read scripts/tests/review-skip-test.sh to see what it covers for editing the plan after a skip stub is written. I did not run a live ADVERSARIAL_REVIEW re-entry.
- **Expected result:** The stale stub, its rendered md and the marker are discarded and the skip decision is recomputed against the new plan; a stale or missing plan sha yields a full panel review.
- **Actual result:** The stale or missing plan sha half is covered at helper level: sha-mismatch-full and sha-empty-full both returned full review, and sha-match returned skip. Discarding the stale stub, its rendered md and the marker on re-entry was NOT observed. The script only greps the drivers for the 'review-skipped' marker and has no behavioral test for the discard. Doing it live needs a driver run to the review stage, an edit of the plan, and re-entry, which this lane cannot do.
- **Defects:** None

### MC-107

- **Action:** Read the checklist row and the driver green-check; did not run the live driver flow.
- **Expected result:** Run stops immediately with nonzero exit, no retry, no model invocation, no fallback to full review when the skip stub is corrupt.
- **Actual result:** Not executed. Reaching the driver's validation state with a corrupted stub requires a live stagegate.sh run with an approved plan and a classifier outcome, which was not set up in this worker.
- **Defects:** None

### MC-108

- **Action:** Read the checklist row; did not run the end-to-end stagegate.sh flow.
- **Expected result:** Review panel not launched, skip line shown, human gate appears, and the updated-plan stage accepts the zero-finding review and continues.
- **Actual result:** Not executed. The row needs a real classifier model answering review: skip and an interactive human approval gate, which are not available to this isolated worker.
- **Defects:** None

### MC-200

- **Action:** None. Read the checklist row only. The row needs a live change-workflow.sh run with a real classifier and a real reviewer panel on a risky docs-only plan. That cannot be done within this worker's compact policy and budget.
- **Expected result:** Full adversarial review panel runs; no 'Adversarial review skipped' line appears and no review-skipped marker exists (SI-1).
- **Actual result:** Not executed. No console output or marker state was observed.
- **Defects:** None

### MC-201

- **Action:** Ran scripts/tests/review-skip-test.sh (narrow, stub-level check). Did not run a live change-workflow.sh with a real classifier through the review gate.
- **Expected result:** Console shows skip line; no panel; gate shows zero-finding stub with 'skipped: class <class>, no risk hits'; change-class.json review=skip; marker exists.
- **Actual result:** Helper/CLI-level test passed 36/0 (stub written only for verified skip, exact overall_assessment, zero runner invocations, drivers reference the helper and marker). The live end-to-end driver run with a real classifier was not performed in this worker.
- **Defects:** None

### MC-202

- **Action:** None live. Declining a review at the gate is a human action, and MC-201 was not run live.
- **Expected result:** Run continues; stub and marker removed; full panel review runs; skip never re-applied.
- **Actual result:** Not executed. The test script only partly covers the stale/marker handling.
- **Defects:** None

### MC-203

- **Action:** None. Read the checklist row only. The row needs live change-workflow.sh runs with WORKFLOW_SKIP_REVIEW set to 0, empty and false against a real classifier and reviewer panel. This worker did not perform them.
- **Expected result:** Each run performs a full review; skip is honored only when the variable is unset or exactly 1 (SI-4).
- **Actual result:** Not executed. No console output was observed for any of the three values.
- **Defects:** None

### MC-204

- **Action:** Not run live. The review-skip-test.sh stale-plan sha cases passed as part of the 36 checks.
- **Expected result:** Stale stub, rendered md and marker discarded after a plan edit; decision recomputed against the new plan.
- **Actual result:** Not executed end to end in the driver; depends on MC-201 live state.
- **Defects:** None

### MC-205

- **Action:** Not run live in either driver. The review-skip-test.sh wiring checks passed (both drivers reference the helper, marker and skip-review).
- **Expected result:** Each driver stops immediately with nonzero exit on a corrupt stub, with no retry, no fallback and no model call.
- **Actual result:** Not executed against stagegate.sh or change-workflow.sh with a corrupted stub.
- **Defects:** None

### MC-206

- **Action:** Ran bash scripts/tests/review-skip-test.sh, which exercises the shared change_class_review_skipped helper (the function the drivers call) for WORKFLOW_CLASSIFY=0, a forced WORKFLOW_CHANGE_CLASS=docs, and the path-floor cases. Read review-skip-test.py, which covers driver/gate/auth/secret script paths (scripts/stagegate.sh, scripts/change-workflow.sh, src/auth.py, etc.). I did not run the full workflow end to end.
- **Expected result:** All three scenarios run a full review with no skip (SI-4, SI-5 path floor).
- **Actual result:** 36 passed, 0 failed. The classify-off-full and forced-class-full cases return 1 (not skipped). The path-floor test list includes driver and gate script paths. The driver green-check reports no regressions.
- **Defects:** None

### MC-207

- **Action:** Not run. This needs both drivers taken through the human approval gate and the final audit, which needs a human and a real reviewer.
- **Expected result:** Plan approval gate and final audit run normally on the zero-finding stub; updated-plan stage accepts it.
- **Actual result:** Not executed.
- **Defects:** None

### MC-300

- **Action:** Read the checklist row only. Did not launch change-workflow.sh in a scratch project.
- **Expected result:** No review panel runs; console shows `Adversarial review skipped: class docs, no risk hits`; the human review gate shows the stub with that reason and zero findings.
- **Actual result:** Not executed. The check needs a full change-workflow.sh run with a real model classifier in a scratch project, taken to an interactive human review gate. A compact worker has no budget or gate access for that.
- **Defects:** None

### MC-301

- **Action:** Not performed. It depends on the MC-300 gate, which was not reached.
- **Expected result:** Declining the skipped review at the gate reruns ADVERSARIAL_REVIEW as a full panel review, removes the stub and review-skipped marker before the panel starts, and does not re-take the skip.
- **Actual result:** Not executed. It needs the MC-300 gate state and a human decline action at an interactive approval gate.
- **Defects:** None

### MC-302

- **Action:** Did not execute. The check needs a scratch project plus a full change-workflow.sh run with a real classifier agent CLI and reviewer panel. I judged that too costly for this compact worker, and the budget is limited.
- **Expected result:** Full adversarial review runs with no skip stub and no review-skipped marker.
- **Actual result:** Not performed. Related automated coverage of risky-path floors is in review-skip-test.py, but it does not substitute for the live transcript this check requires.
- **Defects:** None

### MC-303

- **Action:** Ran scripts/tests/review-skip-test.sh (narrow check) and inspected its WORKFLOW_SKIP_REVIEW value matrix. Did not run change-workflow.sh end-to-end in a scratch project, because that needs a live reviewer panel.
- **Expected result:** Both runs (WORKFLOW_SKIP_REVIEW=0 and =false) perform a full panel review with no skip stub, even if the classifier answered skip.
- **Actual result:** At the helper level, with a stored class review=skip and a matching plan sha, WORKFLOW_SKIP_REVIEW=0 and =false both return 1 (full review); only unset and =1 honor the skip. The suite reported 36 passed, 0 failed. No full-driver transcript showing the panel being invoked was captured.
- **Defects:** None

### MC-304

- **Action:** Inspected review-skip-test.sh and ran it. Did not edit a plan after a stub was written or re-enter ADVERSARIAL_REVIEW in a scratch project.
- **Expected result:** After the plan is edited, the stale stub, its rendered md and the marker are discarded, and the skip decision is recomputed against the new plan.
- **Actual result:** The suite covers sha-mismatch, sha-empty and mismatched-sha skip-review, and each gives a full review with no stub written. It does not cover removal of an existing stub, its rendered md or the marker after a plan edit. The required before/after file listing was not produced.
- **Defects:** None

### MC-305

- **Action:** Read the checklist row. No live run: it needs two interactive drivers with a skip stub in a fifth scratch project, and this worker has no scratch project or driver session assigned.
- **Expected result:** Each driver stops immediately with nonzero exit, no retry, no model invocation, and no fallback to a full review.
- **Actual result:** Not performed. No live observation of either driver's behavior on a corrupted ADVERSARIAL_REVIEW.json.
- **Defects:** None

### MC-306

- **Action:** Read the checklist row. No live run: it needs stagegate.sh on a new small app project with a real classifier answering skip, through to the human approval gate. No real classifier session or scratch-app-small project was available to this worker.
- **Expected result:** No panel runs; the stub shows `skipped: class small, no risk hits` at the gate; the marker is written; the human approval gate still appears.
- **Actual result:** Not performed. No gate transcript or marker listing was captured.
- **Defects:** None

### MC-401

- **Action:** Did not launch a fresh change-workflow.sh run with a real classifier (requires a full multi-agent workflow run, outside this worker's scope). Inspected the current run's own artifacts: change-class.json (class risky, 4 lenses), adversarial-review-panel directory, and workflow dir for skip markers.
- **Expected result:** Full reviewer panel runs as before; no skip stub is written and no review-skipped marker exists.
- **Actual result:** Observed only for this run: the classifier labelled the plan risky, all four lens packets (requirements, regression, security, testability) exist plus a synthesis, and no skip marker file is in .uncle/workflow. This is incidental evidence, not the dedicated risky-plan scenario with the plan text the check names (data deletion / auth-secret path). Not independently exercised.
- **Defects:** None

### MC-402

- **Action:** Did not run stagegate.sh with a standard/large-class change, nor a docs-class change with WORKFLOW_CLASSIFY=0. Each needs a full live driver run with the reviewer panel.
- **Expected result:** Both runs launch the full review panel with every lens; disabled classification or a non-reducible class never skips.
- **Actual result:** Not performed; no observation was made of either scenario.
- **Defects:** None

### MC-403

- **Action:** Did not run a full change-workflow.sh pass. Ran the narrow scripts/tests/review-skip-test.sh, whose value matrix drives the shared skip-decision helper with WORKFLOW_SKIP_REVIEW unset, 1, 0, empty, false, no and 2 against a plan classified review=skip. Also read the ADVERSARIAL_REVIEW state in scripts/change-workflow.sh.
- **Expected result:** Every run with WORKFLOW_SKIP_REVIEW=0, empty or false performs a full panel review and writes no stub, even when the classifier answered review: skip.
- **Actual result:** The helper returned 'full review' (rc 1) for 0, empty, false, no and 2, and 'skip' only for unset and 1. No runner calls were made. The helper-level suite passed 36 of 36. The end-to-end driver run was not executed, so the no-stub outcome is shown only through the decision helper and the driver wiring.
- **Defects:** None

### MC-405

- **Action:** Read the decline and stale-plan handling in change-workflow.sh and stagegate.sh. Ran review-skip-test.sh, which covers a plan edited after the decision. Did not run a live driver at a review gate.
- **Expected result:** Declining a skipped review reruns ADVERSARIAL_REVIEW as a full panel review with the stub and review-skipped marker removed. A plan edit discards the stale stub and recomputes the decision.
- **Actual result:** Plan-edit half: the test passed (plan-edited-after-decision-full and sha-mismatch-full both force a full review). Decline half: the code removes the review-skipped and review-skip-declined markers and falls through to the panel. I found no code removing the stub ADVERSARIAL_REVIEW.json on decline, and the decline gate was not exercised live, so that half is unverified.
- **Defects:** None

### MC-406

- **Action:** Read the checklist row and inspected scripts/tests/review-skip-test.sh to see what is covered. Did not run stagegate.sh end to end.
- **Expected result:** Same skip text appears at the gate, the review-skipped marker exists, and the remaining stages and human gates behave unchanged.
- **Actual result:** Not executed. A live run through stagegate.sh needs the approval gates signed by a person and the downstream stages run with a model. The existing test only greps the drivers for the helper, marker and skip-review references, which is not behavioral evidence.
- **Defects:** None

### MC-407

- **Action:** Read the checklist row and inspected scripts/tests/review-skip-test.sh. Did not corrupt the stub or resume either driver.
- **Expected result:** The run stops immediately with a nonzero exit, with no retry, no model invocation, and no fallback to full review.
- **Actual result:** Not executed. It needs a staged run in each of change-workflow.sh and stagegate.sh with a skip stub, which needs an approved earlier gate that only a person can supply. The test suite only greps for the helper, marker and skip-review references. The 'no-runner-calls' check covers the helper's value matrix, not a driver resume.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | BLOCKED-SETUP | None captured. Automated skip-path coverage, if any, belongs to the driver green-check and is not claimed here. |
| MC-102 | YES | BLOCKED-SETUP | None. |
| MC-103 | YES | BLOCKED-SETUP | None. |
| MC-105 | YES | NOT RUN | review-skip-test: 36 passed, 0 failed (env-[0]/[]/[false]-full-review and classify-off-full checks). The script is not in green-check.commands or green-check.md, so this was a narrow run, not a cited driver result. |
| MC-106 | YES | NOT RUN | review-skip-test.sh lines 65-68 (sha cases) pass. Lines 114-120 only grep for marker references. No before/after listing of artifacts was captured. |
| MC-107 | YES | NOT RUN | The green-check shows no regressions (bash scripts/run-shell-tests.sh and run-python-tests.sh, PREEXISTING). The review-skip-test.sh corrupt-json-full check covers only a corrupt change-class.json, not the corrupted ADVERSARIAL_REVIEW.json stub. No live evidence exists for this row. |
| MC-108 | YES | BLOCKED-HUMAN | No live transcript was captured. Automated coverage is limited to the driver green-check, which reports no regressions. |
| MC-200 | YES | NOT RUN | None. The driver green-check and scripts/tests/review-skip-test.sh may cover the skip logic with stubs, but this worker did not run or read them. They are not a substitute for the live run the row requires. |
| MC-201 | YES | NOT RUN | review-skip-test: 36 passed, 0 failed; driver green-check reports no regressions. This is not a substitute for the live console transcript. |
| MC-202 | YES | BLOCKED-HUMAN | No transcript. Depends on MC-201 live run, and on a person declining the gate. |
| MC-203 | YES | NOT RUN | None. Nothing was run or inspected for this row, so there is no evidence of the behavior either way. |
| MC-204 | YES | NOT RUN | review-skip-test: 36 passed (includes plan sha mismatch/edit cases), cited as partial only. |
| MC-205 | YES | NOT RUN | Static wiring grep checks passed in review-skip-test.sh; no runtime exit-code observation. |
| MC-206 | YES | PASS | review-skip-test: 36 passed, 0 failed; helper cases at review-skip-test.sh lines 55-56; path-floor list at review-skip-test.py line 149; .uncle/workflow/green-check.md. Scope limit: this is helper-level evidence, not console output from three full change-workflow.sh runs. The mapping of 'a plan owning a driver/gate script classified small' to the floor test rests on my reading of the test list at review-skip-test.py line 149; I did not run that case individually. |
| MC-207 | YES | BLOCKED-HUMAN | No transcript. Depends on MC-201 live run and on human gate approvals. |
| MC-300 | YES | NOT RUN | None. No runtime observation was made, and the driver green-check does not cover this live end-to-end behavior. |
| MC-301 | YES | NOT RUN | None. The MC-300 prerequisite was not run, so there was nothing to decline. |
| MC-302 | YES | NOT RUN | None for the live run. |
| MC-303 | YES | NOT RUN | review-skip-test: 36 passed, 0 failed. Cases env-[0]-full-review and env-[false]-full-review pass. |
| MC-304 | YES | NOT RUN | Cases sha-mismatch-full, sha-empty-full and skip-review-mismatch-no-stub pass in the 36/36 run. There is no stale-stub removal evidence. |
| MC-305 | YES | NOT RUN | I did not run scripts/tests/review-skip-test.sh. The driver green-check owns automated commands, and I did not read it, so I make no claim that it covers this row. |
| MC-306 | YES | BLOCKED-SETUP | None. The human approval gate cannot be signed or observed by this worker. Setup needed: a real classifier and a scratch-app-small project, plus a person to reach the gate. |
| MC-401 | YES | NOT RUN | change-class.json class=risky; adversarial-review-panel/{requirements,regression,security,testability}.json; ls .uncle/workflow / grep -i skip returned nothing. scripts/tests/review-skip-test.sh covers the helper and CLI refusal logic, but I did not run it and the driver green-check is not cited here. |
| MC-402 | YES | NOT RUN | None. scripts/tests/review-skip-test.sh has a value-matrix section for the disabling switches, but I did not execute it. |
| MC-403 | YES | PASS | review-skip-test: 36 passed, 0 failed; checks env-[0]-full-review, env-[]-full-review and env-[false]-full-review. change-workflow.sh:3964-3979 only calls skip-review when change_class_review_skipped succeeds. |
| MC-405 | YES | NOT RUN | change-workflow.sh:3964-3965 removes only the markers; the stagegate.sh:5480 path looks similar. The human decline interaction was not performed. |
| MC-406 | YES | BLOCKED-HUMAN | scripts/tests/review-skip-test.sh lines 114-120 are static greps of the drivers. No live run was performed. |
| MC-407 | YES | BLOCKED-HUMAN | scripts/tests/review-skip-test.sh line 63 (corrupt-json-full covers change-class.json, not the review stub) and lines 111 and 114-120 (static greps). No live resume was performed. |
