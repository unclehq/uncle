# Defects

## D-2

- **Status:** BLOCKED-SETUP
- **Evidence:** Needs a real model agent and a scratch project. Action: provide both.
- **Expected result:** One repair turn, then continue, or exit 1 naming the file, step and resume command.
- **Actual result:** Not performed.

## D-2

- **Status:** NOT RUN
- **Evidence:** The end-to-end scratch scenario was not executed.
- **Expected result:** One repair call, a warning line on stderr, re-check passes; a valid-plan rerun makes zero calls.
- **Actual result:** The scratch-project scenario was not run, so the combined outcome is unobserved.

## D-2

- **Status:** NOT RUN
- **Evidence:** Depends on MC-202, which is absent from the checklist.
- **Expected result:** One fresh repair call for a changed plan hash; identical behaviour for UPDATED_PLAN.
- **Actual result:** Not performed.

## D-2

- **Status:** NOT RUN
- **Evidence:** The five failure modes were not run individually.
- **Expected result:** One agent call, exit 1 and the marker retained, in every case.
- **Actual result:** Not performed.

## D-3

- **Status:** FAIL
- **Evidence:** `/abs` is silently dropped on the Markdown route and kept on the JSON route. See D-3.
- **Expected result:** `../x`, `a/../../b` and `/abs` dropped with warnings; the other tokens kept.
- **Actual result:** `../x` and `a/../../b` were dropped with a warning on both routes. `a..b.py`, `src/{a,b}.py`, `~` and `src/` were kept. `/abs` was dropped silently on the Markdown route (no warning) and kept on the JSON route.

## MC-303

- **Status:** BLOCKED-HUMAN
- **Evidence:** The user must view the warning lines in a real terminal.
- **Expected result:** One warning line per token; no escape effects in a terminal; truncation at 80 characters.
- **Actual result:** The program output matches. Terminal rendering was not observed.
