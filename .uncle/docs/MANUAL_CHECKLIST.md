# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a docs-only change through change-workflow.sh with a real classifier (unset WORKFLOW_SKIP_REVIEW) whose plan owns only documentation files and has no risky words, and watch the console through the adversarial review stage.
- Expected result: No review panel or primary reviewer is launched; the console prints `Adversarial review skipped: class docs, no risk hits` and the run proceeds to validation and the approval gate.
- Evidence to capture: Console transcript showing the skip line and absence of reviewer invocation.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-101
- Exact action: At the review approval gate of the skipped run from MC-101, open the rendered .uncle/docs/ADVERSARIAL_REVIEW.md and .uncle/workflow/change-class.json, and check that the marker .uncle/workflow/review-skipped exists.
- Expected result: The rendered review shows zero findings and the overall assessment `skipped: class <class>, no risk hits`; change-class.json records review=skip with a review_reason; the marker file exists.
- Evidence to capture: Contents of the rendered review, the review fields of change-class.json, and a listing showing the marker.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-102
- Exact action: At the gate for a skipped review, decline the review as a human.
- Expected result: The run does not stop; ADVERSARIAL_REVIEW reruns as a full panel review, the stub and review-skipped marker are removed before the panel starts, and skip is not re-applied.
- Evidence to capture: Console transcript of the rerun showing the panel launching, and a listing showing the marker and stub gone.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Repeat a docs-only run that would normally skip, once each with WORKFLOW_SKIP_REVIEW=0, WORKFLOW_SKIP_REVIEW= (empty), and WORKFLOW_SKIP_REVIEW=false, then once with WORKFLOW_CLASSIFY=0.
- Expected result: Every one of these runs launches a full review panel and prints no skip line.
- Evidence to capture: Console transcript for each variant showing the panel running.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: After a skip stub is written but before approval, edit the plan so its content changes, then re-enter ADVERSARIAL_REVIEW.
- Expected result: The stale stub, its rendered md and the marker are discarded and the skip decision is recomputed against the new plan; a stale or missing plan sha yields a full panel review.
- Evidence to capture: Console transcript and a listing of the review artifacts and marker before and after the edit.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Corrupt the skip stub ADVERSARIAL_REVIEW.json so it fails validation, then let the driver reach the validation state.
- Expected result: The run stops immediately with a nonzero exit, with no retry, no model invocation and no fallback to a full review.
- Evidence to capture: Console output and exit status of the stopped run, with no reviewer activity.
- Actual result: 
- Status: NOT RUN

### MC-108
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a new-app flow through stagegate.sh with a small, low-risk plan and a real classifier answering review: skip, and confirm the review approval gate and later stages (updated plan, final audit) behave normally.
- Expected result: The review panel is not launched, the skip line is shown, the human gate appears, and the updated-plan stage accepts the zero-finding review and continues.
- Evidence to capture: Console transcript from classification through the updated-plan stage.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run change-workflow.sh on a docs-only change whose plan mentions deleting files or touching auth/secret terms, with a real classifier that may answer review: skip. Observe the ADVERSARIAL_REVIEW stage.
- Expected result: Full adversarial review panel runs; no 'Adversarial review skipped' line appears and no review-skipped marker exists (SI-1).
- Evidence to capture: Console output of the review stage and absence of .uncle/workflow/review-skipped.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a genuinely docs-only change (owned files all documentation, no risk words) through change-workflow.sh with a real classifier and reach the review gate.
- Expected result: Console shows 'Adversarial review skipped: class <class>, no risk hits'; no panel or reviewer runs; the gate shows ADVERSARIAL_REVIEW.md with zero findings and the exact text 'skipped: class <class>, no risk hits'; change-class.json records review=skip and the marker exists (SI-2).
- Evidence to capture: Console transcript, rendered ADVERSARIAL_REVIEW.md, change-class.json review fields, marker presence.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-201
- Exact action: At the review gate of a skipped review, decline the review, then observe the rerun.
- Expected result: The run does not stop; the stub and review-skipped marker are removed and a full panel review runs, never re-skipping (D-5).
- Evidence to capture: Console transcript after decline and file listing showing marker and stub gone, real review present.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the same docs-only change with WORKFLOW_SKIP_REVIEW set to 0, then to empty, then to false, observing the review stage each time.
- Expected result: Each run performs a full review; skip is honored only when the variable is unset or exactly 1 (SI-4).
- Evidence to capture: Console output per value showing the panel ran and no skip line.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-201
- Exact action: After a skip stub is written, edit the plan so its content changes, then re-enter ADVERSARIAL_REVIEW.
- Expected result: The stale stub, rendered md and marker are discarded and the decision is recomputed against the new plan; a full review runs if skip no longer holds (SB-9).
- Evidence to capture: Console output and file state before and after the re-entry.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-201
- Exact action: Corrupt a skip stub's ADVERSARIAL_REVIEW.json so it fails validation, then resume the run in both stagegate.sh and change-workflow.sh.
- Expected result: Each driver stops immediately with a nonzero exit, no retry, no fallback to full review and no model invocation (SB-8).
- Evidence to capture: Exit code, console output, and absence of any runner or model call.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a docs-only change with WORKFLOW_CLASSIFY=0, and another with a forced WORKFLOW_CHANGE_CLASS, and also a plan owning a driver/gate script classified small.
- Expected result: All three run a full review with no skip (SI-4, SI-5 path floor).
- Evidence to capture: Console output of each run and absence of the skip marker.
- Actual result: 
- Status: NOT RUN

### MC-207
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-201
- Exact action: Take a skipped review through to the human approval gate and final audit in both drivers.
- Expected result: The plan approval gate and final audit run as normal on the zero-finding stub, and the updated-plan stage accepts it (SI-3).
- Evidence to capture: Console output showing gate prompt, updated-plan stage and final audit completing.
- Actual result: 
- Status: NOT RUN

## resources

### MC-300
- Required for acceptance: YES
- Exclusive resources: dir:scratch-project-skip
- Depends on: none
- Exact action: In a scratch project, run change-workflow.sh with a real classifier on a docs-only change plan (only .md files owned, no risky words) with WORKFLOW_SKIP_REVIEW unset, and watch the ADVERSARIAL_REVIEW stage.
- Expected result: No review panel or reviewer runs; console shows `Adversarial review skipped: class docs, no risk hits`; the human review gate displays the stub with that skip reason and zero findings.
- Evidence to capture: Terminal transcript of the stage plus the rendered ADVERSARIAL_REVIEW.md, change-class.json review fields and the .uncle/workflow/review-skipped marker.
- Actual result: 
- Status: NOT RUN

### MC-301
- Required for acceptance: YES
- Exclusive resources: dir:scratch-project-skip
- Depends on: MC-300
- Exact action: At the review gate reached in MC-300, decline the skipped review.
- Expected result: The run does not stop; ADVERSARIAL_REVIEW reruns as a full panel review, the stub and review-skipped marker are removed before the panel starts, and the skip is not re-taken.
- Evidence to capture: Terminal transcript showing panel launch, and listing of .uncle/workflow showing marker absent.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: dir:scratch-project-risky
- Depends on: none
- Exact action: In a separate scratch project, run change-workflow.sh with a real classifier on a plan that mentions deleting data or touching auth/shell driver files.
- Expected result: Full adversarial review runs with no skip stub and no review-skipped marker.
- Evidence to capture: Terminal transcript showing the panel running and absence of skip text and marker.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: dir:scratch-project-env
- Depends on: none
- Exact action: In a third scratch project with a docs-only plan, run change-workflow.sh once with WORKFLOW_SKIP_REVIEW=0 and once with WORKFLOW_SKIP_REVIEW=false.
- Expected result: Both runs perform a full panel review with no skip stub, even if the classifier answered skip.
- Evidence to capture: Transcripts of both runs showing the panel invoked and no skipped line.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: dir:scratch-project-stale
- Depends on: none
- Exact action: After a skip stub is written in a fourth scratch project, edit the plan text, then re-enter ADVERSARIAL_REVIEW.
- Expected result: The stale stub, its rendered md and the marker are discarded and the skip decision is recomputed against the new plan (full review if sha mismatch or floor fails).
- Evidence to capture: Transcript plus file listing before and after showing stub/marker removal.
- Actual result: 
- Status: NOT RUN

### MC-305
- Required for acceptance: YES
- Exclusive resources: dir:scratch-project-corrupt
- Depends on: none
- Exact action: After a skip stub is written in a fifth scratch project, corrupt ADVERSARIAL_REVIEW.json so it is invalid, then re-run the validation stage in change-workflow.sh and stagegate.sh.
- Expected result: Each driver stops immediately with nonzero exit, no retry, no model invocation and no fallback to a full review.
- Evidence to capture: Exit codes and transcripts for both drivers showing no reviewer launched.
- Actual result: 
- Status: NOT RUN

### MC-306
- Required for acceptance: YES
- Exclusive resources: dir:scratch-app-small
- Depends on: none
- Exact action: Run stagegate.sh on a new small app project with a real classifier that answers skip and no risky/sensitive owned paths, then reach the ADVERSARIAL_REVIEW gate.
- Expected result: No panel runs; stub shown at the gate with `skipped: class small, no risk hits`; marker written; human approval gate still appears.
- Evidence to capture: Transcript of the gate screen and listing of review-skipped marker.
- Actual result: 
- Status: NOT RUN

### MC-401
- Exclusive resources: none
- Exact action: Run a risky plan (e.g. one mentioning deletion of data, or owning an auth/secret path) through change-workflow.sh with a real classifier, then watch the ADVERSARIAL_REVIEW stage.
- Expected result: The full reviewer panel runs as before; no skip stub is written and no review-skipped marker exists.
- Actual result: 
- Status: NOT RUN

### MC-402
- Exclusive resources: none
- Exact action: Run a standard/large-class change through stagegate.sh, and separately run a docs-class change with WORKFLOW_CLASSIFY=0, and observe ADVERSARIAL_REVIEW in each.
- Expected result: Both runs launch the full review panel with every lens; classification disabled or non-reducible class never skips.
- Actual result: 
- Status: NOT RUN

### MC-403
- Exclusive resources: none
- Exact action: Run a docs-only change through change-workflow.sh with WORKFLOW_SKIP_REVIEW=0, then repeat with WORKFLOW_SKIP_REVIEW set to empty and to false.
- Expected result: Every run performs a full panel review; no stub is written, even if the classifier answered review: skip.
- Actual result: 
- Status: NOT RUN

### MC-405
- Exclusive resources: none
- Exact action: At the review gate for a skipped review, decline it; also in a separate run edit the plan after the stub is written and re-enter ADVERSARIAL_REVIEW.
- Expected result: Declining reruns ADVERSARIAL_REVIEW as a full panel review with the stub and review-skipped marker removed; a plan edit discards the stale stub and recomputes the decision.
- Actual result: 
- Status: NOT RUN

### MC-406
- Exclusive resources: none
- Exact action: Run a skipped-review change through stagegate.sh up to the review gate, then approve and proceed to the next stages.
- Expected result: Same skip text appears at the gate, the review-skipped marker exists, and the remaining stages and human gates behave unchanged.
- Actual result: 
- Status: NOT RUN

### MC-407
- Exclusive resources: none
- Exact action: Corrupt the skip stub ADVERSARIAL_REVIEW.json so it fails validation, then resume the run in each driver.
- Expected result: The run stops immediately with a nonzero exit, with no retry, no model invocation, and no fallback to full review.
- Actual result: 
- Status: NOT RUN
