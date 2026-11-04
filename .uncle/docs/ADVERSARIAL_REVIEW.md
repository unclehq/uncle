## AR-001: Plan never says if the attended y/n prompt shows when detection is ambiguous, headless, or a live pid file exists.

- Severity: HIGH
- References: CHANGE_SPEC D-1, D-4; CHANGE_PLAN section 1 and DEC-8.
- Failure: Plan never says if the attended y/n prompt shows when detection is ambiguous, headless, or a live pid file exists. Say: 'The prompt is shown only for a single detected command, non-headless, no live pid file; otherwise print the reason or candidates, record skipped, no prompt.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Unattended and headless signals overlap with no precedence (attended TUI with no stdin TTY, or over SSH).

- Severity: HIGH
- References: CHANGE_PLAN DEC-4, DEC-5, launch_decision signature.
- Failure: Unattended and headless signals overlap with no precedence (attended TUI with no stdin TTY, or over SSH). Say: 'Unattended is true if any signal holds; launch_decision checks opt-out, then unattended, then headless, then asks.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: D-5 says opt-out does no detection, but D-7 suppresses web preview when desktop is detected and enabled.

- Severity: MEDIUM
- References: CHANGE_SPEC D-5 vs D-7.
- Failure: D-5 says opt-out does no detection, but D-7 suppresses web preview when desktop is detected and enabled. Say: 'With WORKFLOW_PREVIEW_DESKTOP=0 the web preview runs as before, even for Electron projects.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Unclear whether the web preview stays suppressed on a desktop project when the flow ends in decline, skip, ambiguous or

- Severity: MEDIUM
- References: CHANGE_PLAN section 1; CHANGE_SPEC D-7.
- Failure: Unclear whether the web preview stays suppressed on a desktop project when the flow ends in decline, skip, ambiguous or failure. Say: 'The web preview is suppressed for any detected desktop project with the flow enabled, whatever the outcome.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Live pid file blocks relaunch, but PID reuse and a crash after the grace period are unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN DEC-7, DEC-8, section 12.
- Failure: Live pid file blocks relaunch, but PID reuse and a crash after the grace period are unspecified. Say: 'A pid file is live only if the PID is alive and the recorded command matches; a later crash is reported only while the TUI is open.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Empty, unparsable or non-desktop-project `desktop.launch_command` behavior is undefined.

- Severity: LOW
- References: CHANGE_PLAN DEC-9; CHANGE_SPEC D-8.
- Failure: Empty, unparsable or non-desktop-project `desktop.launch_command` behavior is undefined. Say: 'An empty or unparsable value is ignored with a one-line warning; the override applies only when a desktop framework is detected.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan says the desktop prompt precedes `_completion_dialog` and that web CompletionPreview is skipped for desktop project

- Severity: HIGH
- References: CHANGE_PLAN s1 'web CompletionPreview and unattended _show_early_preview are skipped (D-7)' vs s5/s8 'launch.json contract unchanged'; spec D-7 says 'may open browser'.
- Failure: Plan says the desktop prompt precedes `_completion_dialog` and that web CompletionPreview is skipped for desktop projects, but never says how a project with a `launch.json` web/command entry and desktop detection interacts. Plan should say: when desktop is detected and enabled, `launch.json` kind is ignored for the preview, and the launch.json file is left untouched and still validated.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Skipping the early preview (and web preview) for a detected-desktop project is unconditional even when the desktop flow

- Severity: HIGH
- References: CHANGE_PLAN s1 'When desktop is detected and enabled... skipped'; D-3/D-4 produce no launch; AC-8 only tests opt-out and non-desktop projects.
- Failure: Skipping the early preview (and web preview) for a detected-desktop project is unconditional even when the desktop flow then declines, is ambiguous, is headless, or is unattended. A user whose Electron-detected project also has a web preview loses it, contradicting D-6/AC-8. Plan should say: web previews are skipped only when a desktop launch actually occurs or is offered, not on detection alone.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Unattended detection includes `not sys.stdin.isatty()`, which may be true in existing TUI tests or piped usage, silently

- Severity: MEDIUM
- References: CHANGE_PLAN DEC-5 vs s17 'existing suites must pass unchanged'; spec D-3.
- Failure: Unattended detection includes `not sys.stdin.isatty()`, which may be true in existing TUI tests or piped usage, silently changing the attended path of `_offer_support` and the existing quit flow. Plan should say: existing suites run with the desktop flow disabled via `WORKFLOW_PREVIEW_DESKTOP=0` or on non-desktop fixtures, and the TUI's own attended state takes precedence over isatty.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The new `prompt_kind='desktop'` is inserted before the support/finished dialog, but key handling, resize, quit and Esc b

- Severity: MEDIUM
- References: CHANGE_PLAN s7 'New prompt_kind=desktop (confirm/decline)'; key handling at uncle_tui.py ~6878 only referenced as to read.
- Failure: The new `prompt_kind='desktop'` is inserted before the support/finished dialog, but key handling, resize, quit and Esc behavior while the desktop prompt is showing are unspecified, and so is what happens if the workflow-exit event arrives twice. Plan should say: any key other than y/Y confirms decline, Esc/q declines, and `_offer_support` is idempotent per run.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Cleanup on stop_workflow/_quit kills the process, but the plan does not say what happens when the desktop app is still r

- Severity: MEDIUM
- References: CHANGE_PLAN DEC-8 'live one blocks relaunch with a message' vs s7 flow.
- Failure: Cleanup on stop_workflow/_quit kills the process, but the plan does not say what happens when the desktop app is still running at the time the TUI starts the next workflow run, or when the live-pid-file relaunch block (DEC-8) fires in the attended prompt. Plan should say: a live pid blocks the prompt, prints a message, and the flow continues to `_completion_dialog`.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan auto-detects and runs project-defined commands (npm start/dev) from a freshly built, possibly untrusted repo; the p

- Severity: HIGH
- References: CHANGE_PLAN DEC-2 and D-1/D-2; I-2 requires confirmation but sets no default or disclosure rule.
- Failure: Plan auto-detects and runs project-defined commands (npm start/dev) from a freshly built, possibly untrusted repo; the prompt only shows the command. Plan should say: the prompt displays the resolved argv, warns that project scripts run with user privileges, and defaults to No.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: `desktop.launch_command` is read from `.uncle/config`, which lives in the project and may be repo-controlled, yet the sp

- Severity: HIGH
- References: CHANGE_SPEC section 10 Security; DEC-9 and D-8.
- Failure: `desktop.launch_command` is read from `.uncle/config`, which lives in the project and may be repo-controlled, yet the spec calls it 'the operator's own'. Plan should say: a config-supplied command is shown in full and never launches without confirmation.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Cleanup behavior is unspecified for a stale pid file whose PID has been reused by another process.

- Severity: MEDIUM
- References: DEC-8, D-9 and R-2 do not define pid-reuse verification.
- Failure: Cleanup behavior is unspecified for a stale pid file whose PID has been reused by another process. Plan should say: cleanup kills only the process tree of this session's Popen handle, or verifies pid, start time and command before killing, and never kills a pid taken only from the file.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Log tail is displayed in the TUI and files are created with unspecified permissions.

- Severity: MEDIUM
- References: DEC-7 and section 12 ('last 20 log lines'); no sanitization or permission rule.
- Failure: Log tail is displayed in the TUI and files are created with unspecified permissions. Plan should say: pid, log and record files are created mode 0600 and the log tail is stripped of control/escape sequences before display.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Precedence between attended, unattended and headless signals is unspecified, for example workflow_unattended false but s

- Severity: MEDIUM
- References: DEC-4/DEC-5 and `launch_decision(attended, unattended, headless, opted_out)`.
- Failure: Precedence between attended, unattended and headless signals is unspecified, for example workflow_unattended false but stdin not a TTY. Plan should say: any positive unattended or headless signal always wins, and the desktop prompt reads only from the TUI's TTY.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: The plan never says which of opted_out, unattended, headless and attended wins when they conflict, or which skip reason

- Severity: HIGH
- References: CHANGE_PLAN s1 and DEC-4/DEC-5; AC-5 and AC-6 are tested separately, with no combined-case row.
- Failure: The plan never says which of opted_out, unattended, headless and attended wins when they conflict, or which skip reason is recorded. Say: 'Precedence is opted_out, then unattended, then headless, then attended-confirm; each skip records only its own reason.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: D-2 says a crash or non-zero exit within grace is failed.

- Severity: HIGH
- References: CHANGE_SPEC D-2; CHANGE_PLAN DEC-6; AC-7 covers only non-zero.
- Failure: D-2 says a crash or non-zero exit within grace is failed. DEC-6 says alive after grace is success. An exit 0 within grace is covered by neither rule. Say: 'Any exit within grace, including 0, is failed with the log tail.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The stale-pid rule is untestable: it doesn't say how a live pid is told from a reused one, or what a corrupt pid file do

- Severity: MEDIUM
- References: CHANGE_PLAN DEC-8; no AC covers it, though CHANGE_SPEC s8 lists it.
- Failure: The stale-pid rule is untestable: it doesn't say how a live pid is told from a reused one, or what a corrupt pid file does. Say: 'Liveness is os.kill(pid,0) plus a matching recorded command; an unparseable pid file is stale; a blocked relaunch records status skipped, reason already running.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The desktop prompt's keys other than y and n are unspecified, as is quit while the prompt is open.

- Severity: MEDIUM
- References: CHANGE_PLAN s7; AC-4 tests decline only.
- Failure: The desktop prompt's keys other than y and n are unspecified, as is quit while the prompt is open. Say: 'y launches. n, Esc and Enter decline and record declined. Other keys are ignored. Quit while the prompt is open counts as decline.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: D-5 says opt-out means no output.

- Severity: MEDIUM
- References: CHANGE_SPEC D-5 and D-7; CHANGE_PLAN s8 ('0 disables').
- Failure: D-5 says opt-out means no output. D-7 skips the web preview only when desktop is detected and enabled, and opt-out does no detection. It's unspecified whether opted-out runs write files or keep the web preview. Say: 'With =0, nothing is detected, written or printed, and the web preview is unchanged.' Also say which values count as disabled.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: The plan gives no result for malformed package.json, an empty or invalid launch_command, or an invalid or zero grace val

- Severity: LOW
- References: CHANGE_PLAN DEC-1, DEC-2, DEC-6 and DEC-9; AC-1 and AC-2 cover only the happy path.
- Failure: The plan gives no result for malformed package.json, an empty or invalid launch_command, or an invalid or zero grace value. Say: 'Invalid package.json gives none. Invalid launch_command is ignored with a warning and falls back to guessing. Invalid or negative grace uses 3 s; 0 checks immediately.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
