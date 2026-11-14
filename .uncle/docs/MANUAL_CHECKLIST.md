# Manual checklist

## Completion wording

### MC-902
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Exercise final_audit_route_verdict with NOT_READY and the override gate disabled in isolated sandboxes containing: no output artifacts; only an attestation written for this run; both hand-off and attestation artifacts written for this run; and artifacts retained from an earlier run with neither written for the current run. Capture each completion message.
- Expected result: Messages name only artifacts confirmed written for the current run. When none are confirmed, they point to .uncle/docs/FINAL_AUDIT.md. Hand-off completion does not claim that findings are in a published PR. Retained artifacts alone do not justify naming them.
- Evidence to capture: Artifact inventory and run provenance for each scenario, emitted messages, and resulting workflow state.
- Actual result: 
- Status: NOT RUN
