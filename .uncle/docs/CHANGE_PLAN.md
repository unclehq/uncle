# Change plan (issue 145)

Seeded from [unclehq/uncle#145](https://github.com/unclehq/uncle/issues/145).

Issue 145

Omitted sections: Schema/persistence (only untracked runtime files); Migration (none); Concurrency (single daemon thread, as CompletionPreview); Feature flag beyond env opt-out (see 15)

## 1. Selected technical approach

New pure-ish module `scripts/lib/desktop_launch.py` with: `detect(root)` -> {framework, command|None, candidates}; `headless_reason(env, platform)`; `launch_decision(attended, unattended, headless, opted_out)`; `DesktopLaunch` class (Popen with `group_options`, log file, pid file, grace-period watcher, `close()`). `uncle_tui.py` calls it from `_offer_support` for BOTH families when desktop is detected. Opt-out: with `WORKFLOW_PREVIEW_DESKTOP=0` the desktop flow is bypassed before any detection, so nothing is detected, written or printed, and the web `CompletionPreview` and unattended `_show_early_preview` run exactly as before, even for Electron/Tauri projects. Prompt eligibility: the attended y/n `prompt_kind='desktop'` gate is shown ONLY when detection yields a single resolved command, the environment is not headless, and no live pid file exists. Otherwise no prompt is shown: for ambiguous detection print the candidates, for headless print the headless reason, for a live pid file print the already-running message; each case records `.uncle/workflow/desktop-launch.json` with status skipped and its reason, then the flow continues to `_completion_dialog`. Unattended -> print the command to history and record `.uncle/workflow/desktop-launch.json`, then continue the existing quit path. Web-preview suppression rule (D-7): when the desktop flow is enabled and a desktop project is detected, the web `CompletionPreview` and unattended `_show_early_preview` are suppressed whatever the outcome (launched, declined, skipped, ambiguous, headless, unattended or failed). Only the opt-out case keeps the web preview.

- Opt-out rule (AR-021): when `WORKFLOW_PREVIEW_DESKTOP` is a disabled value (`0`, `false`, `no`, `off`), `desktop_launch.detect` is never called, no `.uncle/workflow/desktop-*` file is written, nothing is printed to history, and the web `CompletionPreview` and `_show_early_preview` run unchanged. This is a strict no-op for the desktop flow.
- Precedence in `launch_decision`: opted_out, then unattended, then headless, then attended-confirm. The first signal that holds wins and short-circuits the rest; each skip records only its own reason (`opted-out`, `unattended`, `headless`). Only when none holds does the attended y/n prompt appear. Unattended and headless signals are not merged, so with both true the recorded reason is `unattended`. With opted_out and any other signal true, the outcome is the opt-out no-op above.
- launch.json interaction: when desktop is detected and the flow is enabled, the `launch.json` kind (webpage/command) is not used to drive the preview for that run. `.uncle/launch.json` is never modified by the desktop flow and is still read and validated by the existing code, so an invalid file reports the same error as before. Which previews are suppressed for each desktop outcome is decided under AR-008. With the flow disabled or no desktop detected, launch.json behaves exactly as today.

## 2. Alternatives considered
- Extend `CompletionPreview`/launch.json with a `desktop` kind: rejected, changes a public contract and mixes confirm-gating into web flow.
- Shell hook in change-workflow.sh: rejected, driver has no TTY/dialog and the launch must live with the TUI cleanup.
- Extend preview-build.sh early preview: deferred (request says end of build).

## 3. Why preferred
Isolated module is unit-testable without curses; minimal TUI edit; web path untouched.

## 4. Decisions (settled)

| ID | Decision | Reason |
|---|---|---|
| DEC-1 | Electron: dep/devDep `electron`, `electron-builder`, `@electron-forge/cli`; Tauri: `src-tauri/tauri.conf.json` or `@tauri-apps/cli` dep | request examples; an unreadable or invalid-JSON package.json yields framework none (no launch, no error). |
| DEC-2 | Command: config override; else Electron `npm start` if only `start`, `npm run dev` if only `dev`; both -> ambiguous; neither + `main` + node_modules/.bin/electron -> `[node_modules/.bin/electron, .]`; Tauri `npm run tauri dev` if scripts.tauri else ambiguous (candidate `cargo tauri dev`) | never guess between candidates; the attended desktop prompt shows the full resolved argv, warns that project-defined scripts run with the user's privileges, and defaults to No (only an explicit y launches; Enter declines); an invalid or empty launch_command override is ignored with a one-line warning and detection falls back to the guessing rules. |
| DEC-3 | Both frameworks detected -> ambiguous | safe default |
| DEC-4 | Headless: Linux without DISPLAY/WAYLAND_DISPLAY; `CI` non-empty; `SSH_CONNECTION`/`SSH_TTY` set (any OS). `launch_decision` precedence is opted_out > unattended > headless > attended-confirm: headless is evaluated after opt-out and unattended, and any positive headless signal wins over attended state. A headless environment never shows the desktop prompt; the launch is skipped, the reason is printed, and the skip records only its own reason `headless` (status skipped). | D-4; precedence resolves overlap with unattended (AR-002) |
| DEC-5 | Unattended is true if ANY signal holds: TUI `workflow_unattended`, `WORKFLOW_UNATTENDED=1`, or `not sys.stdin.isatty()`. Any positive unattended signal wins over the TUI's attended state and over headless; the TUI's own attended state never overrides a positive signal. `launch_decision` order is opted_out, then unattended, then headless, then attended-confirm prompt. An unattended skip records only reason `unattended`, even when headless also holds. The desktop y/n prompt reads keys only from the TUI's own TTY/curses input, never from piped stdin. Existing suites run with WORKFLOW_PREVIEW_DESKTOP=0 or non-desktop fixtures so the attended `_offer_support` path is unchanged. | D-3; explicit precedence so overlapping signals (e.g. attended TUI with no stdin TTY, or over SSH) give one deterministic outcome (AR-002); AR-009: existing tests and piped usage keep their current behavior via opt-out/non-desktop fixtures |
| DEC-6 | Grace 3 s default via `WORKFLOW_PREVIEW_DESKTOP_GRACE`; process still alive after grace = success reported; ANY exit within grace, including exit code 0, = failed, reported with exit code and the log tail (pid file removed). Non-numeric or negative grace uses 3 s; 0 checks exit status immediately once (an exit at that check is failed, still alive = success). | D-2; an immediate clean exit means no window stayed open, so it is not a successful launch; defined results for invalid grace values. |
| DEC-7 | Files: `.uncle/workflow/desktop-app.pid` (JSON pid/command/log/started), `desktop-app.log`, `desktop-launch.json` (status launched/failed/skipped/declined + reason). All three are created with mode 0600 (os.open with 0o600, not widened by umask) and remain untracked. | invariant I-3; all untracked; app output and commands may be sensitive, so owner-only access |
| DEC-8 | Cleanup on stop_workflow/_quit kills only the process tree of this session's own Popen handle (via process_tree.kill_tree); a PID read only from the pid file is NEVER signalled. Pid-file liveness: a pid file is live only if its PID is alive (os.kill(pid, 0) succeeds) AND the recorded `command` field matches that PID's actual command. A dead PID, mismatched command (PID reuse) or unparseable/corrupt pid file is stale and is overwritten. A live pid file (app still running) blocks relaunch and never shows the desktop prompt: the TUI prints a 'desktop app already running (pid N)' message, records desktop-launch.json status `skipped` with reason `already running`, and the flow continues to `_completion_dialog`. Starting a new workflow run from the TUI does not kill a still-running desktop app; the next run's end-of-build flow applies the same live-pid rule. | no silent orphan from this session; PID reuse must never cause killing an unrelated process; no duplicate launch; flow never blocks; testable liveness rule (AR-019) |
| DEC-9 | Config key `desktop.launch_command` parsed with `shlex.split` from `.uncle/config`. `.uncle/config` is project-local and may be repo-controlled, so the command is untrusted: it is shown in full (resolved argv) in the confirmation prompt and never launches without explicit attended confirmation (same gate as detected commands; unattended/headless skip still applies and only prints it). It is never treated as pre-trusted. An empty or unparsable value (shlex error, or no tokens) is ignored with a one-line warning and detection falls back to the DEC-2 command guess. The override applies only when a desktop framework is detected; on a non-desktop project it is never read or applied. | prefer explicit setting, but not trusted as operator-authored (AR-013); invalid or irrelevant values have defined behavior and never block or crash the flow. |

## 5. Components not to modify
preview-build.sh, preview_server.py, preview_kind.py, completion_preview.py (launch.json contract), bash drivers, process_tree.py (reused as-is), test-report writers.

## 6. Data flow
workflow exit 0 -> `_offer_support` -> `desktop_launch.detect` -> `launch_decision` -> {print+record | prompt -> `DesktopLaunch.start`} -> events into `home_history`.

## 7. State transitions

New `prompt_kind='desktop'` (confirm/decline) before the existing support/finished dialog; after answer, flow continues to `_completion_dialog`. If a live desktop pid already exists (DEC-8), the prompt is not entered: a message is printed, `skipped` is recorded, and the flow goes straight to `_completion_dialog`. Key handling while the prompt is open: `y`/`Y` launches; `n`/`N`, Esc and Enter decline and record `declined`; all other keys are ignored (prompt stays open); resize redraws the prompt without changing state. Quit/stop of the TUI while the prompt is open counts as decline (nothing launched, `declined` recorded) and then proceeds through the normal quit path. The prompt reads keys only from the TUI's own input loop. `_offer_support` is idempotent per workflow run: a guard flag set on first entry makes a duplicate workflow-exit event a no-op, so no second prompt, launch or record is produced.

## 8. Interfaces

Env `WORKFLOW_PREVIEW_DESKTOP` (opt-out), `WORKFLOW_PREVIEW_DESKTOP_GRACE`; config `desktop.launch_command`. Disabled values (case-insensitive, whitespace-trimmed): `0`, `false`, `no`, `off`; unset, empty or any other value leaves the flow enabled. With the flow disabled, nothing is detected, written or printed, no prompt is shown, and the web preview and early preview behave exactly as before, even for Electron/Tauri projects. The launch.json file format and contract are unchanged: the desktop flow never writes it, and still validates it. When the desktop flow applies, its `kind` is ignored for the preview.

## 10. Compatibility

Non-desktop projects take no new code path beyond a cheap detect that returns none (D-6). A `desktop.launch_command` in `.uncle/config` does not bypass the confirmation gate.

## 12. Error and recovery

OSError on spawn -> failed status with message; any exit within grace -> exit code + last 20 log lines, pid file removed; a crash after the grace period is reported only while the TUI is open (no reporting after TUI exit); the log tail is stripped of ANSI/CSI/OSC escape sequences and control characters (except newline and tab) before any display in the TUI history or record file; all paths non-blocking.

## 14. Rollback plan
Revert commit, or set `WORKFLOW_PREVIEW_DESKTOP=0`. Remove untracked `.uncle/workflow/desktop-*` files if desired; nothing else persisted.

## 15. Containment
Env opt-out; default-safe (confirmation / never unattended).

## 16. Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Invariants | I-2, D-3 | No unattended/unconfirmed launch | `launch_decision` pure gate + TUI prompt that displays the resolved argv, warns that project scripts run with the user's privileges, and defaults to No | testable matrix | CAP-PY | uncle_tui.py:2250 unattended branch inspected | CODING |
| R-2 | USER | CHANGE_REQUEST Invariants | I-3, D-9 | Tracked pid file, no silent orphan, no kill of reused pid | pid file + close hooks at uncle_tui.py 2917, 7387; close() acts only on the in-memory Popen handle of this session, never on a pid read from the file | same as web | CAP-PY | process_tree.kill_tree exists (line 279) | CODING |
| R-3 | USER | CHANGE_REQUEST Invariants | I-4 | Working tree untouched | write only under .uncle/workflow (gitignored via .uncle/*) | .gitignore inspected | CAP-PY | .gitignore lines 1-6 | CODING |
| R-4 | REPOSITORY | CLAUDE.md | I-1 | No test report row | module imports no report writers | boundary | CAP-PY | grep | CODING |
| R-5 | PLATFORM | GUI | D-2 live | Real Electron window opens | manual check only | no GUI automation in scope | CAP-GUI | not available here | LIVE_VERIFICATION |

Runner binding: Python `unittest` via `bash scripts/run-python-tests.sh` (collects `scripts/tests/*-test.py`).

## 17. Automated-test strategy

New `scripts/tests/desktop-launch-test.py` (detection fixtures in tmp dirs, decision matrix, config override, stub launch/crash/cleanup, git-status unchanged) and `scripts/tests/tui-desktop-launch-test.py` (TUI hook with stub, following tui-complete-dialog-test.py patterns). Stub command is a `python3 -c` sleep/exit argv. No real GUI. Regression: existing completion-preview, tui-complete-dialog, tui-support suites must pass unchanged, run with stdin non-TTY and with WORKFLOW_PREVIEW_DESKTOP=0 or on non-desktop fixtures; verification commands are those in the baseline. Added test cases: (a) launch_decision parametrized over all 16 combinations of opted_out/unattended/headless/attended asserting outcome and recorded reason under precedence opted_out > unattended > headless > attended-confirm. (b) Child exits 0 within grace -> failed with log tail, alongside non-zero exit and alive-past-grace. (c) Pid file: dead pid overwritten; live pid with matching command blocks and records skipped/already running; live pid with mismatched command stale; unparseable file stale. (d) close() with a pid file naming an unrelated live sleeper and an instance that never started leaves the sleeper alive; close() terminates the child it started. (e) os.stat mode 0600 on pid, log and record files; stub emitting ANSI/control bytes yields a displayed tail free of them. (f) Invalid package.json -> none; empty/unparsable launch_command -> warning and guessing; grace invalid/negative -> 3 s, 0 -> immediate check. (g) TUI: desktop prompt text contains full resolved argv and the privilege warning, Enter declines; keys y launches, n/Esc/Enter/quit record declined with no spawn, unrelated keys leave prompt open; config-supplied launch_command shown in full, never spawned without y in attended or unattended runs. (h) TUI with Electron fixture plus valid web launch.json: launch.json bytes unchanged; web/early preview behavior asserted for launched, declined, ambiguous, headless, unattended, opted-out outcomes per the D-7 rule. (i) Each disabled value (0/false/no/off) on an Electron fixture: no `.uncle/workflow/desktop-*` files, no history lines, web preview still invoked. (j) TUI attended state outranks isatty; non-desktop fixtures never reach the desktop path.

## 18. Manual verification
Build a minimal Electron app and confirm the window opens, PID/log printed, and window closes on cleanup (CAP-GUI, LIVE_VERIFICATION). Not PASS-able by automation.

## 19. Observability
History lines: framework, command, PID, log path, skip/failure reason; `desktop-launch.json` status record.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| scripts/lib/desktop_launch.py | New module | detection, gating, launch, cleanup | Low (isolated) | desktop-launch-test.py |
| uncle_tui.py | Hook in `_offer_support`, `_poll_completion_preview`, prompt handling, close paths | integrate offer/launch/cleanup | Medium (dialog sequencing) | tui-desktop-launch-test.py, tui-complete-dialog-test.py (run with WORKFLOW_PREVIEW_DESKTOP=0 or on non-desktop fixtures so the desktop flow cannot alter them) |
| scripts/tests/desktop-launch-test.py | New | AC-1..AC-9 | None | self |
| scripts/tests/tui-desktop-launch-test.py | New | TUI behavior | None | self |
| scripts/README.md | Document env/config | operator discovery | None | none |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1,AC-2 | D-1, D-8 | I-5 | desktop_launch.py | desktop-launch-test.py (includes: config-supplied command is shown in full in the prompt and never launches without confirmation) | Electron fixture |
| AC-1,AC-2 edge inputs (AR-022) | D-1, D-2, D-8 | I-5 | desktop_launch.py | desktop-launch-test.py: malformed package.json -> none; empty/unparsable launch_command -> warning + guessing; grace invalid/negative -> 3 s; grace 0 -> immediate check | none |
| AC-3,AC-4 (prompt shown only for a single detected command, non-headless, no live pid file; ambiguous/headless/live-pid print reason or candidates, record skipped, no prompt; y launches; n, Esc, Enter and quit-while-open decline and record declined; other keys ignored) | D-1, D-2 | I-2 | uncle_tui.py, desktop_launch.py | tui-desktop-launch-test.py | window opens |
| AC-5,AC-6 (plus combined-signal precedence: opted_out > unattended > headless > attended-confirm) | D-3, D-4 | I-2 | desktop_launch.py | desktop-launch-test.py (includes a combined-case matrix asserting winner and recorded reason for every conflicting signal combination) | none |
| AC-7 | D-2 | I-1 | desktop_launch.py | desktop-launch-test.py (stub exits non-zero within grace -> failed; stub exits 0 within grace -> failed with log tail; stub alive past grace -> launched) | none |
| AC-8: with WORKFLOW_PREVIEW_DESKTOP set to a disabled value (0/false/no/off), nothing is detected, written or printed and the web preview runs unchanged, even for an Electron project; non-desktop projects are likewise unchanged. For a detected desktop project with the flow enabled, the web/early preview is suppressed whatever the desktop outcome (launched, declined, skipped, ambiguous, failed). | D-5, D-6, D-7 | I-4 | uncle_tui.py | existing + new (suppression asserted for launched, declined, skipped, ambiguous and failed outcomes; opt-out asserted as a strict no-op) | none |
| AC-9 | D-9 | I-3, I-4 | both | both, desktop-launch-test.py: close() with a pid file naming a foreign live pid and no Popen handle sends no signal to that pid | cleanup stops window |
| AC-10 | D-6 | all | all | both runner commands | none |

## Implementation sequence

1. Desktop module: detection, gating, headless, launch, grace watcher, pid/log/record files, close
   Owns: `scripts/lib/desktop_launch.py`
2. Module tests (independent of TUI; written against the contract in step 1's interfaces: `detect`, `launch_decision`, `DesktopLaunch`), covering cases (a)-(f) of the automated-test strategy
   Owns: `scripts/tests/desktop-launch-test.py`
3. TUI integration: import, `_offer_support` branch for both families (idempotent per run via a guard flag), `desktop` prompt with the key handling in section 7 (y launches; n/Esc/Enter/q decline; other keys ignored; resize redraws; quit = decline), poll events, close hooks, skip web preview when desktop enabled (builds on the existing functions in uncle_tui.py; sole writer of that file)
   Owns: `uncle_tui.py`
   Depends on: 1
4. TUI tests covering cases (g)-(j) of the automated-test strategy; sole owner of any environment setup (WORKFLOW_PREVIEW_DESKTOP=0) needed for regression runs; existing test files are not edited
   Owns: `scripts/tests/tui-desktop-launch-test.py`
   Depends on: 3
5. Docs
   
   Before coding step 3, read `_offer_support`, `_poll_completion_preview`, and the `complete`/`support` prompt key handling (uncle_tui.py ~6878) to mirror their patterns.
   Owns: `scripts/README.md`

## 21. Scope cuts under time pressure
Cut first: Tauri support, then `desktop.launch_command` config, then README docs. Never cut: confirmation gate, unattended/headless skip, pid tracking, cleanup.

## 22. Risks and unresolved questions
| Risk | Mitigation |
|---|---|
| Dialog ordering regresses star prompt | keep existing suites green; desktop prompt precedes `_completion_dialog` |
| Windows `npm` shims | argv passed through `launch_command` |
| Linux/Windows not live-verified | stated in non-goals; manual check on darwin only |
No blocking planning decisions remain.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan did not say when the attended prompt is shown; an explicit eligibility rule is needed. | Section 1 prose, DEC-4 and traceability row s18.1.r2 now state the prompt shows only for a single command, non-headless, no live pid file. |
| AR-002 | Accepted | Unattended and headless signals can overlap and the plan gave no precedence, making the gate untestable. | DEC-5 now says unattended is true if any signal holds; DEC-4 and DEC-5 state the order opt-out, unattended, headless, then ask. |
| AR-003 | Accepted | D-5 (opt-out does no detection) and D-7 (suppress web preview on detection) conflict; opt-out must leave the web preview unchanged. | Section 1 text states that with WORKFLOW_PREVIEW_DESKTOP=0 nothing is detected and the web preview runs as before, even for Electron projects; AC-8 traceability row updated. |
| AR-004 | Accepted | Real ambiguity; a single rule (suppress whenever a desktop project is detected with the flow enabled) is simple and predictable. | Section 1 now states the web preview and early preview are suppressed for any detected desktop project with the flow enabled, whatever the outcome; AC-8 aligned. |
| AR-005 | Accepted | PID reuse and post-grace crashes were unspecified; a command-matching liveness rule and TUI-bound crash reporting make both testable. | Edited DEC-8 (liveness = alive PID plus matching recorded command) and s10.1 (post-grace crash reported only while TUI is open). |
| AR-006 | Accepted | The behavior of an empty, unparsable or non-desktop-project launch_command was undefined and is cheap to specify. | DEC-9 now states empty/unparsable values are ignored with a one-line warning and the override applies only when a desktop framework is detected. |
| AR-007 | Accepted | The plan was silent on how a desktop project's launch.json web/command entry interacts with the desktop flow; the interaction needs a stated rule. | Added a launch.json interaction block after s1.1 and clarified s8.1: kind ignored for the preview, file untouched and still validated. |
| AR-008 | Accepted | Unconditional suppression on detection alone removes a user's web preview when no desktop launch happens, contradicting D-6/AC-8. | s1.1 now suppresses web previews only when a desktop launch is offered or occurs; AC-8 gains tests for decline/ambiguous/headless/unattended keeping the web preview. |
| AR-009 | Accepted | Real risk: isatty may be false under test or piped runs and would silently change the attended path of existing suites. | DEC-5 makes TUI attended state take precedence over isatty; s17 runs existing suites with WORKFLOW_PREVIEW_DESKTOP=0 or non-desktop fixtures. |
| AR-010 | Accepted | Key handling, resize, quit and duplicate workflow-exit behavior for the desktop prompt were unspecified. Decline-on-other-keys is rejected in favor of ignoring them, to avoid accidental declines. | Section 7 now specifies y/n/Esc/Enter/q keys, ignore-other-keys, resize redraw, quit as decline, and idempotent _offer_support; step 3 updated. |
| AR-011 | Accepted | The plan left unspecified what happens when the app is already running at the attended prompt or at the next workflow run. | Edited DEC-8 and s7.1: live pid skips the prompt, prints a message, records skipped, continues to _completion_dialog; next-run behavior defined. |
| AR-012 | Accepted | Auto-detected project scripts run with user privileges from a possibly untrusted repo, so the prompt must disclose the argv and default to No. | DEC-2 and R-1 now require the prompt to show the resolved argv, warn that project scripts run with user privileges, and default to No. |
| AR-013 | Accepted | `.uncle/config` lives in the project and may be repo-controlled, so a config command is untrusted like detected scripts and needs the same gate. | DEC-9 now says a config-supplied command is shown in full, never launches without confirmation, and is never treated as pre-trusted; s9.1 and AC-1/AC-2 traceability row r1 updated. |
| AR-014 | Accepted | A PID taken only from a file can be reused by an unrelated process, so cleanup must never signal it. | Edit DEC-8 and R-2 so cleanup kills only this session's Popen handle tree and a file-only pid is never killed; AC-9 tests it. |
| AR-015 | Accepted | Log tail is shown in the TUI and files may hold sensitive output, so permissions and escape stripping are warranted. | DEC-7 now requires 0600 files; s10.1 requires log tail control/escape sequences be stripped before display. |
| AR-016 | Accepted | Precedence between unattended, headless and attended signals was unspecified; any positive signal must win and the prompt must read only from the TUI's TTY. | DEC-4 and DEC-5 now state that any positive unattended or headless signal wins and the prompt reads only from the TUI's TTY. |
| AR-017 | Accepted | Conflicting opt-out/unattended/headless/attended signals need a single deterministic precedence and per-skip reason. | Section 1 (s1.1) states the precedence; DEC-4 and DEC-5 reference it; s18.1.r3 gains a combined-case test. |
| AR-018 | Accepted | Exit 0 within the grace period was covered by neither D-2 nor DEC-6; a desktop app that exits immediately did not launch successfully. | DEC-6 now says any exit within grace, including 0, is failed with log tail; AC-7 row s18.1.r2/AC-7 tests cover exit 0. |
| AR-019 | Accepted | The stale-pid rule was untestable without a liveness definition and corrupt-file behavior. | DEC-8 now defines liveness (os.kill(pid,0) plus matching command), corrupt file as stale, and blocked relaunch recording skipped/already running. |
| AR-020 | Accepted | Real gap: prompt key handling and quit-while-open were unspecified. | s7.1 now defines keys (y launches; n/Esc/Enter decline; others ignored; quit = decline); s18.1.r2 test coverage extended. |
| AR-021 | Accepted | Opt-out semantics were ambiguous between D-5 and D-7; a strict no-op rule resolves it and keeps the web preview unchanged. | Edit s8.1 to define disabled values and the strict no-op rule; add the same to s1.1 and AC-8 requirement. |
| AR-022 | Accepted | Malformed package.json, invalid launch_command and invalid grace values were unspecified and need defined results. | Edit DEC-1, DEC-2, DEC-6, DEC-9 and add an s18.1 traceability row for edge-input tests. |
