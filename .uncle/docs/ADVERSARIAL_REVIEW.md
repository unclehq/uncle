## AR-001: D-6/D-7 owner semantics conflict with BH-3/BH-5 (drivers write on no-issue runs) and BH-9 (driver silent under TUI).

- Severity: HIGH
- References: CHANGE_PLAN D-6/D-7 vs CHANGE_SPEC BH-3, BH-9, AC-6; terminal-title.sh:103.
- Failure: D-6/D-7 owner semantics conflict with BH-3/BH-5 (drivers write on no-issue runs) and BH-9 (driver silent under TUI). Settle: 'When UNCLE_TITLE_OWNER is set, uncle_title_begin/end write nothing; only the TUI retitles on run start and run end.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Exit path is unspecified when the stack was never pushed (guard false) or when exit is via signal/exception.

- Severity: HIGH
- References: CHANGE_PLAN D-3, D-6; BH-4; terminal-title.sh:110 ACTIVE flag.
- Failure: Exit path is unspecified when the stack was never pushed (guard false) or when exit is via signal/exception. Settle: 'end() writes project-only title and CSI 23;2 t only if begin() pushed in this process; it runs in finally and on SIGTERM/SIGHUP, and is idempotent.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Non-numeric/empty issue has no expected title, and 60-char truncation is ambiguous about whether the issue suffix surviv

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1, section 10; CHANGE_PLAN D-4.
- Failure: Non-numeric/empty issue has no expected title, and 60-char truncation is ambiguous about whether the issue suffix survives. Settle: 'Non-numeric or empty issue yields the no-issue title; the project name is truncated so the full title is at most 60 chars and the suffix is kept.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Project name edge cases undefined: relative or empty UNCLE_PROJECT_ROOT, root '/', or name empty after sanitizing.

- Severity: MEDIUM
- References: CHANGE_PLAN D-4, D-5; CHANGE_SPEC section 8 vs AC-1.
- Failure: Project name edge cases undefined: relative or empty UNCLE_PROJECT_ROOT, root '/', or name empty after sanitizing. 'Fallback uncle' conflicts with the AC-1 format 'project first'. Settle: 'Ignore non-absolute UNCLE_PROJECT_ROOT and use cwd; an empty name yields the title exactly `uncle`.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Opt-out values are unspecified (empty, false, unset) and I-4 requires both stdout and stderr ttys though writes go to on

- Severity: MEDIUM
- References: CHANGE_SPEC I-4, BH-7; CHANGE_PLAN R-3.
- Failure: Opt-out values are unspecified (empty, false, unset) and I-4 requires both stdout and stderr ttys though writes go to one stream. Settle: 'Only the exact value 0 disables; any other value enables; writes go to stdout, and both stdout and stderr must be ttys.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Nested drivers started from the uncle line menu may push the stack again, giving mismatched pops.

- Severity: LOW
- References: CHANGE_PLAN D-7, step 4 (uncle begin/end around line menu); AC-6.
- Failure: Nested drivers started from the uncle line menu may push the stack again, giving mismatched pops. Settle: 'The line menu exports UNCLE_TITLE_OWNER, so child drivers push and retitle nothing.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan never says what a driver does when the TUI skipped its own begin (non-tty, opt-out) yet runs children.

- Severity: HIGH
- References: CHANGE_PLAN D-6/D-7; terminal-title.sh:103-106 sets the owner only after the guard passes.
- Failure: Plan never says what a driver does when the TUI skipped its own begin (non-tty, opt-out) yet runs children. Settle with: the TUI exports UNCLE_TITLE_OWNER only when it actually began, and drivers push only when it is unset.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: EXIT-trap and repeat-call behavior is unspecified.

- Severity: HIGH
- References: terminal-title.sh:100-115,116-130; CHANGE_PLAN section 12 says only 'chain onto existing ones'.
- Failure: EXIT-trap and repeat-call behavior is unspecified. Settle with: end is idempotent and runs from the EXIT trap on every exit path including uncle_cancel, and a second begin in the same process is a no-op.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Non-numeric, non-empty issue in bash is unspecified: the old guard rejected it, the plan accepts an empty one.

- Severity: MEDIUM
- References: terminal-title.sh:103 rejects non-digits; CHANGE_SPEC AC-1 lists 'non-numeric issue'; CHANGE_PLAN section 8.
- Failure: Non-numeric, non-empty issue in bash is unspecified: the old guard rejected it, the plan accepts an empty one. Settle with: a non-numeric issue is treated as empty and produces `<project> · uncle`.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The bash path now spawns python3 per begin/end, and the plan does not say what happens if python3 is missing, or which f

- Severity: MEDIUM
- References: CHANGE_PLAN section 1 'terminal-title.sh calls the CLI'; terminal-title.sh:103-107 uses -t 1 -t 2 in bash.
- Failure: The bash path now spawns python3 per begin/end, and the plan does not say what happens if python3 is missing, or which fds the helper's isatty checks see. Settle with: the helper inherits fds 1/2 unchanged, and a missing or failing python3 yields silence with exit 0.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Plan does not say whether end writes the project-only title when this process never did the matching begin (TUI-owned, o

- Severity: MEDIUM
- References: CHANGE_SPEC BH-4; CHANGE_PLAN D-3/D-6; terminal-title.sh:110 gates on UNCLE_TITLE_ACTIVE.
- Failure: Plan does not say whether end writes the project-only title when this process never did the matching begin (TUI-owned, or end without begin). Settle with: end writes nothing unless this process performed the matching begin.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The 60-char cap is ambiguous: whole title or project name.

- Severity: LOW
- References: CHANGE_PLAN D-4 'truncate to 60 chars'; CHANGE_SPEC AC-1.
- Failure: The 60-char cap is ambiguous: whole title or project name. Truncating the whole title could cut off the issue number. Settle with: the project name is truncated to 60 chars before the suffix is appended.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Sanitization covers only C0/C1/DEL, so bidi overrides and line separators can still reach the OSC payload.

- Severity: HIGH
- References: CHANGE_PLAN D-4 and CHANGE_SPEC section 10 name only C0/C1/DEL; I-3 says 'no ESC/BEL/control chars'.
- Failure: Sanitization covers only C0/C1/DEL, so bidi overrides and line separators can still reach the OSC payload. Plan should say: sanitize drops all Unicode categories Cc, Cf, Zl and Zp before truncation.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Order of sanitize and truncate, and what the 60 chars covers, is unspecified.

- Severity: HIGH
- References: AC-1 says 'truncates to 60 chars, never returns empty'; D-4 and BH-8 do not say which part is truncated.
- Failure: Order of sanitize and truncate, and what the 60 chars covers, is unspecified. Plan should say: strip first, truncate only the project name to 60 code points, then append the fixed suffix; an empty result falls back to 'uncle'.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The CLI's handling of a non-numeric, empty or flag-like issue, and how the root reaches it, is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN section 1 CLI 'begin|retitle|end [issue]'; CHANGE_SPEC section 10 says 'digits-only issue' without naming the enforcing layer.
- Failure: The CLI's handling of a non-numeric, empty or flag-like issue, and how the root reaches it, is unspecified. Plan should say: the CLI accepts the issue only if it matches ^[0-9]+$, else treats it as no issue, and reads the root only from the env var, never argv.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: The plan does not say how end() behaves if the tty guard fails at exit, or how a stale or environment-set UNCLE_TITLE_OW

- Severity: MEDIUM
- References: Existing terminal-title.sh:103-114 checks only that UNCLE_TITLE_OWNER is non-empty; D-6, D-7 and AC-6 do not change that.
- Failure: The plan does not say how end() behaves if the tty guard fails at exit, or how a stale or environment-set UNCLE_TITLE_OWNER is treated. Plan should say: end() re-checks the full guard and writes nothing on failure; the owner variable is honored only when it names a live ancestor PID.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Push/pop balance is unspecified for a double begin, an end without begin, or a signal during teardown.

- Severity: MEDIUM
- References: CHANGE_PLAN D-3, D-6, D-7 and 'EXIT traps chain'; uncle_cancel calls exit, but the plan does not say the TUI finally covers SIGTERM.
- Failure: Push/pop balance is unspecified for a double begin, an end without begin, or a signal during teardown. Plan should say: begin pushes at most once per process, end pops only if that process pushed, and end is idempotent and also runs on signal paths.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The plan names no stream for title bytes and does not say what happens when only one of stdout/stderr is a tty.

- Severity: HIGH
- References: terminal-title.sh:103-104 needs -t 1 and -t 2; plan R-3 says 'isatty both' but AC-5 says 'stdout or stderr is not a tty'.
- Failure: The plan names no stream for title bytes and does not say what happens when only one of stdout/stderr is a tty. Decision: 'Title and stack sequences go to stderr in the TUI and stdout in shell, and only when both are ttys; otherwise nothing is written.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: End-sequence order and the run-end versus session-exit behavior conflict.

- Severity: HIGH
- References: CHANGE_SPEC BH-4 says run end or exit gives project-only title then pop, but plan D-6 says per-run the TUI only retitles and pops once at session end.
- Failure: End-sequence order and the run-end versus session-exit behavior conflict. Decision: 'On exit write the project-only title, then CSI 23;2 t. A run end while the TUI lives writes only the idle title and no pop.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The 60-char cap scope, unit and order against sanitizing are ambiguous.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 says 'truncates to 60 chars'; plan D-4 gives no order, scope or unit.
- Failure: The 60-char cap scope, unit and order against sanitizing are ambiguous. Decision: 'The 60 cap applies to the project name only, in code points, after stripping controls and trimming; the suffix is appended afterwards.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: The title for a non-numeric, empty or very long issue argument is not defined.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 verification lists 'non-numeric issue' and section 10 says digits-only, but no BH row gives the expected title.
- Failure: The title for a non-numeric, empty or very long issue argument is not defined. Decision: 'A non-numeric or empty issue is treated as no issue and yields `<project> · uncle`; digits are never truncated.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: The CLI `end` runs in a separate python3 process and is stateless, so it cannot know whether begin pushed.

- Severity: MEDIUM
- References: terminal-title.sh:110 gates end on UNCLE_TITLE_ACTIVE; plan D-7 and the CLI `end` define no such state.
- Failure: The CLI `end` runs in a separate python3 process and is stateless, so it cannot know whether begin pushed. Decision: 'Any non-empty UNCLE_TITLE_OWNER makes begin and end no-ops, and bash end acts only if this shell's begin pushed, tracked by UNCLE_TITLE_ACTIVE.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: AC-8 defect injection does not name the mutants or how the mutated copy is exercised, and it is on the cut list.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-8 versus plan section 16 ('a mutated temp copy') and section 21 listing defect-injection automation as cut first.
- Failure: AC-8 defect injection does not name the mutants or how the mutated copy is exercised, and it is on the cut list. Decision: 'The test runs terminal_title.py from a temp copy with (a) end writing bare uncle and (b) sanitize disabled, and requires the suite to fail for each; this check is never cut.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
