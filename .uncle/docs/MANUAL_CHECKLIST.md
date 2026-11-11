# Manual checklist

### MC-200
- Exclusive resources: none
- Depends on: none
- Exact action: In an isolated sample with recorded passing stages, use an editor to change a protected verification file identified by the workflow verification snapshot, then invoke `uncle --revalidate --noui`. Observe the plan and terminal outcome without approving or refreshing the snapshot.
- Expected result: The affected stage is identified as needs-review, never reused or executed. Revalidation exits non-zero without silently accepting the protected change.
- Actual result: 
- Status: NOT RUN

### MC-201
- Exclusive resources: none
- Depends on: none
- Exact action: In an isolated sample whose changed stage reaches a human approval gate, invoke `uncle --revalidate --noui --attended`. Observe the terminal outcome without submitting approval.
- Expected result: Revalidation stops at the reopened gate with exit 75 and reports the stage as blocked. It neither approves the gate nor continues into downstream execution.
- Actual result: 
- Status: NOT RUN

### MC-202
- Exclusive resources: none
- Depends on: none
- Exact action: In an isolated sample prepared with an unchanged passing stage and a changed stage whose runner fails, invoke `uncle --revalidate --noui` and observe the final report. Make the failing service or runner available again without changing stage inputs, then repeat the same invocation.
- Expected result: The first invocation stops on failure, retains the unchanged stage's reused result, and exits non-zero. The second invocation resumes the unfinished stage instead of reporting it reused; downstream execution occurs only after its prerequisite succeeds.
- Actual result: 
- Status: NOT RUN

### MC-401
- Exclusive resources: none
- Depends on: none
- Exact action: In driver-provided sample projects with a matching attestation and a mismatching attestation respectively, manually invoke `uncle verify` and observe its output and exit status.
- Expected result: Verification reports success for the matching sample and a mismatch with nonzero exit for the mismatching sample. Neither invocation starts revalidation, model work, or test execution.
- Actual result: 
- Status: NOT RUN
