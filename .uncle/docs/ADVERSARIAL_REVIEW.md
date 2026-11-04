## AR-001: Behavior when the next arg starts with `--` and stdin is an empty non-TTY pipe is unspecified.

- Severity: HIGH
- References: CHANGE_PLAN s1 (value exists iff $1 != --*); CHANGE_SPEC S-4, S-11.
- Failure: Behavior when the next arg starts with `--` and stdin is an empty non-TTY pipe is unspecified. Settle: 'A next argument starting with `--` is never text; the launcher reads stdin, and empty input exits 1 with `Error: --OPT text cannot be empty`; use `--OPT=--text` for such text.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Ordering between stdin read and rejecting later unknown arguments is unspecified (`--application --bogus < f`).

- Severity: HIGH
- References: uncle:221-235 unknown-argument case; CHANGE_PLAN s1 gives no ordering.
- Failure: Ordering between stdin read and rejecting later unknown arguments is unspecified (`--application --bogus < f`). Settle: 'Stdin is read only after all arguments parse; an unknown argument exits 1 before any stdin read or temp file creation.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Plan does not say which wins if both UNCLE_STARTUP_TEXT and UNCLE_STARTUP_TEXT_FILE are set (e.g.

- Severity: MEDIUM
- References: CHANGE_PLAN s6 and s8 D-2; uncle:115-116,249.
- Failure: Plan does not say which wins if both UNCLE_STARTUP_TEXT and UNCLE_STARTUP_TEXT_FILE are set (e.g. caller-exported env). Settle: 'When UNCLE_STARTUP_TEXT_FILE is set the TUI ignores UNCLE_STARTUP_TEXT; the launcher leaves UNCLE_STARTUP_TEXT empty in the stdin case.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Where the single trailing-newline strip happens relative to the emptiness check and the `--text` path is undefined.

- Severity: MEDIUM
- References: CHANGE_SPEC s15 assumptions, AC-7; CHANGE_PLAN s1.
- Failure: Where the single trailing-newline strip happens relative to the emptiness check and the `--text` path is undefined. Settle: 'The strip occurs only in the stdin branch of housekeeping_input.py, after CRLF normalization and before the emptiness check; --text is never stripped.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Exclusivity check runs only on option entry, so `--application --application` or `--application --housekeeping` ordering

- Severity: MEDIUM
- References: uncle:148-151,173-176; CHANGE_SPEC AC-8, S-9.
- Failure: Exclusivity check runs only on option entry, so `--application --application` or `--application --housekeeping` ordering relative to stdin read is unspecified. Settle: 'A second mode option exits 1 with the mutually-exclusive error before any stdin is read.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Whether any `--application` message must still contain `requires an argument` is unstated, though the TTY message replac

- Severity: LOW
- References: CHANGE_SPEC S-5; CHANGE_PLAN s8 D-1, R-3.
- Failure: Whether any `--application` message must still contain `requires an argument` is unstated, though the TTY message replaces it. Settle: 'No --application message retains `requires an argument`; existing assertions on it, if any, are recorded as a deviation.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Housekeeping stdin text moves from env to a file, but the plan never says what UNCLE_STARTUP_TEXT holds in the stdin cas

- Severity: HIGH
- References: CHANGE_PLAN s8 D-2 and s6; uncle:158,164 currently set UNCLE_STARTUP_TEXT from stdin; s19 admits existing test assumptions are unverified.
- Failure: Housekeeping stdin text moves from env to a file, but the plan never says what UNCLE_STARTUP_TEXT holds in the stdin case, or which the TUI prefers if both are set. Plan should say: in the stdin case UNCLE_STARTUP_TEXT is empty and only UNCLE_STARTUP_TEXT_FILE is set; in the value case only UNCLE_STARTUP_TEXT is set.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The validated reader replaces the old housekeeping check, which only rejected whitespace-only input.

- Severity: HIGH
- References: CHANGE_PLAN s19.i2, R-3; uncle:164-168 (old $(cat) path has no limits).
- Failure: The validated reader replaces the old housekeeping check, which only rejected whitespace-only input. Existing housekeeping stdin tests with control chars, CRLF or large text may now change, yet the plan expects no assertion changes. Plan should say: run the existing housekeeping stdin cases before step 3 and treat any conflict as stop-and-ask.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The value rule `$1 != --*` makes any value starting with `--` go to stdin mode, regressing `--application "--foo bar"` w

- Severity: MEDIUM
- References: CHANGE_PLAN s1 and s8; uncle:178-187 accepts any non-empty $1 for --application.
- Failure: The value rule `$1 != --*` makes any value starting with `--` go to stdin mode, regressing `--application "--foo bar"` which works today, while s8 claims value forms are unchanged. Plan should say: this regression is accepted, documented under Compatibility, and pinned by a test (text starting with -- needs the = form).
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The plan does not say when stdin is read relative to the rest of argument parsing.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 (function called inline in the arg loop); uncle:221-235 unknown-argument exit.
- Failure: The plan does not say when stdin is read relative to the rest of argument parsing. With `--application --bogus`, stdin could be consumed and a temp file made before `Unknown argument` exits. Plan should say: stdin is read only after the whole argument list parses successfully.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The one-newline strip is stdin only, but housekeeping_input.py shares one validation path for --text and stdin.

- Severity: LOW
- References: CHANGE_PLAN s1, D-5; housekeeping_input.py:30-35.
- Failure: The one-newline strip is stdin only, but housekeeping_input.py shares one validation path for --text and stdin. Plan should say: the strip is applied only on the stdin read path in the helper, never on --text.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan relies on the EXIT trap to delete the private stdin text file, but the launcher later may exec the TUI, which skips

- Severity: HIGH
- References: CHANGE_PLAN s9 and s6 rely on the EXIT trap (uncle:119); exec replaces the shell so the trap never fires.
- Failure: Plan relies on the EXIT trap to delete the private stdin text file, but the launcher later may exec the TUI, which skips the trap. Add: 'The text file lives only in the 0700 mktemp dir, 0600, and is removed on every exit path including exec (TUI deletes it after reading).'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Non-TTY stdin that never reaches EOF (FIFO, open pipe in CI) blocks forever; the size cap limits bytes, not time.

- Severity: MEDIUM
- References: CHANGE_SPEC I-2 guards only TTY; housekeeping_input.py:35 does a blocking read.
- Failure: Non-TTY stdin that never reaches EOF (FIFO, open pipe in CI) blocks forever; the size cap limits bytes, not time. Add: 'Stdin read has no timeout; a non-TTY stdin that never closes blocks, accepted and documented', or specify a timeout.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: I-3 claims identical validation for all inputs, but value-form text (argv, --opt=VALUE) skips size, UTF-8 and control-ch

- Severity: MEDIUM
- References: CHANGE_SPEC I-3 and S-3/S-11; the plan keeps UNCLE_STARTUP_TEXT unvalidated while housekeeping_input.py already supports --text.
- Failure: I-3 claims identical validation for all inputs, but value-form text (argv, --opt=VALUE) skips size, UTF-8 and control-character checks. Add: 'Value-form text is also validated via housekeeping_input.py --text', or state that the value path is unvalidated.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Any text beginning with -- is treated as an option, so a brief starting with -- is silently misread.

- Severity: LOW
- References: CHANGE_PLAN s1 guard `$1 != --*`; S-11 covers only the = form.
- Failure: Any text beginning with -- is treated as an option, so a brief starting with -- is silently misread. Add: 'Positional text beginning with -- is never text; use --opt=VALUE, and the unknown-argument error mentions that form.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Order of CRLF normalization, single-newline strip and empty check is unspecified, and --text shares the helper.

- Severity: HIGH
- References: CHANGE_SPEC §15, PLAN D-5; housekeeping_input.py lines 33-46; AC-7.
- Failure: Order of CRLF normalization, single-newline strip and empty check is unspecified, and --text shares the helper. Settle with: 'Normalize CRLF/CR to LF, then strip exactly one trailing LF on the stdin path only (never --text), then apply the empty check.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Plan does not say whether the 1048576 cap counts raw bytes before the strip.

- Severity: HIGH
- References: PLAN §16 boundaries; AC-4; housekeeping_input.py lines 35-36.
- Failure: Plan does not say whether the 1048576 cap counts raw bytes before the strip. Settle with: 'The cap applies to raw stdin bytes before CRLF normalization and newline stripping.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Whether stdin stays unread for empty value forms ("" and =) is unspecified, so the I-4 test is ambiguous.

- Severity: MEDIUM
- References: PLAN §12, I-4, AC-5; uncle lines 154-157, 182-185.
- Failure: Whether stdin stays unread for empty value forms ("" and =) is unspecified, so the I-4 test is ambiguous. Settle with: 'Empty value forms are refused without reading stdin; --OPT= never falls back to stdin.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The value rule leaves next arguments like -h, verify and single-dash words ambiguous.

- Severity: MEDIUM
- References: PLAN §1 value rule; uncle lines 122-124.
- Failure: The value rule leaves next arguments like -h, verify and single-dash words ambiguous. Settle with: 'Only arguments beginning with -- are options; any other next argument, including -h, verify and empty string, is the value.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Order of stdin read versus later parse errors is unspecified (e.g.

- Severity: MEDIUM
- References: PLAN §1; uncle lines 148-151, 221-234; AC-8, S-9.
- Failure: Order of stdin read versus later parse errors is unspecified (e.g. --application --bogus < f, or with --issue). Settle with: 'Stdin is read at the option, so its validation errors win over later unknown-argument or mutual-exclusion errors.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: D-1 TTY message includes 'empty input' for both options while AC-3 requires it only for housekeeping.

- Severity: LOW
- References: PLAN §8 D-1 vs CHANGE_SPEC AC-3.
- Failure: D-1 TTY message includes 'empty input' for both options while AC-3 requires it only for housekeeping. Settle with: 'The D-1 message including empty input is used for both options and tests assert it for both.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
