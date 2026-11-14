# Verification report

## Findings

### MC-902

- **Action:** Sourced scripts/lib/audit-verdict.sh in four isolated temp sandboxes (AUDIT_GATE=0, WORKFLOW_NOT_READY_GATE unset, stub set_state) and called final_audit_route_verdict NOT_READY. Scenarios: (1) no artifacts; (2) only .uncle/attestation.json freshly written; (3) fresh handoff.json + attestation.json; (4) both artifacts present but with mtime 2020-01-01 (retained from an earlier run, nothing written this run).
- **Expected result:** Messages name only artifacts confirmed written for the current run; none confirmed -> point to .uncle/docs/FINAL_AUDIT.md; hand-off completion does not claim findings are in a published PR; retained artifacts alone do not justify naming them.
- **Actual result:** (1) none: 'findings are in .uncle/docs/FINAL_AUDIT.md' - OK. (2) attestation only: 'findings are inthe attestation (.uncle/attestation.json)' - names correct artifact but has a missing-space typo ('inthe'). (3) both: names hand-off record and attestation, no PR-publication claim - OK. (4) retained/stale: message still names the hand-off record and attestation as holding findings, because the function only tests file existence/non-emptiness (-s) and has no run-provenance check; expected pointer to .uncle/docs/FINAL_AUDIT.md. All scenarios ended in STATE=COMPLETE.
- **Defects:** Retained artifacts from an earlier run are named as holding current findings (audit-verdict.sh:216-222); plus spacing typo 'inthe' in the attestation-only message (line 219-222).

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-902 | YES | FAIL | Function at scripts/lib/audit-verdict.sh:216-225 uses only `[[ -s file ]]` for handoff.json and attestation.json; no run_id/mtime comparison. Scenario 4 output: 'Final audit is NOT_READY; completing so the PR reviewer can decide (findings are in the hand-off record (.uncle/handoff/handoff.json) and the attestation (.uncle/attestation.json)).' Scenario 2 output contains 'inthe'. Not covered by driver green-check as a live exercise of this function. |
