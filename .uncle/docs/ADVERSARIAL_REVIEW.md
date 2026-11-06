## AR-001: Spec/plan contradict the code on the candidate set.

- Severity: HIGH
- References: CHANGE_SPEC §4 lists 11 names; uncle_repl.py:217-220 derives cands from USAGE, so any future USAGE key silently changes expansion.
- Failure: Spec/plan contradict the code on the candidate set. SB-4 and the ambiguity text assume `/s` matches only /settings and /stop. The code builds candidates from USAGE plus quit/exit, and the plan never says whether USAGE contains every command. Plan should say: 'The candidate set is exactly help, quit, exit, mode, issue, stop, resume, clear, triage, do, settings, and a test pins it.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Letter-only expansion is unspecified for uppercase and non-letter single characters.

- Severity: MEDIUM
- References: uncle_repl.py:214,216 lowercases before the a-z check; SI-1 says only 'a-z names expand'.
- Failure: Letter-only expansion is unspecified for uppercase and non-letter single characters. Code lowercases first, so `/Q` expands, but AC-1..4 never state that; `/1` and `/?` fall through to unknown. Plan should say: '/Q expands the same as /q; non-letter single characters are never expanded.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Expanded /q and /e with arguments is unspecified.

- Severity: MEDIUM
- References: uncle_repl.py:227-230 calls complain(USAGE[name]) and returns None; AC-1 covers only bare /q.
- Failure: Expanded /q and /e with arguments is unspecified. After expansion `/q now` hits the quit-with-args path, which complains and does not quit, with an unstated rc. Plan should say: '/q or /e with any argument prints usage: /quit, does not quit, and exits rc 2.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Two statements conflict on rc.

- Severity: MEDIUM
- References: CHANGE_PLAN §12 says rc 2 and the session continues; CHANGE_SPEC AC-3 says exits rc 2.
- Failure: Two statements conflict on rc. 'Ambiguous and unmatched cases refuse with rc 2 and the session continues' sits beside AC-1's 'quits the session with rc 0', and the rc for ordinary and error commands in an interactive session is undefined. Plan should say: 'rc is the process exit status at session end, and a refusal sets the last-command status to 2 without ending the session.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Ambiguous message ordering and the `/` and `/?` cases are underspecified.

- Severity: LOW
- References: uncle_repl.py:225 uses sorted(hits); CHANGE_SPEC §8 gives the string but AC-3 does not.
- Failure: Ambiguous message ordering and the `/` and `/?` cases are underspecified. Matches are sorted alphabetically, while AC-3 only says 'names /settings and /stop'. Plan should say: 'The ambiguous message lists matches sorted alphabetically, exactly `ambiguous command: /s (matches: /settings, /stop)`.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Case of one-character names is unspecified.

- Severity: MEDIUM
- References: uncle_repl.py:214 lowercases before the :216 check; SI-1 says only a-z and no test covers uppercase.
- Failure: Case of one-character names is unspecified. Code lowercases first, so /Q quits. Plan sentence: 'One-character slash names are case-insensitive: /Q behaves as /q, and /S is refused as ambiguous.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Arguments on one-character names are unspecified.

- Severity: MEDIUM
- References: uncle_repl.py:224-231; AC-3/AC-4 cover only bare /s, /qu, /, /?.
- Failure: Arguments on one-character names are unspecified. Ambiguity refuses before args are examined, while /q extra expands then complains of usage. Plan sentence: 'Ambiguous names are refused rc 2 regardless of args; /q extra gives the /quit usage complaint and does not quit.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Plan lists a fixed candidate set but code derives it from USAGE plus quit/exit, so a new command silently changes expans

- Severity: MEDIUM
- References: uncle_repl.py:217-221 vs CHANGE_SPEC section 4 fixed list; SI-1 verified only by map pin.
- Failure: Plan lists a fixed candidate set but code derives it from USAGE plus quit/exit, so a new command silently changes expansion. Plan sentence: 'Candidates are exactly USAGE keys plus quit and exit; adding a command requires updating the a-z map pin.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: No rule for a regression in the verification commands when the plan expects no diff.

- Severity: LOW
- References: CHANGE_PLAN step 1 says 'edit only if a gap is found' with no gap criterion; CHANGE_SPEC section 5 marks rows ADD.
- Failure: No rule for a regression in the verification commands when the plan expects no diff. Plan sentence: 'If either suite regresses against baseline, the regression is fixed in uncle_repl.py or the test and recorded as a deviation; a green run means no diff.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Non-letter single characters (e.g.

- Severity: LOW
- References: uncle_repl.py:216 guards on a-z; AC-4 names only /qu, unmatched letters, /, /?.
- Failure: Non-letter single characters (e.g. /1) are unspecified. Plan sentence: 'Any one-character name outside a-z, including digits and punctuation, is an unknown command with rc 2 and never expands.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Plan never states whether a bare `/s`-style ambiguity or expansion must apply identically for `/Q` (uppercase) and for o

- Severity: MEDIUM
- References: uncle_repl.py:214,216,227-230 lowercases the name and applies the quit args check after expansion; SB-1..SB-5 specify no uppercase or argument-bearing case.
- Failure: Plan never states whether a bare `/s`-style ambiguity or expansion must apply identically for `/Q` (uppercase) and for one-character names with args. Settle: 'Name matching is case-insensitive via lower(); uppercase `/Q` expands to /quit; expansion applies before argument checks, so `/q extra` expands to /quit and then refuses with usage (rc 2) without quitting.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The destructive or side-effecting expansions (/c clear, /d do, /r resume, /e exit) are not stated to be safe against acc

- Severity: LOW
- References: CHANGE_SPEC SB-2 maps /d to do and /c to clear with no confirmation behavior; uncle_repl.py:222-223 expands silently.
- Failure: The destructive or side-effecting expansions (/c clear, /d do, /r resume, /e exit) are not stated to be safe against accidental single-keystroke triggering. Settle: 'Single-letter expansion of /c, /d, /r, /e runs identical to the full command with no extra confirmation; this is accepted.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: SI-3 (escape filtering) is asserted for the ambiguity and unknown messages, but the unknown-command message echoes user-

- Severity: LOW
- References: uncle_repl.py:233 interpolates user name into the refuse message; SI-3 verification cites only a :598 test, not the slash refusal path.
- Failure: SI-3 (escape filtering) is asserted for the ambiguity and unknown messages, but the unknown-command message echoes user-supplied name text. Settle: 'The refusal message echoing the user-typed name is emitted only through the Out escape filter.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Plan has no implementation diff, so the testable claim rests on pre-existing tests the plan never proves can fail.

- Severity: HIGH
- References: CHANGE_PLAN s9: 'No test is expected to fail before the change since the feature is present'; uncle_repl.py:216-226.
- Failure: Plan has no implementation diff, so the testable claim rests on pre-existing tests the plan never proves can fail. Plan should state: 'Verification must include a defect-injection check: temporarily mutating the expansion (e.g. removing the len(hits)==1 branch) must make at least one repl-session-test.py case fail, recorded in the test report.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Uppercase and mixed-case one-char input is unspecified: the code lowercases the name before the a-z check, so `/Q` expan

- Severity: MEDIUM
- References: uncle_repl.py:214 `.lower()` precedes :216; SI-1 'Only 1-char a-z names expand'.
- Failure: Uppercase and mixed-case one-char input is unspecified: the code lowercases the name before the a-z check, so `/Q` expands to quit, but SI-1 and AC-1 say nothing about case. Plan should say: '`/Q` and `/H` expand identically to lowercase forms (or are refused)', with a test.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: One-char expansion with extra args is not specified for non-mapped quit/exit: `/q extra` and `/e foo` would fall to the

- Severity: MEDIUM
- References: uncle_repl.py:227-230 complain(USAGE[name]) returns None; AC-1 covers only bare `/q`.
- Failure: One-char expansion with extra args is not specified for non-mapped quit/exit: `/q extra` and `/e foo` would fall to the usage complaint path, and the rc is undefined. Plan should say: '`/q <args>` prints usage /quit and does not quit; rc is X'.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Candidate set conflicts: the spec lists 11 names, but the code builds candidates from USAGE plus quit/exit, so any futur

- Severity: MEDIUM
- References: uncle_repl.py:217-220 vs CHANGE_SPEC s4 list; SI-1 'map pin a-z'.
- Failure: Candidate set conflicts: the spec lists 11 names, but the code builds candidates from USAGE plus quit/exit, so any future USAGE key silently changes uniqueness (e.g. adding a 'q...' command breaks `/q`). Plan should say: 'The a-z map pin test asserts the full letter-to-command table, so any new command fails it.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Observable output for the ambiguous refusal and its rc 2 depends on `refuse`, and the plan does not say whether the sort

- Severity: LOW
- References: uncle_repl.py:225 sorted(hits); CHANGE_SPEC s8 message; AC-3 only says 'names /settings and /stop'.
- Failure: Observable output for the ambiguous refusal and its rc 2 depends on `refuse`, and the plan does not say whether the sorted match order or stderr/stdout stream is asserted. Plan should say: 'Tests assert the exact message `ambiguous command: /s (matches: /settings, /stop)` on the refuse stream and rc 2.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
