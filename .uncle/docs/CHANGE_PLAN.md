# Change plan: issue 165 bare `--noui` interactive session

Omitted sections: Schema/persistence (none); Migration (none); Feature flag (none: bare form only); Observability (plain output only)

Issue 165

Seeded from [unclehq/uncle#165](https://github.com/unclehq/uncle/issues/165).

## 1. Selected technical approach
New `scripts/lib/uncle_repl.py` runs a line-based loop over an injectable I/O object. Actions execute through a new shared `repl_actions.py` executor that validates with `home_actions.parse_reply`, prepares drivers with a new `uncle_headless.prepare_driver` (extracted from `_driver_from_env`, behavior-preserving) and runs them with `uncle_headless.run`. Chat goes through `repl_chat.py`, a synchronous adapter over the same home agent / supervisor request path the TUI uses. The launcher execs the REPL for bare `--noui`.

## 2. Alternatives
(a) Embed the loop in the TUI class headlessly: drags curses in, violates I-1. (b) Wrap `uncle_headless.py` only: it is one-shot and has no chat. (c) Selected: new loop + extracted shared pieces.

## 3. Why selected
Satisfies I-1/I-2/I-3 with minimal edits to the TUI; reuses `run()` signal, killpg and gate handling.

## 4. Decisions (resolved in plan)

| ID | Decision | Reason |
|---|---|---|
| D-1 | The banner always prints to stdout, including piped runs. The prompt `uncle> ` is printed only when stdin is a tty or `UNCLE_REPL_PROMPT=1`; piped runs echo no prompt decoration (SB-13). Replies and build progress go to stdout; errors and refusals go to stderr. | Stable, exact stdout/stderr for scripts and tests |
| D-2 | tty: `readline` if importable, else `input()`; non-tty: own unbuffered os.read line reader (so attended gate reads on fd 0 never lose buffered lines). Line bound is 1048576 bytes: a longer line is discarded through its next newline or EOF, one 'line too long' error is printed to stderr, and the discarded remainder is never run as a command, chat line, or gate/confirmation answer; the same bound and discard rule apply to the driver's gate reads. An unterminated final line within the bound at EOF is processed as a normal line. EOF at a gate prompt or any confirmation (quit, brief replacement) declines/stops, never approves. | Gate/chat share input safely; defined overflow and EOF behavior keeps the two readers identical and testable, and overflow cannot smuggle commands or answers |
| D-3 | Gate prompts come from the driver stream. During a build the REPL itself reads no stdin; lines not yet read stay buffered in the fd 0 reader and run in order as normal prompts after `run()` returns, never dropped. Unattended drivers never read fd 0. An attended gate consumes exactly one line per gate from fd 0, read only via the REPL's shared unbuffered line reader so no buffered line is lost or over-consumed. Gate answers are read only from user input (fd 0), never from model/chat output or action fields; EOF at a gate means decline/stop, never approve. Chat resumes after the build. | Satisfies SB-6 'held until gate resolves'; every line has exactly one consumer (gate answer or post-build prompt), so piped lines cannot be eaten as extra gate answers, and model output cannot approve a human gate (I-5). |
| D-4 | Build mode = `--attended` flag or launcher env (`UNCLE_STARTUP_ATTENDED/UNATTENDED`). Precedence: `--attended` flag, then env; if both env vars are set, attended wins; if neither is set, the default is attended. `/mode` overrides for later builds; attended with non-tty stdin refused by `run()` message, session continues | Reuses #155 resolution |
| D-5 | Replies print after each reply (no streaming); streaming is a follow-up | Smallest safe slice; tests exact |
| D-6 | `run()` return 130 (128+SIGINT) while in session = build stopped, return to prompt; that build counts as the most recent build event with code 130 (a Ctrl-C-stopped build is a build result of 130), so a session ending at EOF/`/quit` right after exits 130 unless a later build-or-refusal event replaces it; 143 = quit session (SIGTERM exits 143). The session SIGTERM handler is saved before and restored after each `run()` (see section 11), leaking no handler or process-group state, so a SIGTERM arriving between builds is still handled by the session. | R-8; consistent with D-8 |
| D-7 | Idle Ctrl-C at the prompt cancels the line; a second consecutive Ctrl-C quits (counter resets on any input). Ctrl-C during an in-flight chat request cancels the request and counts as the first idle Ctrl-C (a second consecutive one quits). Ctrl-C at an attended gate prompt is handled by the driver/run() semantics (D-6) and does not touch the counter. Ctrl-C at a confirmation prompt declines it. | R-7; AR-022 |
| D-8 | Exit code comes solely from the most recent executed build-or-refusal event: a build gives its own exit code (130 if stopped by Ctrl-C), a refused action or line gives 2; with no such event the code is 0. Chat and slash lines that are not refusals never reset or change it. /quit and EOF return that code; SIGTERM exits 143. | R-9; a single last-event rule resolves refusal-after-failed-build and the reverse, and interleaved chat/slash lines never alter the code |
| D-9 | `ISSUE_REQUEST_RE` moves to `home_actions.py`; `uncle_tui.py` imports it (one-line edit) so `uncle_tui.ISSUE_REQUEST_RE` remains a valid name bound to the very same compiled object (`uncle_tui.ISSUE_REQUEST_RE is home_actions.ISSUE_REQUEST_RE`) | Avoids copying TUI logic without breaking existing references to the TUI name |
| D-10 | `/triage` and `/do` map to the same stage-rerun/resume executor entries; where TUI triage state is required they print that this needs the TUI. Slash edge rules: lines starting with `/` are never sent to chat; an unknown command, bad argument (e.g. invalid `/mode` value, non-numeric `/issue`) or extra arguments print exactly one usage line and change no state; `/stop` with no build running prints `no build running`; `/resume` with nothing to resume prints a notice; `/mode` with no argument prints the current mode. `repl_actions.execute` accepts only allowlisted action types (run, runstage, stop, resume, clear) and re-validates every field via `home_actions.parse_reply` (integer issue N, stage name from the fixed stage set, paths resolving inside the project root); anything else is refused with exit 2 and no driver started. | Bounded scope; deterministic behavior in odd states; model-supplied fields are never trusted (AR-012) |
| D-11 | Existing-brief replacement: ask on same input; yes archives under `.uncle/brief-history`. Confirmation rule for every REPL confirmation (replacement and quit): only `y`/`yes` (case-insensitive, trimmed) consents; blank, any other text, EOF or Ctrl-C declines. Confirmations are read only from user-typed input on stdin, never model output, so the model cannot self-approve. Quit confirmation is asked only on an attended tty while a build runs; on non-tty input or unattended there is no prompt, and EOF during it quits and stops the build (I-4 holds). | SB-16, SB-7; AR-003; AR-022; confirmations cannot be self-approved by the model |
| D-12 | `/date` omitted; `/settings` read-only | Does not exist in TUI |

## 5. Components not to modify
`scripts/stagegate.sh`, `change-workflow.sh`, `from-issue.sh`, gate libs, `supervisor_chat.py`, `supervisor_runner.py`, `home_agent_session.py`, `run_duties.py`, `process_tree.py`, TUI behavior beyond the import line.

## 6-9. Data flow, state, interface
Input line -> slash dispatch or ISSUE_REQUEST_RE or chat adapter -> reply text and optional home action -> `repl_actions.execute` -> `prepare_driver` -> `uncle_headless.run` (filtered output). Session state: history list, mode, idle-Ctrl-C counter. No persistence added; build state files unchanged. Interfaces: `uncle_repl.main(argv, env, io)`, `repl_actions.execute(action, ctx)`, `uncle_headless.prepare_driver(action, text, root, runtime, issue_mode, err)`.

## 10. Compatibility

One-shot path calls the same logic through `_driver_from_env`, which keeps its exact existing signature and becomes a thin wrapper over `prepare_driver`. For every existing failure path (e.g. invalid action, missing runtime, bad issue mode, attended with non-tty stdin) the wrapper emits byte-identical stderr and the same exit code as before the extraction. A test in `headless-equivalence-test.py` captures stderr and exit code for each such path from the pre-change behavior and asserts equality; success-path output and exit codes are also unchanged.

Output filtering: all REPL stdout/stderr text, including chat replies, runner errors, issue titles and exception messages as well as build output, passes through EscapeFilter, which strips control bytes except newline and tab, and CSI/OSC sequences. The one-shot path's existing filtering is unchanged.

## 11. Concurrency

One build at a time; REPL blocks in `run()`. Chat adapter runs synchronously with cancellation on Ctrl-C and launches the chat runner in its own process group. Ctrl-C during an in-flight chat reply cancels that request and counts as one idle Ctrl-C press (D-7). Ctrl-C during a build or at an attended gate is handled by run()/driver semantics (D-6) and does not change the idle counter; Ctrl-C at a confirmation prompt declines it. The session SIGTERM handler terminates both the active chat runner subprocess group and the active build process group, then exits 143; no child of either kind may remain (covered by the process inventory test). Handler discipline: the REPL saves the current SIGTERM (and SIGINT) handler immediately before each `run()` call and restores it in a `finally` immediately after, so `run()`'s own handler installation never replaces the session handler permanently; `run()` must leave no changed signal handler or process-group state behind on return, including when it raises. A test asserts `signal.getsignal` values before and after a build (normal, failed and Ctrl-C-stopped) are identical.

## 12. Error and recovery
Every action/chat exception is caught per line, printed once, and the loop continues; fatal only on EOF/quit.

## 14. Rollback plan
Revert the `uncle` bare-noui branch to the previous refusal and restore the two launcher test rows; revert `ISSUE_REQUEST_RE` import. New files can remain unreferenced.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST I-1 | I-1 | No curses | REPL imports no curses/uncle_tui; import test | Spec | CAP-PY | CODING |
| R-7 | USER | AR-014; CHANGE_REQUEST I-1 | I-1, SB-2 | All REPL output escape-filtered | Every REPL write to stdout/stderr (chat replies, runner errors, issue titles, exception messages, build output) goes through one EscapeFilter-backed writer; repl_chat has no direct output; test feeds ESC/CSI/OSC/control bytes via fake runner, issue title and exception and byte-scans output | Untrusted model/issue text must not inject terminal control sequences | CAP-PY | CODING |
| R-2 | USER | CHANGE_REQUEST I-2 | I-2 | Actions only via validated path | single `repl_actions.execute` using `parse_reply`; action-type allowlist; field re-validation (integer issue N, fixed stage set, paths inside project root); refusal returns exit 2 before `prepare_driver` is called; test with defect injection (non-integer issue, unknown stage, path escaping root, unknown action type) asserts no driver started | Spec | CAP-PY | CODING |
| R-3 | USER | CHANGE_REQUEST I-4 | I-4 | No orphan child | reuse `run()` killpg for the build group; session SIGTERM handler also kills the chat runner subprocess group, then exits 143 | Existing mechanism | CAP-PY | CODING |
| R-4 | REPOSITORY | CLAUDE.md | AC-10 | Tests not weakened | Only launcher-noui-test.sh rows that assert bare `--noui`/`UNCLE_NOUI=1` refusal are replaced (identified by content, not row number), justified by request N-6; every other row, including bare `--noui` with any unrecognized argument, stays unchanged and passing. | Authority from request | CAP-SH | CODING |
| R-5 | PLATFORM | pty availability | AC-5, AC-6 | pty tests | Python `pty` module on darwin/linux; probe: `python3 -c 'import pty'` (inspected stdlib) | Real tty needed | CAP-PTY | CODING |
| R-6 | DESIGN | D-5 | SB-2 | No streaming | print per reply | Revisable | CAP-PY | CODING |

CAP-PY = python3; CAP-SH = bash; CAP-PTY = python pty. Fake runner/driver used in all automated tests; real-runner `ssh` manual check is LIVE_VERIFICATION (needs authenticated runner; not a coding prerequisite).

## 16-17. Automated and regression test strategy

Commands: `bash scripts/run-shell-tests.sh`, `bash scripts/run-python-tests.sh` (from baseline). New: `scripts/tests/repl-session-test.py` (pipe sessions, executor, I-2 with defect injection, I-6, import check), `scripts/tests/repl-pty-test.py` (banner, Ctrl-C, gate, byte scan, orphan check), `scripts/tests/launcher-repl-test.sh` rows (or additions in launcher-noui-test.sh), and an extension of `headless-equivalence-test.py`. Regression: existing headless, home-actions, tui-home-agent suites must stay green (D-9 import); a test asserts `uncle_tui.ISSUE_REQUEST_RE is home_actions.ISSUE_REQUEST_RE` so the TUI name stays valid.

- Exit-code matrix (parametrized, repl-session-test): failed build then chat, refusal then build, build then refusal, Ctrl-C-stopped build then EOF (130), SIGTERM (143); code always from the last build-or-refusal event.
- Over-long line cases: exactly 1048576 bytes accepted, 1048577 discarded through newline with the next line run, chunk-split lines, oversize unterminated final line at EOF; unterminated normal final line processed.
- Confirmation answers (replacement and quit): y, YES, blank, junk, EOF, Ctrl-C; only y/yes consents.
- Startup mode: both env vars set gives attended, neither set gives attended, --attended flag honored.
- Escape byte-scan: fake runner emitting CSI/OSC/control bytes in replies, errors, issue titles and exceptions; stdout and stderr contain none except newline and tab.
- Executor refusals: non-allowlisted type, non-integer issue, unknown stage, out-of-root path; each exit 2 with fake driver never started, plus a defect-injection variant bypassing parse_reply that must fail.
- headless-equivalence-test.py: one case per existing _driver_from_env failure path asserting byte-identical stderr and exit code against pre-change expectations.
- Signal state: signal.getsignal for SIGTERM and SIGINT identical before and after run() (normal, failed, Ctrl-C-stopped).

## 18. Manual verification
Real session over `ssh` without and with a pty: chat, start a small build, answer a gate, quit (LIVE_VERIFICATION).

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle` | Bare --noui execs REPL; usage text | SB-1 | Launcher arg handling | launcher tests |
| `scripts/lib/uncle_repl.py` | New loop, banner, slash commands, I/O | SB-1..16 | New code | repl-session/pty tests |
| `scripts/lib/repl_actions.py` | New validated action executor | I-2 | New code | repl-session-test |
| `scripts/lib/repl_chat.py` | Sync chat adapter | SB-2, SB-3 | Runner API binding | repl-session-test fake runner |
| `scripts/lib/uncle_headless.py` | Extract `prepare_driver`; no behavior change | I-3 | One-shot regression | headless-run/equivalence tests |
| `scripts/lib/home_actions.py` | Host `ISSUE_REQUEST_RE` | D-9 | TUI regex use | home-actions, tui-home-agent tests; identity assertion with uncle_tui.ISSUE_REQUEST_RE |
| `uncle_tui.py` | Import `ISSUE_REQUEST_RE` from home_actions; the name stays bound in `uncle_tui` to the same compiled object | D-9 | TUI startup | tui-home-agent-test; identity assertion `uncle_tui.ISSUE_REQUEST_RE is home_actions.ISSUE_REQUEST_RE` |
| `scripts/tests/launcher-noui-test.sh` | Replace bare-refusal rows (13-14) | N-6 changed | Test weakening risk | itself |
| `scripts/tests/repl-session-test.py`, `repl-pty-test.py`, `headless-equivalence-test.py` | New/extended tests | AC-2..9 | None | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| Bare `--noui`, `UNCLE_NOUI=1` and `--noinput` start the REPL. Bare `--noui` with any unrecognized argument keeps its current error message and exit code (tested). | SB-1, SB-11, SB-12 | I-1 | uncle | launcher-noui-test.sh | ssh session |
| AC-2 | SB-2, SB-3 | I-6 | repl_chat, uncle_repl | repl-session-test | ssh session |
| AC-3 | SB-4, SB-5, SB-16 | I-2 | repl_actions | repl-session-test + defect injection | ssh session |
| AC-4: piped runs print plain lines without prompt decoration. Exit code comes solely from the last executed build-or-refusal action (build = its own code, Ctrl-C-stopped build = 130, refused = 2, none executed = 0); chat and slash lines never change it. /quit and EOF return it; SIGTERM exits 143. A line over 1 MiB (1048576 bytes) is discarded through its terminating newline (or EOF), exactly one error is printed to stderr, the remainder is never run as a command or gate answer, it counts as a refused action (exit 2 if it is the last executed action), and the session continues. | SB-10, SB-13 | I-1 | uncle_repl | repl-session-test, repl-session-test (exact stdout: banner present, no prompt when piped; replies/progress on stdout, errors on stderr), repl-session-test (incl. over-long line: one error, remainder not executed, exit 2, session continues, both pipe reader and tty reader), repl-session-test: piped input with a build mid-stream — lines after the build are processed in order, none dropped or consumed by an unattended driver | piped run |
| AC-5 | SB-7, SB-8, SB-9 | I-1, I-4 | uncle_repl | repl-pty-test (incl. Ctrl-C during in-flight chat counts as one idle press, Ctrl-C at gate follows run() semantics, Ctrl-C at replacement confirmation declines) | ssh with pty |
| AC-6: gates and confirmations are answered only by user input, never by model output; an attended gate consumes exactly one user-typed line; EOF at a gate declines/stops and never approves; unattended builds consume no lines; lines typed during a build are never dropped and remaining lines run in order as prompts after the build returns (tested with a model reply containing 'yes' and with piped EOF). | SB-6 | I-5 | uncle_repl, headless.run | repl-pty-test, repl-session-test: piped lines supplied during an attended build — exactly one consumed per gate, remaining lines run in order as prompts after run() returns; unattended build consumes none | answer a gate |
| AC-7 | SB-7 | I-4 | uncle_repl | repl-pty-test, repl-session-test, process inventory test: SIGTERM during an in-flight chat request and during a build leaves no chat runner or build child, exit 143 | quit mid-build |
| AC-8 | SB-4 | I-3 | prepare_driver | headless-equivalence-test | n/a |
| AC-9: Lines starting with `/` are never sent to chat. An unknown slash command prints an unknown-command message plus usage and counts as a refused action (exit 2). `/stop` with no build running prints 'no build running' and `/resume` with nothing to resume prints a notice; neither changes the exit code. `/mode` with no argument prints the current mode. An invalid `/mode` value, a non-numeric `/issue`, or extra arguments print one usage line with no state change. | SB-14, SB-15 | n/a | uncle_repl | repl-session-test: unknown command refused with exit 2 and never reaches the chat adapter; /stop with no build prints 'no build running' and /resume with nothing to resume prints a notice, both leaving the exit code unchanged; /mode with no argument prints the current mode; invalid /mode value, non-numeric /issue, and extra args each print one usage line and leave state unchanged | /help |
| AC-10 | SB-12 | EI-1..5 | all | both runners | n/a |

## Implementation sequence

1. Extract `prepare_driver` from `_driver_from_env`; keep `_driver_from_env` with its exact signature as a wrapper, preserving byte-identical stderr and exit codes for every existing failure path (capture pre-change expectations before refactoring). Move `ISSUE_REQUEST_RE` to `home_actions.py` and import it in the TUI.
   Owns: `scripts/lib/uncle_headless.py`, `scripts/lib/home_actions.py`, `uncle_tui.py`
2. Action executor accepting only allowlisted action types (run, runstage, stop, resume, clear); re-validates fields via parse_reply (integer issue, fixed stage set, paths inside project root); refuses anything else with exit 2 before prepare_driver is called; replacement confirmation read only from user input (y/yes consents, everything else declines).
   Owns: `scripts/lib/repl_actions.py`
   Depends on: 1
3. Chat adapter over home agent / supervisor request path (independent file; binds API at implementation). Launches the chat runner in its own process group and exposes a cancel/terminate function that kills that group, for use by the session SIGTERM handler and Ctrl-C cancellation. Does no direct output.
   Owns: `scripts/lib/repl_chat.py`
4. REPL loop: banner, line reader (1048576-byte bound, discard-through-newline), slash commands, Ctrl-C and exit code policy (D-6/D-7/D-8), EscapeFilter-backed output writer. Owns signal discipline: saves the SIGTERM/SIGINT handlers before each run() and restores them after (run() itself is not edited beyond step 1); the SIGTERM handler calls the chat adapter terminate function and kills the build group, then exits 143.
   Owns: `scripts/lib/uncle_repl.py`
   Depends on: 2, 3
5. Launcher: replace bare-refusal with exec of REPL; usage text.
   Owns: `uncle`
   Depends on: 4
6. Tests: session, pty, equivalence extension; in launcher-noui-test.sh replace only the rows that assert bare-refusal (selected by content) and add rows proving bare `--noui` plus an unrecognized argument still yields the current error and exit code; defect-injection evidence.
   Owns: `scripts/tests/repl-session-test.py`, `scripts/tests/repl-pty-test.py`, `scripts/tests/headless-equivalence-test.py`, `scripts/tests/launcher-noui-test.sh`
   Depends on: 4, 5

## 21. Scope cuts under time pressure
Cut first: `/triage` and `/do` plain-text mapping (print TUI-needed message), `/settings` print, readline editing, then replacement confirmation (decline instead). Never cut: I-1..I-5 tests, launcher change, Ctrl-C semantics.

## 22. Risks and unresolved questions

- Chat adapter binding to HomeAgentSession/SupervisorRequest threads: bound at step 3; fake-runner test proves it; fallback is the ChatRequest path.
- stdin sharing with attended gates: mitigated by D-2/D-3 (REPL reads no stdin during a build; one line per attended gate; unattended never reads fd 0; unread lines run in order as prompts afterward; the 1048576-byte line bound and EOF-declines rule apply) and by the pty gate test plus a piped-lines-order test. Gate and replacement confirmations are read only from user input, never model output, and EOF declines (tested in repl-session-test and repl-pty-test).
- Extracting the regex touches `uncle_tui.py`: one import line, covered by tui-home-agent tests.
- No blocking planning decisions remain.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | D-3 and SB-6 conflicted: non-gate lines and unattended/piped lines had no stated consumer; a single explicit stdin ownership rule resolves it. | Rewrote D-3 with the stdin ownership rule, updated AC-6 and the s18.1.i2 risk text to match. |
| AR-002 | Accepted | The exit-code policy was ambiguous across interleaved builds, refusals, chat/slash lines, 130 and 143. | D-6 and D-8 rewritten with one exit-code rule; AC-4 requirement updated to match. |
| AR-003 | Accepted | Confirmation prompts were unspecified for non-tty, blank, unrecognized, EOF and Ctrl-C input; a single consent rule is needed and must not conflict with I-4. | Edit D-11 to define the consent rule and add the quit-confirmation rule (attended tty only; EOF quits and stops the build). |
| AR-004 | Accepted | Over-long line handling was unspecified; a defined discard-through-newline rule and refusal classification make the two readers agree. | AC-4 traceability row (s15.1) now requires tests that a line over 1 MiB is discarded through its newline, prints one error, counts as refused (exit 2), and the session continues. |
| AR-005 | Accepted | Slash-command edge states were unspecified; the stated rules are consistent with D-8 and the TUI behavior. | AC-9 row requirement now states slash routing, unknown-command refusal, empty /stop and /resume notices and /mode with no argument. |
| AR-006 | Accepted | Ctrl-C during chat and at a gate was undefined against the D-7 counter; defining it is cheap and removes ambiguity. | D-7 now defines Ctrl-C in flight during chat (cancels, counts as first idle press) and at a gate (driver handles it, counter untouched); concurrency text agrees. |
| AR-007 | Accepted | The plan did not state that the _driver_from_env wrapper preserves its signature and failure output; the one-shot path must stay byte-identical. | Edited s7.1 (Compatibility) and step-1 to pin the wrapper signature and add byte-identical stderr/exit-code tests for each existing failure path. |
| AR-008 | Accepted | Row scope was ambiguous and other bare --noui combinations were unspecified; pinning them prevents test weakening and launcher regressions. | Edited R-4, AC-1 and step-6: replace only rows asserting bare refusal; any bare --noui with an unrecognized argument keeps its current error and exit code, with tests. |
| AR-009 | Accepted | Existing code or tests may reference uncle_tui.ISSUE_REQUEST_RE; keeping the name bound to the same compiled object avoids breakage. | D-9 now requires uncle_tui.ISSUE_REQUEST_RE to remain bound to the same object; r6/r7 and s12.1 gain matching coverage. |
| AR-010 | Accepted | Interplay between the session SIGTERM handler and run()'s own handler was unspecified; save/restore makes it deterministic. | Section 11 (s8.1) states save-before/restore-after of the SIGTERM handler around each run() and no leaked handler or process-group state; D-6 notes the same. |
| AR-011 | Accepted | The exit-code rule collided across interleaved refusals, builds and chat; one deterministic rule removes the ambiguity. | D-8 rewritten: exit code comes solely from the last executed build-or-refusal action; chat and slash lines never change it; AC-4 requirement states this. |
| AR-012 | Accepted | The plan did not constrain model-supplied action fields; an allowlist plus re-validation is needed to keep I-2 meaningful. | Edit D-10 and R-2, and add a field-constraint paragraph to s6.1, so execute allowlists action types and re-validates fields via parse_reply. |
| AR-013 | Accepted | Real gap: plan did not say who may answer gate or replacement prompts; piped 'yes' lines or model output must not auto-approve. | Edit D-3 and D-11 to read confirmations only from user input, EOF declines; AC-6 requirement and s18.1.i2 risk updated to match. |
| AR-014 | Accepted | Escape filtering was stated only for build output; chat replies, runner errors, titles and exceptions could emit raw control sequences to the terminal. | Added restriction R-7 and rule in s7 requiring all REPL stdout/stderr text to pass through EscapeFilter (strips control bytes except newline/tab, plus CSI/OSC). |
| AR-015 | Accepted | The 1 MiB line bound had no defined overflow behavior on the os.read reader; a leftover tail could run as a command or gate answer. | D-2 now defines overflow: discard through next newline or EOF, one 'line too long' error, remainder never run as command or gate answer. |
| AR-016 | Accepted | SIGTERM handling must also terminate the chat runner subprocess group or AC-7/I-4 can leave an orphan. | Edit s8.1 (Concurrency), R-3 mechanism, and AC-7 tests to cover chat runner group plus build group, exit 143, process inventory test. |
| AR-017 | Accepted | D-4 named the flag and env vars without precedence or default; the finding's rule is clear and cheap to state. | D-4 now states attended wins when both env vars are set and attended is the default when neither is set. |
| AR-018 | Accepted | D-3 and SB-6 conflicted; settling that no input is read during a build and unread lines run as normal prompts afterwards removes the ambiguity. | Rewrote D-3, extended AC-6 and AC-4 tests/behaviors, and reworded the stdin-sharing risk s18.1.i2. |
| AR-019 | Accepted | D-6/D-8 left interleaving of refusals, builds, chat lines and 130/143 ambiguous; one rule keyed to the most recent build-or-refusal event settles it. | Rewrote D-6 and D-8 and aligned AC-4 requirement text in the decisions and traceability tables. |
| AR-020 | Accepted | Slash-command behavior in odd states and with bad arguments was unspecified; a single rule makes the tests deterministic. | Extend D-10 with slash-command edge rules and update AC-9 requirement and tests to cover them. |
| AR-021 | Accepted | Over-long line and EOF edge cases were undefined; the proposed rule is bounded and consistent with decline-on-EOF. | D-2 now defines the 1048576-byte overflow, unterminated final line, and EOF at a gate or confirmation; s18.1.i2 cites it. |
| AR-022 | Accepted | Ctrl-C during chat, gate prompt and replacement confirmation was undefined; the settled rule is consistent with R-7/R-8 and run() semantics. | Updated D-7 and D-11, added concurrency text in s8.1, and extended AC-5 invariants/tests to cover Ctrl-C in chat, gate and confirmation. |
| AR-023 | Accepted | Banner and stream routing for piped runs was unspecified, leaving exact-stdout tests underdetermined. | D-1 now fixes banner, prompt, reply/progress and error routing; AC-4 row names the stream-routing test. |
