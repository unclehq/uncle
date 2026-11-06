## AR-001: Plan leaves open whether quit/exit are USAGE keys, so /q and /e may not resolve.

- Severity: HIGH
- References: CHANGE_PLAN s1.1 D1 ('implementer confirms') and Risks s16; uncle_repl.py:216-221 handles quit/exit before the USAGE check.
- Failure: Plan leaves open whether quit/exit are USAGE keys, so /q and /e may not resolve. Settle: 'The candidate set is USAGE keys plus quit and exit; /q -> quit, /e -> exit, /h -> help, /d -> do, /t -> triage.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Ambiguity message ordering and format are unspecified; the example '/stop, /settings' depends on dict order.

- Severity: HIGH
- References: CHANGE_PLAN s1.1 example message; AC-3 requires only that both names appear.
- Failure: Ambiguity message ordering and format are unspecified; the example '/stop, /settings' depends on dict order. Settle: 'Matches are listed in USAGE definition order, comma-separated, each prefixed with /.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Arguments combined with ambiguity or quit are unspecified (/s foo, /q now).

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1 says existing branches apply but orders nothing for ambiguous input; uncle_repl.py:216-219.
- Failure: Arguments combined with ambiguity or quit are unspecified (/s foo, /q now). Settle: 'Ambiguity is checked before argument validation; /q with args prints usage for /quit and does not quit; /s with args gives the ambiguity refusal.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Uppercase and empty or non-letter names are unspecified (/Q, bare /, /?).

- Severity: MEDIUM
- References: uncle_repl.py:214 lowercases the name; plan guard is only len(name)==1; S4 lists /x only.
- Failure: Uppercase and empty or non-letter names are unspecified (/Q, bare /, /?). Settle: 'Names are lowercased before matching so /Q quits; an empty name or a character matching no command is refused as unknown command, rc 2.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Usage-error rc for expanded commands is unstated; the spec says 'usage error' for /i but 'rc 2' for refusals.

- Severity: MEDIUM
- References: CHANGE_SPEC S6 vs Errors section; uncle_repl.py:218 uses complain, 222 uses refuse.
- Failure: Usage-error rc for expanded commands is unstated; the spec says 'usage error' for /i but 'rc 2' for refusals. Settle: 'A usage error from an expanded command behaves exactly as the full-name command, rc unchanged.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Echoed or logged line and HELP edit are unspecified.

- Severity: LOW
- References: uncle_repl.py:236-237 passes line to self.execute; CHANGE_PLAN D2 optional HELP tweak.
- Failure: Echoed or logged line and HELP edit are unspecified. Settle: 'The original typed line is passed unchanged to execute; any HELP change only appends a one-letter shortcut note and keeps existing assertions valid.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: quit/exit are handled before the USAGE lookup and may not be USAGE keys; the plan leaves the candidate set conditional.

- Severity: HIGH
- References: uncle_repl.py:216-221 handles quit/exit before the USAGE check; CHANGE_PLAN Risks says 'if so'.
- Failure: quit/exit are handled before the USAGE lookup and may not be USAGE keys; the plan leaves the candidate set conditional. Settle with: 'Candidate set = USAGE keys plus quit and exit, and expansion runs before the quit/exit branch.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Expanded one-character commands with arguments (e.g.

- Severity: HIGH
- References: uncle_repl.py:216-219; AC-1 covers only bare `/q`.
- Failure: Expanded one-character commands with arguments (e.g. `/q now`) are unspecified. Settle with: 'Expansion happens first, then all existing branches run unchanged, so `/q now` prints usage for /quit and does not quit.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The plan does not say whether the ambiguous refusal behaves like the unknown-command refusal in session flow.

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1 'return None (rc 2)'; uncle_repl.py:221-223.
- Failure: The plan does not say whether the ambiguous refusal behaves like the unknown-command refusal in session flow. Settle with: 'Ambiguous refusal uses the same stream, rc 2 and session continuation as the unknown-command refusal.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Case, bare `/` and non-letter one-character names are unspecified.

- Severity: MEDIUM
- References: uncle_repl.py:214 lowercases name; CHANGE_SPEC S4 lists only `/qu`, `/frob`, `/x`.
- Failure: Case, bare `/` and non-letter one-character names are unspecified. Settle with: 'Matching is case-insensitive; `/` alone and any single character matching no command keep the existing unknown-command refusal.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The HELP tweak (D2) can break the unknown-command message, which prints the last HELP line.

- Severity: MEDIUM
- References: uncle_repl.py:222 uses HELP.strip().splitlines()[-1]; HELP at lines 30-32.
- Failure: The HELP tweak (D2) can break the unknown-command message, which prints the last HELP line. Settle with: 'Any shortcut mention goes on or before the Commands line; the last line of HELP stays the Commands line.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Candidate order and wording in the ambiguous message are undefined.

- Severity: LOW
- References: CHANGE_PLAN s1.1 example `/stop, /settings` vs AC-3 'names both'.
- Failure: Candidate order and wording in the ambiguous message are undefined. Settle with: 'Candidates are listed in USAGE insertion order joined by ", ", message starting `ambiguous command: /<c>`.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Plan says one-char expansion applies to every USAGE key and that /e (exit) and /q (quit) run, yet it does not say whethe

- Severity: HIGH
- References: CHANGE_PLAN s1.1 says name is set to the expansion 'so all existing branches ... apply'; uncle_repl.py:216-220 handles quit/exit before the USAGE lookup. Plan sentence needed: 'Expansion occurs before the quit/exit check, so /q foo and /e foo produce the usage error and do not quit.'
- Failure: Plan says one-char expansion applies to every USAGE key and that /e (exit) and /q (quit) run, yet it does not say whether the single-char name is matched before or after the existing quit/exit branch. A /q handled by prefix expansion must not skip the 'args present => usage error' check. Decision needed: expansion runs first, then the quit/exit branch.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The plan does not say how an expanded or refused command is echoed.

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1 ambiguous message format; uncle_repl.py:35-49 Out is the 'single escape-filtered writer'. Plan sentence needed: 'The ambiguous message is emitted only via self.refuse and contains only the literal typed single character, which is a single non-control character validated before interpolation.'
- Failure: The plan does not say how an expanded or refused command is echoed. The refusal text interpolates user-typed input, and the plan does not require that input to go through the escape-filtered writer. The ambiguity message could carry unfiltered terminal escapes if built outside self.refuse.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The plan does not specify what the 'one character' is: a typed `/\x1b` or a multibyte or non-ASCII character, or an uppe

- Severity: MEDIUM
- References: uncle_repl.py:214 name = parts[0][1:].lower(); CHANGE_PLAN s1.1 only says len(name)==1. Plan sentence needed: '/Q expands like /q; a one-character name that is not ASCII a-z falls through to the unknown-command refusal.'
- Failure: The plan does not specify what the 'one character' is: a typed `/\x1b` or a multibyte or non-ASCII character, or an uppercase character, which is lowercased. A control or Unicode character is a one-length name that matches nothing and echoes into the unknown-command message. The case behavior of `/Q` is also unspecified.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: The plan says /s is ambiguous (stop, settings) and that /d, /t, /e map to do, triage, exit.

- Severity: MEDIUM
- References: CHANGE_PLAN D1 derives candidates dynamically from USAGE; CHANGE_SPEC AC-2 lists fixed unique letters h,m,i,c,t,d,e,r. Plan sentence needed: 'Tests assert the fixed letter-to-command map so a new USAGE key that makes a shortcut ambiguous fails the suite.'
- Failure: The plan says /s is ambiguous (stop, settings) and that /d, /t, /e map to do, triage, exit. The plan does not say that adding any future USAGE key silently changes which shortcuts are unique or ambiguous. A previously unique /m could become ambiguous, and /r/c/e depend on the current key set. The test should pin it.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: The plan allows execute-type commands (/r resume, /c clear, /i with a number) to be triggered by a single keystroke.

- Severity: LOW
- References: CHANGE_SPEC S2 maps /c and /r; uncle_repl.py:245-254 call self.execute for resume_build and clear_build. Plan sentence needed: 'Shortcut-invoked commands go through the same self.execute path and attended-mode confirmation as full names; the original line is passed unchanged.'
- Failure: The plan allows execute-type commands (/r resume, /c clear, /i with a number) to be triggered by a single keystroke. A mistyped /c or /r runs a state-changing action, the same as the full name. Under attended mode, whether confirmation behavior is identical for shortcuts is not stated.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The plan leaves open whether `/e` and `/q` are candidates, since quit/exit may not be USAGE keys.

- Severity: HIGH
- References: CHANGE_PLAN s1.1 'implementer confirms quit/exit are keys' and Risks s16; code line 216 handles quit/exit before the USAGE check.
- Failure: The plan leaves open whether `/e` and `/q` are candidates, since quit/exit may not be USAGE keys. Settle: 'Candidates are USAGE keys plus quit and exit, de-duplicated; /q expands to quit and /e to exit, both quit the session.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The ambiguous-message format is not fixed (the plan's example lists '/stop, /settings'; the spec only says 'names both')

- Severity: HIGH
- References: CHANGE_PLAN s1.1 example text vs CHANGE_SPEC AC-3 'names both stop and settings'.
- Failure: The ambiguous-message format is not fixed (the plan's example lists '/stop, /settings'; the spec only says 'names both'). Settle: 'The message is exactly `ambiguous command: /s (matches: /settings, /stop)`, candidates sorted alphabetically, sent to stderr via self.refuse, rc 2.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Case and non-letter single characters are unspecified (`/Q`, `/?`, `/1`, bare `/`).

- Severity: MEDIUM
- References: Code line 214 `parts[0][1:].lower()`; plan guard is only `len(name)==1`; spec S4 lists only `/x`.
- Failure: Case and non-letter single characters are unspecified (`/Q`, `/?`, `/1`, bare `/`). Settle: 'Expansion applies after lowercasing so /Q quits; any one-character name with no match, including a bare `/`, takes the unknown-command refusal, rc 2.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: Argument handling for expanded commands is only partly specified: `/q extra` and extra args on `/c`, `/r`, `/t` are unte

- Severity: MEDIUM
- References: CHANGE_PLAN s1.1 'arg validation'; s9 test list covers only `/m unattended` and `/i` without argument.
- Failure: Argument handling for expanded commands is only partly specified: `/q extra` and extra args on `/c`, `/r`, `/t` are untested, and the usage text could name the letter or the full command. Settle: 'Expansion precedes dispatch, so usage text is identical to the full-name form (`/q x` prints `usage: /quit`).'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: No verifiable expected output is given for `/t`, `/d`, `/r` and `/c`, and the test strategy lists only `/m`, `/h` and `/

- Severity: MEDIUM
- References: CHANGE_PLAN s9; CHANGE_SPEC AC-2 lists h,m,i,c,t,d,e,r; code lines 245-259.
- Failure: No verifiable expected output is given for `/t`, `/d`, `/r` and `/c`, and the test strategy lists only `/m`, `/h` and `/i`. Settle: 'Tests assert `/t` and `/d` print the full-name TUI-needed message, and `/c` and `/r` invoke clear_build and resume_build.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: The HELP tweak is optional with no expected text and no test, so a HELP assertion could pass or fail either way.

- Severity: LOW
- References: CHANGE_PLAN s1.1 D2 and Scope cuts; code lines 30-32.
- Failure: The HELP tweak is optional with no expected text and no test, so a HELP assertion could pass or fail either way. Settle: 'HELP is unchanged and no test asserts it mentions one-letter shortcuts.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
