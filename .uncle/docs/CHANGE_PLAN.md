# Change Plan: Issue 168

Omitted sections: Schema, Migration, Concurrency, Feature flag, Observability (none apply)

Issue 168

Seeded from [unclehq/uncle#168](https://github.com/unclehq/uncle/issues/168).

## 1. Selected technical approach
The feature already exists in the tree (`Session.slash()`, uncle_repl.py:216-226) with tests. Plan: confirm it against AC-1..AC-5 via the driver's verification commands; make no source edit unless a gap is found. Decision D-1: leave `HELP` unchanged (the request says only "if useful"; HELP is pinned by tests and already lists full names).

## 2-3. Alternatives and rationale
Re-implementing or refactoring the block was rejected: it duplicates working, tested code and widens the diff.

## 4. Components to modify

None required. Candidate only: `scripts/tests/repl-session-test.py` if a requested case (`/q` quits, `/s` ambiguous, `/qu` refused, `/s extra` still ambiguous, `/q extra` gives /quit usage and does not quit) were found missing; the basic cases are present at :145-160.

## 5. Not to modify

TUI slash handling, shell drivers, HELP, other tests. Non-goal: confirmation prompts for single-letter expansions of /c, /d, /r, /e; they run identically to the full command (decision accepted).

## 6-9. Data flow, state, interface, schema
No change.

## 10. Compatibility
Full names and args unchanged (SB-6).

## 12. Error and recovery
Ambiguous and unmatched cases refuse with rc 2 and the session continues.

## 14. Rollback plan
No new edits; to undo the feature revert the changes of commit 73c9097 in `scripts/lib/uncle_repl.py` and `scripts/tests/repl-session-test.py`.

## 16-17. Test strategy

Existing `repl-session-test.py` covers SB-1..SB-5 (including a-z map pin). Run `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` (baseline group `1 2`). No test is expected to fail before the change since the feature is present; this is not a bug fix. Because there is no implementation diff, verification must also include a defect-injection check: temporarily mutate the expansion in `scripts/lib/uncle_repl.py` (e.g. remove the `len(hits) == 1` branch) and confirm at least one `repl-session-test.py` case fails; record the result in the test report and restore the file byte-for-byte afterward (the mutation is never left in the tree). Also verify that the unknown-command refusal echoing the user-typed name goes only through the Out escape filter, with a test that an escape sequence in the name is filtered.

## 18. Manual verification
Run `uncle --noui`, type `/q` (exits), `/s` (refused, lists matches), `/qu` (unknown).

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/uncle_repl.py` | None (already implemented) | Feature present | Low | repl-session-test.py |
| `scripts/tests/repl-session-test.py` | None unless gap found | Cases present | Low | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: bare `/q` (or `/e`) expands to /quit (/exit) and quits the session with process exit status 0. Name matching is case-insensitive via lower() before the a-z check, so `/Q` and `/H` expand identically to `/q` and `/h`. Expansion occurs before argument checks, so `/q <args>` or `/e <args>` expands to /quit (/exit), prints the usage complaint `usage: /quit` (or `usage: /exit`), does NOT quit, sets last-command status 2, and the session continues. | SB-1 | SI-1 | uncle_repl.py slash | repl-session-test /q, repl-session-test /Q uppercase expands like /q and quits (add if missing), repl-session-test `/q extra` prints usage, does not quit, sets status 2 (add if missing) | `/q` exits |
| AC-2: Candidates are exactly the USAGE keys plus quit and exit (currently help, mode, issue, stop, resume, clear, triage, do, settings, quit, exit). A unique one-letter prefix expands to the full command: a one-character name in a-z (after lowercasing, so /Q behaves like /q) expands when exactly one candidate starts with it. Any other single character (digits, punctuation such as /1 or /?) is never expanded and is an unknown command with rc 2. Single-letter expansion of /c (clear), /d (do), /r (resume) and /e (exit) runs identically to the full command with no extra confirmation; this is accepted, as it is the purpose of the feature. Adding a command requires updating the a-z map pin test, which asserts the full letter-to-command table. | SB-2, SB-3 | SI-1 | uncle_repl.py slash | AC-2, map pin: asserts the full letter-to-command table; candidates are exactly USAGE keys plus quit and exit, so adding any command fails the pin until it is updated | /m unattended |
| AC-3: an ambiguous one-character name such as `/s` (or `/S`, since names are case-insensitive) is refused regardless of any arguments; ambiguity is checked before arguments are examined. Refusal sets the last-command status to 2 (rc 2) without ending the session; rc elsewhere means the process exit status at session end. The message lists matches sorted alphabetically, exactly `ambiguous command: /s (matches: /settings, /stop)`. The candidate set is exactly help, quit, exit, mode, issue, stop, resume, clear, triage, do, settings (USAGE keys plus quit and exit); a test pins the full letter-to-command table, so adding or removing a command fails it until the pin is updated. | SB-4 | SI-2 | uncle_repl.py slash | AC-3: asserts the exact message `ambiguous command: /s (matches: /settings, /stop)` (matches sorted alphabetically) on the refuse stream, with refusal status 2, /S refused as ambiguous, /s with arguments is refused as ambiguous, a-z map pin asserts full letter-to-command table and the exact candidate set | /s |
| AC-4: Unmatched letters, multi-letter partial names such as /qu, `/`, `/?` and any one-character name outside a-z (digits and punctuation such as /1 or /?) are unknown commands, refused with rc 2, and never expand. Uppercase one-character names are lowered before matching, so /S is refused as ambiguous exactly like /s. Expansion applies before argument checks: /q extra (and /e foo) expands to /quit (/exit), prints the usage complaint with rc 2, does not quit, and the session continues. The unknown-command refusal echoes the user-typed name only through the Out escape filter, so control or escape sequences in the name are never emitted raw. | SB-5 | SI-2, SI-3 | uncle_repl.py slash | AC-4, repl-session-test: /1 and /? refused as unknown command, no expansion, repl-session-test: /q extra expands to /quit, usage complaint rc 2, session continues, repl-session-test: uppercase /S refused as ambiguous like /s, unknown-command refusal with an escape sequence in the name is filtered (asserted in repl-session-test.py; add if missing) | /qu |
| AC-5 | SB-6 | all | both runners | run-shell/python-tests | n/a |

## Implementation sequence

1. Confirm the existing implementation and tests satisfy AC-1..AC-4 by reading uncle_repl.py:212-234 and repl-session-test.py:145-160, then run both suites. Verify: (a) the a-z map pin asserts the full letter-to-command table, with candidates exactly USAGE keys (help, mode, issue, stop, resume, clear, triage, do, settings) plus quit and exit; (b) the AC-3 test asserts the exact sorted message `ambiguous command: /s (matches: /settings, /stop)` on the refuse stream with status 2, and the refusal path writes through the Out escape filter with a test covering it; (c) case-insensitive cases exist (`/Q` quits like `/q`, `/S` is ambiguous); (d) argument-bearing cases are asserted: `/q extra` and `/e extra` print usage, do not quit, set status 2 and do not end the session, and `/s extra` is refused as ambiguous; (e) one-character names outside a-z (e.g. `/1`, `/?`) are unknown commands (rc 2) and never expand. Add any missing case to repl-session-test.py and record it as a closed gap. Run the defect-injection check: temporarily remove the `len(hits) == 1` expansion branch, confirm at least one repl-session-test.py case fails, record the result, then restore the file exactly. Gap criterion: a green run with all cases present means no diff; if either suite regresses against baseline, fix it in uncle_repl.py or the test and record the fix as a deviation in IMPLEMENTATION_NOTES.md.
   Owns: `scripts/lib/uncle_repl.py`, `scripts/tests/repl-session-test.py`
2. **Conditional gap fix** — Only if step 1 found a gap or either suite regressed against baseline: make the minimal fix or add the missing case in scripts/lib/uncle_repl.py or scripts/tests/repl-session-test.py, and record it as a deviation in IMPLEMENTATION_NOTES.md. Pass criterion: both `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` exit 0 and match baseline. If no gap, make no edit.
   Owns: `scripts/lib/uncle_repl.py`, `scripts/tests/repl-session-test.py`
   Depends on: 1
3. **Defect-injection check** — Temporarily remove the `len(hits) == 1` expansion branch in scripts/lib/uncle_repl.py, run repl-session-test.py and show at least one case fails, then restore the file byte-for-byte and confirm via hash. Record the result in .uncle/docs/CHANGE_TEST_REPORT.md.
   Owns: `scripts/lib/uncle_repl.py`, `.uncle/docs/CHANGE_TEST_REPORT.md`
   Depends on: 2
4. Record in `.uncle/docs/IMPLEMENTATION_NOTES.md` that no further change was needed (or the gap closed).
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 1, 2, 3

## Scope cuts under time pressure
Nothing to cut; HELP edit is already excluded.

## Risks and unresolved questions
- Risk: reviewer expects a diff; the feature predates this run (commit 73c9097). Decision D-2: verify, do not duplicate.
- No blocking planning decisions.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Code derives candidates from USAGE plus quit/exit; the plan must state the exact set and pin it by test. | AC-3 requirement and tests state the exact candidate set; step-1 confirms the map pin covers it. |
| AR-002 | Accepted | Code lowercases before the a-z check; case-insensitivity and non-letter refusal should be stated and tested. | AC-1 and AC-2 requirements state /Q expands like /q and non-letters never expand; step-1 verifies a test exists. |
| AR-003 | Accepted | Code at uncle_repl.py:227-230 complains with usage and does not quit when /q or /e has args; the plan should state it. | AC-1 requirement/behaviors/tests state /q or /e with args prints usage: /quit (or /exit), does not quit, refusal status 2; step-1 checks it. |
| AR-004 | Accepted | rc is ambiguous between session exit status and per-command status; defining both removes the conflict. | AC-3 requirement defines rc as the process exit status at session end and a refusal as setting last-command status 2 without ending the session. |
| AR-005 | Accepted | Code uses sorted(hits); pinning exact message and order in AC-3 makes the behavior testable. | AC-3 requirement/tests now state the exact sorted message `ambiguous command: /s (matches: /settings, /stop)` with rc 2. |
| AR-006 | Accepted | Code lowercases the name before the a-z check, so case-insensitivity is real behavior that needs a stated rule and test. | AC-1 and AC-3 now state /Q behaves as /q and /S is refused as ambiguous; step-1 requires a case test. |
| AR-007 | Accepted | Code refuses ambiguity before args are examined, while /q extra expands then complains; the plan should state both. | AC-3 and AC-4 requirement text state args handling; s3.1 names test cases for ambiguous-with-args and /q extra. |
| AR-008 | Accepted | Candidates are derived from USAGE plus quit/exit, so the plan must say so and require the a-z map pin to be updated when commands are added. | AC-2 requirement states candidate set rule; step-1 checks that the map pin covers every candidate. |
| AR-009 | Accepted | Step 1 lacked a gap criterion and a rule for regressions when no diff is expected. | Step 1 now defines the gap criterion: green run means no diff; a regression is fixed and recorded as a deviation. |
| AR-010 | Accepted | Non-letter single characters are not expanded by the a-z guard; the plan should state this and have it tested. | AC-4 requirement and tests now state that one-character names outside a-z are unknown commands (rc 2) and never expand. |
| AR-011 | Accepted | Code lowercases the name and expands before the quit args check; the plan should state this so behavior is pinned. | AC-1 and AC-4 requirements and tests state case-insensitive expansion and that /q extra expands then refuses with usage rc 2 without quitting; step 1 checks it. |
| AR-012 | Accepted | Silent expansion of /c, /d, /r, /e is the requested behavior; the risk is accepted and should be recorded. | AC-2 requirement records that single-letter expansion runs identically to the full command with no extra confirmation (accepted). |
| AR-013 | Accepted | The unknown-command refusal echoes user-typed text; the plan should require it to go only through the Out escape filter and be verified. | AC-4 requirement and tests, and s9.1, now require escape-filtered refusal output with a test; step-1 checks it. |
| AR-014 | Accepted | With no diff, the pre-existing tests are unproven to catch defects; a defect-injection check is needed. | s9.1 and step-1 require a temporary mutation (removing the len(hits)==1 branch) that must fail a repl-session-test.py case, recorded and reverted. |
| AR-015 | Accepted | Code lowercases before the a-z check, so /Q expands; the plan was silent, so the behavior is now stated and pinned by a test. | AC-1 requirement and tests state /Q and /H expand like lowercase; step-1 confirms/adds a case-insensitive test. |
| AR-016 | Accepted | After expansion /q or /e with args hits the usage complaint path and does not quit; the plan must state this and its status. | AC-1 states /q <args> and /e <args> print usage, do not quit, refused with status 2; step-1 verifies with a test. |
| AR-017 | Accepted | Candidates come from USAGE keys plus quit/exit, so a new command could silently change uniqueness; the full-table pin is the right guard. | AC-2 tests and step-1 state the candidate rule and that the a-z map pin asserts the full letter-to-command table. |
| AR-018 | Accepted | The sorted order and exact text are observable behavior and should be asserted, not only implied. | AC-3 tests and step-1 require asserting the exact ambiguous message on the refuse stream with status 2. |
