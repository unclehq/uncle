## AR-001: SB-6 says lines typed during a build are held or consumed as the gate answer and never dropped, but D-3 says the REPL do

- Severity: HIGH
- References: CHANGE_SPEC SB-6 vs CHANGE_PLAN D-3/D-2. Plan should say: 'During a build the REPL does not read stdin; unread lines stay buffered and run in order after the build returns; unattended drivers never read fd 0; an attended gate consumes exactly one line per gate.'
- Failure: SB-6 says lines typed during a build are held or consumed as the gate answer and never dropped, but D-3 says the REPL does not read input during a build. Non-gate lines (and all lines in unattended mode) have no stated consumer, and piped lines could be eaten as gate answers.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Exit-code policy is inconsistent.

- Severity: HIGH
- References: CHANGE_PLAN D-6, D-8; SB-10. Plan should say: 'Exit code is that of the most recent build or refusal, reset to 0 by a later successful non-build line; a Ctrl-C-stopped build counts as 130; /quit and EOF return that code; SIGTERM exits 143.'
- Failure: Exit-code policy is inconsistent. SB-10/D-8 say last build result, 2 on refusal, else 0, but never say what a later successful chat or slash line does after a failed build. D-6 treats 130 as 'return to prompt', which is unclear against 'last build result' at quit.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Confirmation prompts (SB-7 quit confirm, D-11 replacement) are unspecified for non-tty input, blank or unrecognized answ

- Severity: MEDIUM
- References: CHANGE_SPEC SB-7, SB-16; CHANGE_PLAN D-11. Plan should say: 'Only y/yes (case-insensitive) consents; blank, other text, EOF or Ctrl-C declines; quit confirmation is asked only on attended tty and EOF during it quits and stops the build.'
- Failure: Confirmation prompts (SB-7 quit confirm, D-11 replacement) are unspecified for non-tty input, blank or unrecognized answers, and Ctrl-C. EOF at the quit confirmation is not defined, which could conflict with I-4.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Over-long line handling is underspecified: the remainder of the line after 1 MiB may be processed as new commands, and i

- Severity: MEDIUM
- References: CHANGE_SPEC section 8 and AC-4. Plan should say: 'A line over 1 MiB is discarded through its newline, one error is printed, it counts as a refused action, and the session continues.'
- Failure: Over-long line handling is underspecified: the remainder of the line after 1 MiB may be processed as new commands, and it is unclear whether the rejection counts as a refusal for exit code 2. The two readers may differ.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Slash commands in odd states are unspecified: unknown commands, /stop or /resume with nothing to act on, /mode with no a

- Severity: MEDIUM
- References: CHANGE_SPEC SB-14, AC-9; CHANGE_PLAN section 6-9. Plan should say: 'Lines starting with / are never sent to chat; unknown commands print an unknown-command message and count as refused; /stop and /resume with nothing to act on print a notice and do not change the exit code; /mode with no argument prints the current mode.'
- Failure: Slash commands in odd states are unspecified: unknown commands, /stop or /resume with nothing to act on, /mode with no argument, and slash lines vs chat routing.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Ctrl-C handling during chat in flight or at a gate prompt is undefined against the D-7 consecutive counter.

- Severity: LOW
- References: CHANGE_PLAN D-7 and section 11. Plan should say: 'Ctrl-C during chat cancels the request and counts as the first idle Ctrl-C; Ctrl-C at a gate prompt is handled by the driver and does not touch the counter.'
- Failure: Ctrl-C handling during chat in flight or at a gate prompt is undefined against the D-7 consecutive counter.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan doesn't say `_driver_from_env` keeps its signature and error behavior once it wraps `prepare_driver`.

- Severity: HIGH
- References: CHANGE_PLAN s7.1 and step 1; `prepare_driver(..., err)` interface vs. unspecified wrapper.
- Failure: Plan doesn't say `_driver_from_env` keeps its signature and error behavior once it wraps `prepare_driver`. Plan should say: the wrapper keeps its exact signature, and a test asserts byte-identical stderr and exit codes for each existing failure path.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Launcher rows to replace are ambiguous ('rows 13-14' vs 'the two bare-refusal rows'), and other bare --noui combos are u

- Severity: HIGH
- References: CHANGE_PLAN R-4, change-impact row for launcher-noui-test.sh; AC-1 names only bare, UNCLE_NOUI=1 and --noinput.
- Failure: Launcher rows to replace are ambiguous ('rows 13-14' vs 'the two bare-refusal rows'), and other bare --noui combos are unspecified. Plan should say: bare --noui with any unrecognized argument keeps its current error and exit code, and only rows asserting bare refusal are replaced.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Moving ISSUE_REQUEST_RE may break code or tests that reference `uncle_tui.ISSUE_REQUEST_RE`.

- Severity: MEDIUM
- References: CHANGE_PLAN D-9 and s5.1.
- Failure: Moving ISSUE_REQUEST_RE may break code or tests that reference `uncle_tui.ISSUE_REQUEST_RE`. Plan should say: `uncle_tui.ISSUE_REQUEST_RE` remains a valid name bound to the same compiled object.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Session SIGTERM handler and `run()`'s handler interplay is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN s8.1, D-6, R-3.
- Failure: Session SIGTERM handler and `run()`'s handler interplay is unspecified. Plan should say: the session handler is saved before each `run()` and restored after, and `run()` leaves no changed handler or process-group state behind.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: D-8 exit code rules collide when a refusal follows a failed build or the reverse.

- Severity: MEDIUM
- References: CHANGE_PLAN D-8 vs AC-4/SB-10.
- Failure: D-8 exit code rules collide when a refusal follows a failed build or the reverse. Plan should say: the exit code comes solely from the last executed action (refused=2, build=its code, else 0), and chat or slash lines don't reset it.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan never constrains model-supplied action fields (issue number, paths, stage names).

- Severity: HIGH
- References: CHANGE_SPEC section 10 says only 'rules as in TUI'; PLAN D-10 and the repl_actions step list no field-level constraints.
- Failure: Plan never constrains model-supplied action fields (issue number, paths, stage names). Settle with: 'repl_actions.execute accepts only allowlisted action types, re-validates fields via parse_reply (integer issue N, fixed stage set, paths inside project root), and refuses anything else with exit 2 and no driver started.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Unspecified whether model output or piped stdin lines can answer a gate or replacement prompt.

- Severity: HIGH
- References: PLAN D-3 (driver reads fd 0 during a build), D-11 (EOF/no declines); I-5 says only 'recorded human'. Piped scripts can pre-supply 'yes' lines.
- Failure: Unspecified whether model output or piped stdin lines can answer a gate or replacement prompt. Settle with: 'Gate and replacement confirmations are read only from user input, never model output; EOF at a gate means decline/stop, never approve.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Escape filtering is stated for build output only, not chat replies or errors.

- Severity: MEDIUM
- References: PLAN section 6-9 applies 'filtered output' to run(); SPEC section 10 and I-1 name EscapeFilter but repl_chat has no filter.
- Failure: Escape filtering is stated for build output only, not chat replies or errors. Settle with: 'All REPL stdout/stderr text, including chat replies, runner errors, issue titles and exception messages, passes through EscapeFilter, which strips control bytes except newline and tab, and CSI/OSC sequences.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The 1 MiB line bound has no defined overflow behavior on the os.read reader.

- Severity: MEDIUM
- References: SPEC section 8 says 'bounded (1 MiB) and rejected'; PLAN D-2 describes the reader but not overflow.
- Failure: The 1 MiB line bound has no defined overflow behavior on the os.read reader. Settle with: 'A line over 1 MiB is discarded through the next newline or EOF, one error is printed, and the remainder is never run as a command or gate answer.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: SIGTERM handling covers only the build process group, not the chat runner subprocess.

- Severity: MEDIUM
- References: PLAN section 11 and R-3 reference only run() killpg; AC-7 and I-4 require no child left.
- Failure: SIGTERM handling covers only the build process group, not the chat runner subprocess. Settle with: 'The SIGTERM handler terminates the chat runner subprocess group and the build group, then exits 143; the process inventory test covers both.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Precedence and default for startup mode env vars are undefined.

- Severity: LOW
- References: PLAN D-4 names the --attended flag and both env vars without precedence or default.
- Failure: Precedence and default for startup mode env vars are undefined. Settle with: 'If both UNCLE_STARTUP_ATTENDED and UNCLE_STARTUP_UNATTENDED are set, attended wins; if neither is set, the default is attended.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Lines typed during a build (SB-6) are unspecified when the gate is unattended or stdin is piped; D-3 says no input is re

- Severity: HIGH
- References: CHANGE_PLAN D-3 vs CHANGE_SPEC SB-6, SB-10.
- Failure: Lines typed during a build (SB-6) are unspecified when the gate is unattended or stdin is piped; D-3 says no input is read, SB-6 says held, never dropped. Settle: 'During a build the REPL reads no input; unread lines are processed as normal prompts after run() returns; attended gates consume exactly one line each.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: D-8 exit-code rule is ambiguous when refusals, builds, and chat lines interleave, and for 130/143.

- Severity: HIGH
- References: CHANGE_PLAN D-6, D-8; CHANGE_SPEC SB-10, AC-4.
- Failure: D-8 exit-code rule is ambiguous when refusals, builds, and chat lines interleave, and for 130/143. Settle: 'Exit code is that of the most recent build-or-refusal event; chat and slash lines don't change it; a Ctrl-C-stopped build exits 130 at EOF.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Slash command behavior in odd states or args is unspecified (/stop with no build, bad /mode value, non-numeric /issue, e

- Severity: MEDIUM
- References: CHANGE_SPEC SB-14 'invalid usage prints usage'; CHANGE_PLAN D-10, D-12.
- Failure: Slash command behavior in odd states or args is unspecified (/stop with no build, bad /mode value, non-numeric /issue, extra args, unknown command). Settle: 'Invalid or unknown commands print one usage line with no state change; /stop with no build prints "no build running".'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: Over-long line and EOF edge cases are undefined: the 1 MiB boundary, whether the rest of the line is discarded, untermin

- Severity: MEDIUM
- References: CHANGE_SPEC section 8; CHANGE_PLAN D-2, D-11.
- Failure: Over-long line and EOF edge cases are undefined: the 1 MiB boundary, whether the rest of the line is discarded, unterminated final line, EOF mid-gate. Settle: 'Lines over 1048576 bytes are discarded through the newline with "line too long"; an unterminated final line is processed; EOF at a gate or confirmation declines.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: Ctrl-C is undefined during an in-flight chat reply, an attended gate prompt, and the replacement confirmation.

- Severity: MEDIUM
- References: CHANGE_PLAN D-7, D-11, section 11; SB-8, SB-9.
- Failure: Ctrl-C is undefined during an in-flight chat reply, an attended gate prompt, and the replacement confirmation. Settle: 'Ctrl-C during chat cancels the request and counts as one idle press; at a gate it goes to run() semantics; at a confirmation it declines.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: Banner and stream routing in piped runs is unspecified, so exact-stdout tests are underdetermined (D-1 vs SB-1/SB-13/AC-

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 vs CHANGE_SPEC SB-1, SB-13, AC-4.
- Failure: Banner and stream routing in piped runs is unspecified, so exact-stdout tests are underdetermined (D-1 vs SB-1/SB-13/AC-4). Settle: 'The banner always prints to stdout, including piped runs; the prompt follows D-1; replies and progress go to stdout, errors to stderr.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
