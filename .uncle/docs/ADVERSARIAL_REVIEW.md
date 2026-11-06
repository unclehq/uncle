## AR-001: The plan never says where lines from the driver's stderr that are not errors (banners, gate prompts, progress notes) end

- Severity: HIGH
- References: CHANGE_PLAN D-1 ('Stderr lines also feed handle_line') against CHANGE_SPEC section 4 and S-5 ('gate messages unchanged').  Suggested sentence: 'Every driver stderr line is written verbatim to process stderr only; handle_line may react to it but must never write it to stdout, and gate/banner text formatted by handle_line keeps its current stream.'
- Failure: The plan never says where lines from the driver's stderr that are not errors (banners, gate prompts, progress notes) end up. D-1 sends all stderr to `err`, but the spec's desired behavior reads as if only errors go there. Also, `handle_line` is fed stderr lines, so whether gate or banner text is shown on stdout or stderr is left open.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: D-2 says the final summary on `err` is preceded by nothing extra and that the 'status line is retained'.

- Severity: HIGH
- References: CHANGE_PLAN D-2 against CHANGE_SPEC AC-3 and S-2 ('status line only (B-2)').  Suggested sentence: 'On non-zero exit the 20-line buffer is never re-emitted; only the existing status line is written, once, to stderr, after all driver stderr lines have been flushed.'
- Failure: D-2 says the final summary on `err` is preceded by nothing extra and that the 'status line is retained'. AC-3 and S-2 require stderr to contain the driver's error text and the status line. The plan never says what the status line is, which stream it uses, or whether the 'last 20 stderr lines' buffer is replayed. It is also unclear whether replaying would duplicate lines.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The plan does not define the TUI failure line (AC-5, S-3).

- Severity: HIGH
- References: CHANGE_PLAN D-3 and risk row 4 against CHANGE_SPEC AC-5.  Suggested sentence: 'The TUI appends exactly "Driver exited with status N: <last non-empty build-window line, or (no output)>" for every non-zero exit except a user-initiated stop (130/143), and nothing on exit 0.'
- Failure: The plan does not define the TUI failure line (AC-5, S-3). D-3 says 'last error line seen', but under merged stderr the TUI cannot tell stderr from stdout. The plan leaves open what happens when the driver printed no output, what the exact wording is, and whether exit codes 130, 143 or 3 (cancelled, gate) count as failure.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The ordering of the status line against late stderr output is not specified.

- Severity: MEDIUM
- References: CHANGE_PLAN sections 11 and 12 against CHANGE_SPEC V-4 ('none dropped at EOF').  Suggested sentence: 'After driver exit, timeout or signal, the loop drains both fds until EOF (or a 2 s cap) before the status line is written, and any descendant holding either fd open is killed by _killpg.'
- Failure: The ordering of the status line against late stderr output is not specified. Both pipes are read in one select loop and the 'final kill' happens after EOF on both. The plan does not say whether the loop drains all remaining stderr bytes after the process exits or after a signal or idle timeout. Output could be lost on kill, which V-4 forbids.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The plan does not say how stderr output interacts with stdout prompts that lack a trailing newline.

- Severity: MEDIUM
- References: CHANGE_SPEC section 8 ('Prompts without trailing newline must still display promptly') against CHANGE_PLAN D-1 ('partial last line flushed at EOF').  Suggested sentence: 'A partial stderr line is flushed after the same idle timeout used for stdout prompts, and a stderr write never splits a partial stdout line already pending.'
- Failure: The plan does not say how stderr output interacts with stdout prompts that lack a trailing newline. The spec requires such prompts to display promptly. Stderr line-by-line flushing with partial lines held until EOF could hold back a stderr prompt, while a partial stdout line is pending, and could interleave mid-line.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The plan does not define the redaction and escape-filter rules for output with sequences or secrets split across a read

- Severity: LOW
- References: CHANGE_PLAN D-1 ('second EscapeFilter') against CHANGE_SPEC AC-2.  Suggested sentence: 'Stderr uses its own EscapeFilter and line buffer, redaction runs on complete lines only, and invalid UTF-8 bytes are replaced with U+FFFD.'
- Failure: The plan does not define the redaction and escape-filter rules for output with sequences or secrets split across a read boundary or across the stdout/stderr pair. A single shared `EscapeFilter` or a second one is ambiguous. Binary or invalid UTF-8 bytes on stderr are also unspecified.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Stderr partial lines are flushed only at EOF, but Spec §8 requires prompts without newline to display promptly.

- Severity: HIGH
- References: CHANGE_PLAN D-1 'line by line... partial last line flushed at EOF' vs CHANGE_SPEC §8 prompts without trailing newline.
- Failure: Stderr partial lines are flushed only at EOF, but Spec §8 requires prompts without newline to display promptly. Plan should say: a stderr partial line is flushed after the same idle/prompt heuristic as stdout, not only at EOF.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Gate/banner detection now sees two sources with undefined order when both fds are ready.

- Severity: HIGH
- References: D-1 'Stderr lines also feed handle_line'; Spec §15 interleaving not guaranteed; Risks row on existing tests.
- Failure: Gate/banner detection now sees two sources with undefined order when both fds are ready. Plan should say: when both fds are ready, drain stdout before stderr each iteration, with handle_line semantics identical for both.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: D-2 keeps the last 20 stderr lines but emits nothing extra, while Spec §4 says the final summary includes the driver's l

- Severity: MEDIUM
- References: CHANGE_PLAN D-2 vs CHANGE_SPEC §4 'final stderr summary includes the driver's last error lines'.
- Failure: D-2 keeps the last 20 stderr lines but emits nothing extra, while Spec §4 says the final summary includes the driver's last error lines. Plan should say: buffered lines are not re-emitted, and Spec §4 wording is amended accordingly.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Kill, idle-timeout and signal paths (exit 130/143) are unspecified for pending stderr bytes, risking V-4 violation.

- Severity: MEDIUM
- References: V-4 'none dropped at EOF'; Plan §11 covers only EOF, not kill-triggered paths.
- Failure: Kill, idle-timeout and signal paths (exit 130/143) are unspecified for pending stderr bytes, risking V-4 violation. Plan should say: on kill or signal, drain and flush both fds before the final status line.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: D-3 needs 'last error line seen' but the TUI stream is merged, so errors are indistinguishable from ordinary output.

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 and §6 'TUI unchanged' vs Spec S-3.
- Failure: D-3 needs 'last error line seen' but the TUI stream is merged, so errors are indistinguishable from ordinary output. Plan should say: the last error text is the last non-empty line of merged output before exit.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Redaction applied per line on the stderr stream is unspecified for secrets split across read chunks, and for the partial

- Severity: HIGH
- References: CHANGE_PLAN D-1 says bytes pass through EscapeFilter, redact, then lines are written; AC-2 requires a partial last line redacted.
- Failure: Redaction applied per line on the stderr stream is unspecified for secrets split across read chunks, and for the partial last line at EOF. Plan must say: stderr is buffered to complete lines (or EOF) before redact runs, never redacting raw chunks.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: The plan does not say how unbounded or very long stderr lines are handled, or how the 20-line retention interacts with t

- Severity: MEDIUM
- References: CHANGE_PLAN D-2 keeps the last 20 stderr lines with no length cap and does not say whether they are stored pre- or post-redaction.
- Failure: The plan does not say how unbounded or very long stderr lines are handled, or how the 20-line retention interacts with them. Plan must say: stderr line length and retained buffer are capped, and the retained lines are the redacted text.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: TUI failure line includes the last error text, but the plan does not say whether that text is redacted or escape-filtere

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 and AC-5 appends exit status plus the last error line to the build window; V-2 scope is headless only.
- Failure: TUI failure line includes the last error text, but the plan does not say whether that text is redacted or escape-filtered. Plan must say: the TUI failure line text passes through the same redact and EscapeFilter as other build-window output.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: D-2 contradicts the spec on the final summary: D-2 says nothing extra is emitted, while the spec says stderr contains bo

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 and D-2 versus CHANGE_SPEC section 4; handle_line is fed stderr in D-1.
- Failure: D-2 contradicts the spec on the final summary: D-2 says nothing extra is emitted, while the spec says stderr contains both the driver's error text and the status line. Stderr lines feeding handle_line also leaves unspecified whether a gate trigger on stderr is trusted. Plan must say: the final summary adds no replay of lines, and gate detection on stderr lines is intended or ignored.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: D-1 sends stderr lines to handle_line and D-2 says the final summary is preceded by nothing extra, but the plan never sa

- Severity: HIGH
- References: CHANGE_PLAN D-1/D-2 versus CHANGE_SPEC AC-3. D-2 keeps 'the last 20 stderr lines' but says they are not re-emitted. The plan should say: 'Each stderr line is written to err exactly once, as it arrives; the exit summary writes only the status line and never replays the buffer.'
- Failure: D-1 sends stderr lines to handle_line and D-2 says the final summary is preceded by nothing extra, but the plan never says whether stderr lines are also echoed or formatted like stdout lines. AC-3 requires 'driver error text and the status line' on stderr, and the plan does not say whether the 20-line buffer is replayed at exit. Tests could disagree on whether the error text appears once or twice.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: D-3 says the TUI failure line shows the 'last error line seen', but the plan never defines what that is when the TUI mer

- Severity: HIGH
- References: CHANGE_PLAN D-3 and risk row 4 ('TUI exit-handling site not yet read'), versus CHANGE_SPEC AC-5. The plan should say: 'The failure line is `driver exited with status N: <last non-empty output line>`, or `driver exited with status N` when there is no output; it is shown only for non-zero exits, and is also shown for signal exits 130 and 143.'
- Failure: D-3 says the TUI failure line shows the 'last error line seen', but the plan never defines what that is when the TUI merges stderr into stdout (B-6). It also never says what shows when the driver emitted no output, when the exit code is 0, or when the exit is a signal, 130 or 143. AC-5 cannot be tested without these answers.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The test strategy says the TUI test is placed in the headless suite 'if a pure helper is extractable', else in a new fil

- Severity: MEDIUM
- References: CHANGE_PLAN section 16 versus Change-impact table row 5 and step 3 Owns. The plan should say: 'Extract a pure function `format_failure_line(status, last_line)` in uncle_tui.py and test it in the new file scripts/tests/tui-failure-line-test.py.'
- Failure: The test strategy says the TUI test is placed in the headless suite 'if a pure helper is extractable', else in a new file. The plan lists the new file in the change-impact table and the step 3 'Owns' list as definite. The test location and the helper's existence are therefore left open.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The plan leaves unspecified how stderr and stdout interact when both fds are open.

- Severity: MEDIUM
- References: CHANGE_PLAN D-1, section 11, and section 12. The plan should say: 'Gate and prompt detection use stdout only; stderr lines feed handle_line only for banner detection. Tests assert content per stream, never ordering across streams.'
- Failure: The plan leaves unspecified how stderr and stdout interact when both fds are open. Partial-line prompts on stdout must display promptly while stderr is mid-line, and a prompt-detection pass fed by stderr could misfire. AC-4 requires gate behavior to be unchanged, yet D-1 feeds stderr to handle_line. The interleaving test is nondeterministic unless the plan fixes it.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The plan does not say how redaction behaves when a secret is split across stderr chunk boundaries or lines.

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 ('second EscapeFilter', redact) and CHANGE_SPEC AC-2. The plan should say: 'Redaction is applied per complete line after the filter, and a partial last line is redacted before it is flushed at EOF.'
- Failure: The plan does not say how redaction behaves when a secret is split across stderr chunk boundaries or lines. It also does not say whether a separate EscapeFilter instance is required to stop escape state leaking between the two streams. AC-2 tests could pass or fail depending on the implementation.
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
