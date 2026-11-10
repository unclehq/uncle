# Verification report

## Findings

### MC-105

- **Action:** Ran `test_spending_stop_before_repair` and `test_spending_stop_during_repair_then_resume` (stub agent, not a real HTTP 402) via the new-suite command.
- **Expected result:** Spending_limit stop, no re-check, fresh repair on resume.
- **Actual result:** Both tests passed. A real host 402 was not triggered.
- **Defects:** None

### MC-106

- **Action:** None. This needs a real model agent and a saved invalid UPDATED_PLAN. `test_updated_plan_label` covers only the label with a stub.
- **Expected result:** One repair turn, then continue, or exit 1 naming the file, step and resume command.
- **Actual result:** Not performed.
- **Defects:** D-2

### MC-201

- **Action:** Not run end to end. The suites cover repair count, marker and warning separately with stubs.
- **Expected result:** One repair call, a warning line on stderr, re-check passes; a valid-plan rerun makes zero calls.
- **Actual result:** The scratch-project scenario was not run, so the combined outcome is unobserved.
- **Defects:** D-2

### MC-203

- **Action:** None. `Depends on: MC-202`, which is not in the checklist. `test_changed_plan_or_stale_marker_gets_one_repair` passes but does not cover the UPDATED_PLAN pairing.
- **Expected result:** One fresh repair call for a changed plan hash; identical behaviour for UPDATED_PLAN.
- **Actual result:** Not performed.
- **Defects:** D-2

### MC-205

- **Action:** Not run. The five stub-agent failure modes were not executed individually. `test_failed_repairs_exit_once_with_marker_set` passed but its case coverage was not matched to the five modes.
- **Expected result:** One agent call, exit 1 and the marker retained, in every case.
- **Actual result:** Not performed.
- **Defects:** D-2

### MC-207

- **Action:** Ran the probe on the Markdown and JSON routes for each token.
- **Expected result:** `../x`, `a/../../b` and `/abs` dropped with warnings; the other tokens kept.
- **Actual result:** `../x` and `a/../../b` were dropped with a warning on both routes. `a..b.py`, `src/{a,b}.py`, `~` and `src/` were kept. `/abs` was dropped silently on the Markdown route (no warning) and kept on the JSON route.
- **Defects:** D-3

### MC-303

- **Action:** Called `plan_model.owns_list` with an ANSI-escape plus 200-char token. The output was one line with the token truncated to `...` and the escape stripped. The check needs a real terminal.
- **Expected result:** One warning line per token; no escape effects in a terminal; truncation at 80 characters.
- **Actual result:** The program output matches. Terminal rendering was not observed.
- **Defects:** None

### MC-402

- **Action:** Ran the probe for `src/{a,b}.py`, `~`, `+`, `=`, `a..b.py`, `src/`, `../x` and `foo bar` on both routes. Directory rejection comes from `test_directory_like_token_passes_shape_but_validator_rejects` (passed).
- **Expected result:** Valid tokens kept with no warning; `..` and whitespace tokens dropped with a warning.
- **Actual result:** As expected on both routes.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-105 | YES | PASS | Two stub-based tests passed; a real HTTP 402 was not triggered. |
| MC-106 | YES | BLOCKED-SETUP | Needs a real model agent and a scratch project. Action: provide both. |
| MC-201 | YES | NOT RUN | The end-to-end scratch scenario was not executed. |
| MC-203 | YES | NOT RUN | Depends on MC-202, which is absent from the checklist. |
| MC-205 | YES | NOT RUN | The five failure modes were not run individually. |
| MC-207 | YES | FAIL | `/abs` is silently dropped on the Markdown route and kept on the JSON route. See D-3. |
| MC-303 | YES | BLOCKED-HUMAN | The user must view the warning lines in a real terminal. |
| MC-402 | YES | PASS | Probe output matched on both routes; `src/` rejection covered by a passing test. |
