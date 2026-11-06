# Change Plan

Issue 174

Seeded from [unclehq/uncle#174](https://github.com/unclehq/uncle/issues/174).

Omitted sections: Schema/persistence (none); Migration (none); Feature flag (none); Concurrency (single reader loop only, see item 11)

## 1. Selected technical approach

- D-1: In `uncle_headless.py` spawn the driver with `stderr=subprocess.PIPE` (separate fd). `_stream` selects on both fds; when both are ready in one iteration, stdout is drained before stderr. Stdout lines follow the existing path unchanged. Stderr uses its OWN `EscapeFilter` instance and its OWN line buffer (no state shared with stdout, so escape state and partial lines cannot leak across streams). Stderr bytes are decoded incrementally as UTF-8 with errors replaced by U+FFFD, passed through that filter, and accumulated into complete lines. `redact` runs on complete lines only, after the filter, never on raw read chunks, so a secret split across read boundaries is still redacted; a partial last line is redacted before it is flushed. Each redacted complete stderr line is written verbatim to process stderr (`err`) only, flush each, never to stdout and not reformatted like stdout lines. A partial stderr line (e.g. a prompt without trailing newline) is flushed (redacted first) after the same idle timeout used for stdout partials, not only at EOF; any remainder is flushed at EOF. A stderr flush never splits a stdout partial line already pending: the pending stdout partial is flushed first. Stderr lines also feed `handle_line` for banner detection only; gate/prompt detection is driven by stdout only, so a gate trigger on stderr is ignored and gate behavior is unchanged (S-5). Any text `handle_line` itself formats keeps its current stream, and `handle_line` must never write the stderr line itself to stdout. Tests assert content per stream, never ordering across streams.
- D-2: Each stderr line is written to `err` exactly once, as it arrives (post-redaction, via the TUI's existing redact/EscapeFilter path). Each line is capped at 8192 characters (longer lines are truncated with a trailing `…[truncated]` marker; the cap applies to the retained copy and the line written to `err`, and the raw read buffer for an unterminated line is also capped at 8192 so memory stays bounded). The last 20 redacted lines are kept only as an internal diagnostic buffer for exit-status context and are never replayed or re-emitted. On every termination path (natural exit, idle timeout, signal/exit 130 or 143, and kill) the loop first drains and flushes both fds until EOF (2 s cap), flushing any partial line (redacted), before the status line is written; `_killpg` then kills any descendant still holding either fd, so no stderr bytes are dropped (V-4). The exit path then writes only the existing status line (the same one the headless runner already emits on non-zero exit, B-2), once, to `err`. Stderr lines feed handle_line for banner detection only, never gates. CHANGE_SPEC §4 wording ('final stderr summary includes the driver's last error lines') is amended to mean the error lines already emitted on stderr plus the status line; AC-3 is satisfied because stderr contains the driver's error text exactly once plus the status line. Lines are not duplicated onto stdout; the terminal displays stderr in `--noui`.
- D-3: In `uncle_tui.py`, extract a pure function `format_failure_line(status, last_line)`. When the driver process ends with a non-zero exit status, append one line to the build window: `Driver exited with status N: <last_line>`, or `Driver exited with status N: (no output)` if the driver printed nothing. Exit 0 appends nothing. Signal/user-stop exits 130 and 143 and every other non-zero code (including gate/cancel codes such as 3) count as failure and get the line. Driver stderr stays merged (B-6), so errors cannot be told from other output; `last_line` is defined as the last non-empty line of the merged build-window output before exit. It passes through the same redact and EscapeFilter as all other build-window output before being formatted. The insertion point is chosen after reading `drain_output`/`_absorb_line`.
- D-5: After driver exit, idle timeout, or signal, the headless loop drains both fds until EOF (or a 2 s cap) and flushes any partial lines, redacted, before the status line is written. Any descendant still holding either fd open is killed by `_killpg` after the drain, so no stderr bytes are dropped (V-4).
- D-4: Update `uncle` help text to state errors go to stderr.

## 2. Alternatives considered
| Alt | Verdict |
|---|---|
| Regex-classify merged lines as errors and mirror to stderr | Rejected: heuristic, misses/misclassifies |
| Tee stderr to both stdout and stderr | Rejected: duplicates in a terminal |
| Edit every `>&2` site in drivers | Rejected: already stderr; out of scope |

## 3. Why preferred
True stream separation is exact, small, and needs no change to driver scripts.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
Driver shell scripts, reviewer scripts, `classify_exit` precedence, REPL, exit-code table.

## 6. Data-flow changes
Driver stderr: merged-to-stdout -> own pipe -> filter/redact -> process stderr (headless). TUI unchanged.

## 8. Interface changes
Headless: errors on stderr instead of stdout. No flags added.

## 10. Compatibility strategy
Exit codes and stdout format unchanged; documented in help text.

## 11. Concurrency

Still one thread and one select loop; second fd added. EOF requires both fds closed before final kill; the existing idle/signal handling applies to both fds.

Stream interaction: gate and prompt detection (including partial-line prompt display) operate on stdout only, so a stderr line or partial stderr line never triggers or delays a stdout prompt. Tests assert per-stream content only, not cross-stream ordering.

## 12. Error and recovery
Partial stderr line flushed at EOF. A stderr fd EOF before stdout EOF must not end the loop early.

## 14. Rollback plan
Revert the commit; no persisted state.

## 16. Automated-test strategy

Extend `scripts/tests/headless-run-test.py` (hyphenated name already collected) with stderr cases for AC-1..AC-3. Test the TUI failure line via the pure helper `format_failure_line(status, last_line)` in `uncle_tui.py`, in the new file `scripts/tests/tui-failure-line-test.py`: cases for exit 0 (no line), non-zero with last line, non-zero with no output, 130 and 143 (line shown), and redaction of the last line.

## 17. Regression-test strategy

Existing headless and launcher tests must pass unchanged. Defect injection (AC-6): temporarily set stderr back to STDOUT, confirm new tests fail, restore. Additional headless tests required: (a) driver writes stderr then exits immediately, and driver killed/signalled with stderr pending (exit 130/143): all stderr bytes precede the single status line; (b) driver writes a no-newline stderr prompt then sleeps: it appears in err before the driver exits; (c) secret split across two delayed stderr writes, and a secret in an unterminated last line at EOF: neither appears unredacted in err; (d) multi-megabyte stderr line: 8192-char cap applied and retained text holds no unredacted secret; (e) each distinct driver stderr line occurs exactly once in err and the status line occurs once after all of them (no buffer replay). `scripts/tests/tui-failure-line-test.py` is listed as a protected verification path and in the plan's Verification commands, and includes a case with a secret and an ANSI sequence in the last line asserting the formatted line is redacted and escape-stripped.

## 18. Manual verification
Run `uncle --noui` with a failing request, `2>err.txt`, confirm file has error; trigger same failure in TUI and confirm build window line.

## 19. Observability
The stderr stream is the observability change.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST.md Desired behavior | AC-1, AC-3 | Errors on stderr, non-zero exit | Separate stderr pipe (D-1); stdout drained before stderr when both ready; stderr partial lines flushed on the same idle timeout as stdout | Exact | CAP-none | inspected uncle_headless.py:167,183-296 | CODING |
| R-2 | REPOSITORY | CLAUDE.md rule 7, 13 | AC-4 | Do not weaken tests | Only add assertions | Preserve | CAP-none | headless-run-test.py inspected | CODING |
| R-3 | DESIGN | uncle_headless.py redact | AC-2 | Secrets never leak on new stream, including when split across read chunks | Same redact; stderr gets its own EscapeFilter and line buffer (separate from stdout); stderr buffered to complete lines (or EOF/idle-timeout flush of a partial last line, never splitting a pending stdout partial line) before redact, never redacting raw chunks; invalid UTF-8 replaced with U+FFFD (D-1) | Consistency | CAP-none | redact at line 98 | CODING |

No live authentication required; no external prerequisites.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/uncle_headless.py` | Separate stderr pipe, dual-fd select, filter/redact, stderr passthrough | AC-1..3 | Medium: select/EOF/prompt handling | headless-run-test.py |
| `uncle_tui.py` | Pure helper `format_failure_line(status, last_line)` plus failure line `Driver exited with status N: <last non-empty output line \| (no output)>` on every non-zero exit (incl. 130/143), none on exit 0; last-line text passes through existing EscapeFilter and redact | AC-5 | Low | tui-failure-line-test.py + manual |
| `uncle` | Help text sentence | Docs | Low | launcher-noui-test.sh |
| `scripts/tests/headless-run-test.py` | Add stderr tests | AC-1..3,6 | None | self |
| `scripts/tests/tui-failure-line-test.py` | New test of `format_failure_line` and exit-status handling (exit 0, non-zero, no output, 130/143, redaction) | AC-5 incl. filter/redact of quoted text | None | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | S-1 | V-4 | uncle_headless.py | headless-run-test stderr case, headless-run-test banner-like stderr text is in err, absent from stdout; handle_line-formatted gate text stays on its existing stream, headless-run-test gate prompt on stdout with concurrent stderr noise: gate handling unchanged, gate-like stderr line does not trigger gate handling, per-stream assertions only | `2>file` run |
| AC-2: stderr output is escape-filtered by a dedicated EscapeFilter and redacted per complete line (partial last line redacted before EOF flush); a secret split across read chunks is still redacted; over-long lines are capped at 8192 chars and the retained buffer holds redacted text; invalid UTF-8 decodes to U+FFFD; late stderr is drained before the status line; a stderr partial line without newline is flushed after the stdout idle timeout without splitting a pending stdout partial line. | S-1 | V-2, V-4 | uncle_headless.py | headless-run-test redact/partial, headless-run-test late stderr drained before status line (exit, timeout, signal), headless-run-test secret split across stderr chunks is redacted, headless-run-test invalid UTF-8 on stderr becomes U+FFFD, headless-run-test stderr prompt without newline flushed after idle timeout and does not split a pending stdout partial, headless-run-test partial last stderr line without newline is redacted at EOF, headless-run-test over-long stderr line is capped at 8192 chars and retained buffer holds redacted text, headless-run-test stderr escape state does not leak to stdout | n/a |
| AC-3 | S-2 | V-1 | uncle_headless.py | headless-run-test exit case: stderr contains the driver error text exactly once plus the status line; stdout contains neither | failing run |
| AC-4: existing behavior unchanged; gate and prompt detection use stdout only and are unaffected by stderr lines. | S-4, S-5 | V-1, V-3 | all | existing suites | n/a |
| AC-5: On any non-zero driver exit (including 130/143) the TUI build window gains `Driver exited with status N: <last non-empty output line \| (no output)>`, where the last line is the last non-empty merged build-window line, redacted and escape-filtered; exit 0 adds nothing. | S-3, S-6 | - | uncle_tui.py | tui-failure-line-test: format_failure_line cases (status, last non-empty line, no output, exit 0, 130/143); secret and escape sequence in the last line are redacted/filtered in the failure line | TUI failing run |
| AC-6 | S-1 | - | tests | defect injection | n/a |

Regression test (fails before, passes after): the new headless stderr case asserting driver stderr text is in `err`.

## Implementation sequence

1. S1 Headless stderr split + help text (D-1,D-2,D-4; R-1,R-3; AC-1..3). Stdout is drained before stderr each iteration, with identical handle_line semantics for both fds. Stderr uses its own EscapeFilter and line buffer; redact runs only on complete lines, on a partial line flushed after the same idle timeout as stdout, or on the partial last line at EOF. Includes the 8192-char line cap and 20-line post-redaction retention buffer.
   Owns: `scripts/lib/uncle_headless.py`, `uncle`
2. S2 Headless tests incl. defect injection (AC-1..3,6)
   Owns: `scripts/tests/headless-run-test.py`
   Depends on: 1
3. S3 TUI failure line and its test (D-3; AC-5): add pure `format_failure_line(status, last_line)` to `uncle_tui.py` and wire it at the driver-exit site (read `drain_output`/`_absorb_line` first to choose the insertion point). The failure text is the last non-empty merged output line, passed through the TUI's existing EscapeFilter and redact path (the helper applies them to the quoted line). Test it in `scripts/tests/tui-failure-line-test.py`.
   
   Steps 1 and 3 share no file and may run in parallel.
   Owns: `uncle_tui.py`, `scripts/tests/tui-failure-line-test.py`

## 21. Scope cuts under time pressure
Cut first: S3 (TUI failure line; stderr already merged into build window), then help text. Never cut S1/S2.

## 22. Risks and unresolved questions

| Risk | Mitigation |
|---|---|
| Dual-fd select ends early or hangs on one fd EOF | Loop ends only when both closed; test with stderr-only and stdout-only drivers |
| Interleaving order changes | Documented non-goal |
| Existing tests assume errors on stdout | Check during S2; any needed change is recorded in IMPLEMENTATION_NOTES.md, not silent |

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Plan left the destination of non-error stderr lines and handle_line output undefined; fixing the rule removes ambiguity. | D-1 (s1.1.i1) states every driver stderr line goes verbatim to process stderr only and handle_line output keeps its current stream. |
| AR-002 | Accepted | D-2 left the status line's identity and stream and any buffer replay unspecified, risking duplicate or missing text. | D-2 (s1.1.i2) defines the status line, writes it once to stderr after flush, and forbids replaying the 20-line buffer. |
| AR-003 | Accepted | The TUI failure line wording and exit-code scope were undefined and AC-5 is untestable without them. | D-3 (s1.1.i3) defines exact wording, no-output case, and 130/143 handling; AC-5 and step-3 aligned. |
| AR-004 | Accepted | V-4 requires no dropped stderr bytes on exit, timeout, or signal paths, which the plan did not cover. | Added a drain-before-status-line decision block in section 1 and updated the risk table. |
| AR-005 | Accepted | Real gap: stderr partial lines (e.g. prompts) flushed only at EOF would be held back and could split a pending stdout partial line. | D-1 (s1.1.i1) now flushes stderr partials after the stdout idle timeout without splitting a pending stdout partial line; AC-2 tests updated. |
| AR-006 | Accepted | Real ambiguity about filter instances, chunk-split redaction and invalid UTF-8 on stderr. | D-1 (s1.1.i1) specifies own EscapeFilter and line buffer, redaction on complete lines only, U+FFFD decoding; R-3 and AC-2 updated to match. |
| AR-007 | Accepted | Real gap: stderr partial lines flushed only at EOF would hold back a prompt lacking a trailing newline, contradicting spec section 8. | Edit D-1 (s1.1.i1) so a stderr partial line is flushed after the same idle timeout as stdout, and at EOF. |
| AR-008 | Accepted | Two ready fds make handle_line order undefined; a deterministic rule is cheap and makes tests stable. | Edit D-1 (s1.1.i1): drain stdout before stderr each iteration; identical handle_line semantics for both fds; update R-1 mechanism. |
| AR-009 | Accepted | D-2 already emits nothing extra; the spec §4 'last error lines in summary' wording conflicts and must be amended to match. | D-2 (s1.1.i2) states buffered lines are never re-emitted and CHANGE_SPEC §4 wording is amended accordingly. |
| AR-010 | Accepted | V-4 must hold on kill, idle-timeout and signal paths, not only natural EOF. | D-2 (s1.1.i2) requires draining and flushing both fds before the status line on exit, timeout, signal (130/143) and kill. |
| AR-011 | Accepted | Under merged TUI output errors cannot be told apart, so the failure line must use the last non-empty merged output line. | D-3 (s1.1.i3) defines the failure text as the last non-empty merged build-window line, redacted and escape-filtered; step-3 updated. |
| AR-012 | Accepted | Redacting raw chunks can miss secrets split across reads; redaction must run on complete lines, including the partial last line at EOF. | D-1 (s1.1.i1) buffers stderr to complete lines or EOF before redact; AC-2, R-3 and step-1 updated to match. |
| AR-013 | Accepted | Unbounded stderr lines and an unspecified redaction stage for the retained buffer are real gaps. | D-2 now caps line length at 8192 chars, keeps 20 redacted lines, and AC-2 tests gain a long-line case. |
| AR-014 | Accepted | The TUI failure line quotes output text, so it must be filtered and redacted like other build-window output. | D-3 routes the failure line text through the TUI's existing redact and EscapeFilter path; AC-5 test, impact row and step 3 updated. |
| AR-015 | Accepted | D-2 and the spec disagreed on the summary, and gate trust on stderr lines was unspecified; both are now stated. | Rewrote D-1/D-2: no replay, status line only; stderr lines feed handle_line for banner detection only, never gates. |
| AR-016 | Accepted | Plan must fix that each stderr line is emitted once so tests agree on the count. | D-2 states each stderr line is written once as it arrives and the 20-line buffer is never replayed; AC-3 updated to assert exactly-once. |
| AR-017 | Accepted | D-3 left the failure-line text, empty-output case, and exit-code scope undefined, so AC-5 was untestable. | Rewrite D-3 (s1.1.i3) with exact wording, last non-empty line source, no-output form, non-zero-only incl. 130/143; update AC-5; drop resolved risk row r4. |
| AR-018 | Accepted | The helper and test file location were left conditional while the impact table and step 3 treated them as definite. | Make `format_failure_line(status, last_line)` a definite pure helper tested in tui-failure-line-test.py; update s12.1, s17.1.r2/r5, step-3, AC-5. |
| AR-019 | Accepted | Real gap: stderr feeding handle_line risks gate misfire and nondeterministic interleaving tests. | D-1 and s9.1 say gate/prompt detection is stdout-only, stderr feeds banner detection only, and tests assert per-stream content, never cross-stream order. |
| AR-020 | Accepted | Redaction on raw chunks could miss split secrets; shared filter state could leak between streams. | D-1 now requires a dedicated EscapeFilter and line buffer for stderr, redaction on complete lines only, and redaction of the partial last line before EOF flush; AC-2 updated. |
