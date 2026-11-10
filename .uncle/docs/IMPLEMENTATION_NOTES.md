# Implementation notes

## Step 1

### Files changed

- `scripts/lib/plan_steps.py` — Added is_owns_junk, safe_token, warn_dropped; paths() takes optional dropped list, drops whitespace/comment-marker/..-segment tokens; both Owns call sites warn once per parse only when tokens dropped; step 1 (D-1, D-7); INV-1; BH-3
- `scripts/lib/plan_model.py` — Added owns_list (split_list + shared predicate + same warning); used where a JSON step's owns is built (new step and steps block); step 1 (D-2, D-7); BH-4

### Deviations

- `scripts/lib/plan_model.py`: JSON-route filtering applied only at the two step-construction sites (steps block, new step in an op); the insert_step op site at the third split_list owns use and the op owns-field sites were left generic for later steps to decide.

### Unresolved concerns

- bash scripts/run-python-tests.sh fails SigningAuditTests.test_every_fixture_commit_and_tag_disables_signing and supervisor-test.py; bash scripts/run-shell-tests.sh fails gate-prompt-test.sh. None print 'warning: step' and the driver baseline lists these suites as PREEXISTING; not diagnosed here.
- No new tests added in this step; parser/model tests belong to later steps.

## Step 2

### Files changed

- `scripts/lib/plan_model.py` — owns_list (added in step 1) now also used in new_step_op's insert_step construction; all three step-construction sites filter JSON owns with is_owns_junk and print the D-7 warning; all-dropped steps pass through with empty owns (no new validator rule); step 2 (D-2, D-7); BH-4; INV-1

### Deviations

- `scripts/lib/plan_model.py`: The warning label for a step created by an insert_step op is the literal 'new' because the driver assigns its number later; op-level owns field edits (set_fields, ~line 827) remain unfiltered split_list since no step label is available there.

### Unresolved concerns

- Step-1 note: existing suites show failures unrelated to this change (signing audit test, supervisor-test.py, gate-prompt-test.sh); not diagnosed.
- No tests added yet; plan-owns-path-shape-test.py belongs to a later step.

## Step 3

### Files changed

- `prompts/plan-check-repair.md` — New repair prompt: edit only the plan file, fix only validator errors; validator output and plan text wrapped in delimited blocks labelled untrusted data, never instructions; step 3 (D-3 trust boundary); BH-5, BH-7; INV-3

### Unresolved concerns

- Prompt uses {{PLAN_FILE}}, {{VALIDATOR_OUTPUT}}, {{PLAN_TEXT}} placeholders; the stagegate.sh helper (a later step) must substitute them and must not let plan text terminate the delimited blocks unchecked.
- No automated test exercises the prompt yet; plan-check-repair-test.py belongs to a later step.

## Step 4

### Files changed

- `scripts/stagegate.sh` — Added plan_check_repair_once (fixed labels project-plan/updated-plan, else exit 2; marker holds plan sha256; spending-stop checked before and after the repair turn, marker removed on the post-turn stop; tree hash+path snapshot outside STATE_DIR/.git/node_modules excluding the plan file; nonzero agent exit, missing/empty or unchanged plan, or other-file changes take the final-failure path and skip re-check), plan_check_tree_snapshot and plan_check_repair_final (stderr names file, 'step: N1, N2' or 'step: unknown', validator text, resume hint; keeps supervision_validation_failed and exit 1). Replaced both inline plan checks (PROJECT_PLAN, UPDATED_PLAN) with the helper. Markers cleared before project-plan generation, before the UPDATED_PLAN gated stage, and on a fresh run (no state file).; step 4 (D-3, D-4, D-5, D-6); BH-5, BH-6, BH-7, BH-9, BH-10; INV-3

### Deviations

- `scripts/stagegate.sh`: The driver has no canonical resume command, so the final message prints 'resume with: $0 (re-run in this project to continue)'. The snapshot also skips node_modules directories, so changes there are not detected. The repair turn's timeout is whatever run_claude enforces; the helper handles only its nonzero exit.

### Unresolved concerns

- Helper is verified only by bash -n and shell-syntax-test.py; behavior tests (plan-check-repair-test.py) are a later step.
- Prompt placeholders are substituted by python3 str.replace; a plan containing the literal placeholder strings would be substituted in order (PLAN_FILE, VALIDATOR_OUTPUT, then PLAN_TEXT), so validator text containing {{PLAN_TEXT}} would be expanded. Not hardened here.
- Step-1 suite failures (signing audit, supervisor-test.py, gate-prompt-test.sh) remain undiagnosed.

## Step 5

### Files changed

- `scripts/tests/plan-owns-path-shape-test.py` — New unittest file: ticked line with prose, no-ticks line, whitespace span dropped, `..` segments and /abs on the parser route, dotted names kept, previously valid tokens (brace, tilde, plus, equals, src/**, dotfiles) kept with a validator-parity check, src/ passes the shape test while valid_path rejects it, golden line with empty stderr, exact one-per-token warning lines, all-dropped gives empty owns, safe_token sanitizing and truncation, JSON route via owns_list with identical warnings and a shared-predicate check; step 5 (D-1, D-2, D-7); BH-3, BH-4, BH-10; INV-1

### Deviations

- `scripts/tests/plan-owns-path-shape-test.py`: The 'all dropped' tests assert empty owns and the warnings; they do not run plan_model.validate, which in this repo only warns 'owns no files' for an empty list rather than raising a missing-owns error, so the validator-error ordering was not asserted. The no-ticks test uses src/*.py because plain() strips ** emphasis in unticked text (pre-existing behavior).

### Unresolved concerns

- Step-1 suite failures (signing audit, supervisor-test.py, gate-prompt-test.sh) remain undiagnosed.
- Op-level owns edits (set_fields) remain unfiltered; untested.
- plan-check-repair-test.py is a later step.

## Step 6

### Files changed

- `scripts/tests/plan-check-repair-test.py` — New test: extracts plan_check_repair_once and its two helpers from stagegate.sh and runs them in bash with a stub agent. Covers fail-repair-pass then fail again (2 calls), unchanged-hash marker (0 calls, exit 1), valid plan clears marker, stale marker (one repair), spending-stop before (0 calls, stop-reason, exit 1) and during repair (no re-check, marker absent, resume calls agent again), stub exit 1 / timeout status 124 / no edit / truncate / delete / other-file edit / still-bad plan (exit 1, one call, marker set, message names file and resume), prompt carries three untrusted-data labels and the inputs, final-failure step lists (unknown, one, several), updated-plan label, hostile validator text (digits only, no command executed, one fixed marker), unknown label exits 2, and a structural check that both call sites use the helper and ensure_project_plan_json follows the PROJECT_PLAN check; step 6 (D-3, D-4, D-5, D-6); BH-5, BH-6, BH-7, BH-9, BH-10; INV-3
- `scripts/stagegate.sh` — Fix found by the new test: plan_check_tree_snapshot compared abspath against cwd-resolved paths, so on a symlinked state dir (macOS /var -> /private/var) files under the state dir were counted as stray changes and every repair failed. Now uses realpath.; step 4 follow-up (D-3 write-scope check); BH-5

### Deviations

- `scripts/tests/plan-check-repair-test.py`: Tests run the extracted helper functions with a stub run_initial_planning_agent rather than the whole driver, so BH-9 (headless, no TUI) is covered only by the helper's independence from the supervisor, not by a full headless run; the 'agent timing out' case is a stub returning status 124 because the helper delegates timeouts to run_claude. ensure_project_plan_json re-derivation is asserted structurally (call order in stagegate.sh), not executed.

### Unresolved concerns

- Step-1 suite failures (signing audit, supervisor-test.py, gate-prompt-test.sh) remain undiagnosed.
- A validator error containing the literal {{PLAN_TEXT}} would be expanded in the repair prompt (not hardened).

## Step 7

### Unresolved concerns

- Op-level owns edits (set_fields) remain unfiltered and untested.
- A validator error containing the literal {{PLAN_TEXT}} would be expanded in the repair prompt (not hardened).
- BH-9 headless run is covered only structurally (helper independent of supervisor), not by a full headless run; AC-8 not claimed as end-to-end.
- Pre-existing failures, identical on a detached HEAD worktree: supervisor-test.py SigningAuditTests.test_every_fixture_commit_and_tag_disables_signing (exit 1), and gate-prompt-test.sh (exit 141, 25 FAIL lines both sides). Not diagnosed.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-2 | IMPLEMENTED | scripts/lib/plan_steps.py paths() drops non-path-shaped tokens with warning | plan-owns-path-shape-test.py OK (step 5) |
| AC-3 | IMPLEMENTED | scripts/lib/plan_model.py owns_list on JSON route | JsonRoute tests in plan-owns-path-shape-test.py OK |
| AC-4 | IMPLEMENTED | scripts/stagegate.sh plan_check_repair_once | plan-check-repair-test.py OK (step 6) |
| AC-5 | IMPLEMENTED | scripts/stagegate.sh final-failure path and marker | plan-check-repair-test.py: one call, exit 1, message names file and resume |
| AC-7 | IMPLEMENTED | scripts/stagegate.sh spending-stop checks around repair | plan-check-repair-test.py spending-stop cases OK |
