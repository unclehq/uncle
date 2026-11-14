# Verification report

## Findings

### MC-902

- **Action:** Wrote a disposable harness in /tmp/mc902 (outside the project). It patched transport._via_http1 to return mocked response headers with a schema-invalid edit-ops packet ({ops:'wrong'}) and patched interruptible_chat for the repair turns. It ran hosted.run_opencode as a bounded updated-plan writer (UNCLE_UPDATED_PLAN_ANSWER_TOKENS set) with no live credentials or network. Five cases: (1) x-seren-schema-relaxed 'true' with a repair that fixes the draft; (2) the same header with a repair that leaves the draft invalid; (3) whitespace-only header; (4) no header; (5) x-seren-schema-check only. I spied on run_agent's usage dict to read constraint_mode.
- **Expected result:** Only a nonblank relaxed header enables exactly one targeted repair. A successful repair returns a valid packet and keeps the relaxed mode in constraint_mode. A failed repair raises the existing validation error with no second repair. Blank, absent and check-only headers take the no-repair failure path.
- **Actual result:** (1) One generation request. The repair agent made 2 chat turns (one edit_file call, then a status reply). It returned a packet with ops=[] and constraint_mode='targeted schema repair (locally validated) after json_schema_relaxed'. (2) One generation request. The repair ran once, with 1 chat turn and no edit. It raised ValueError 'Unrepaired draft: Model response violates the artifact schema (json_schema_relaxed constraint): $.ops must be array', with no further repair. (3)-(5) One generation request each, 0 repair chat calls. Each raised ValueError 'Model response violates the artifact schema (json_schema constraint): $.ops must be array', so the mode stayed json_schema. In case (2), the usage constraint_mode I read was 'json_schema_relaxed', so the failure was not relabelled as repaired.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-902 | YES | PASS | The harness output is from /tmp/mc902/h.py and h2.py. Case 1: http_calls=1, repair_chat_calls=2, ops=[], error=None. Case 2: http_calls=1, repair_chat_calls=1, ops=None, error 'Unrepaired draft ... json_schema_relaxed constraint'. Cases 3-5: http_calls=1, repair_chat_calls=0, error 'violates the artifact schema (json_schema constraint)'. The code path is http_agent.py lines 1441-1460, where repairable = object and (not bounded_writer or relaxed). The prepared unit tests in scripts/tests/edit-schema-limits-test.py cover the same header and repair logic. I did not re-run them, because the driver green-check owns that. I did not capture constraint_mode for the blank, absent and check-only cases. Their mode was json_schema, shown by the error text. The 'repair ran once' claim in case 2 rests on 1 repair chat turn plus the 'Unrepaired draft' error, with no second repair attempt seen. |
