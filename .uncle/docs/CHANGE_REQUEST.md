# Change Request

Issue 145

Seeded from [unclehq/uncle#145](https://github.com/unclehq/uncle/issues/145).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Preview and launch the desktop app (e.g. Electron) at the end of a build

## Motivation

## Problem

Uncle can preview a web application while a build is running: `scripts/lib/preview-build.sh` starts a preview, `scripts/lib/preview_server.py` serves it, and a browser tab is opened (`WORKFLOW_PREVIEW_OPEN_BROWSER`). That flow assumes the app is a web app.

When Uncle is building a desktop app (Electron, Tauri, or similar), or changing an existing one, there is nothing equivalent. The run ends and the operator has to work out how to launch the app themselves before they can see whether it works.

## Requested behavior

At the end of a build (after implementation and automated verification), if the project is a desktop app, Uncle should:

1. **Detect** that it is a desktop app. Examples: `electron` in `package.json` dependencies, a `main` entry that is an Electron main process, `electron-builder` or `electron-forge` config, `src-tauri/`, or a plan that says so.
2. **Offer to launch** it: show the launch command and ask before starting. The default must be safe for unattended runs, which should not launch a GUI.
3. **Launch** the app with the project's own run command (for example `npm start`, `npm run dev`, or `electron .`). Prefer an explicit `.uncle/config` setting over guessing.
4. **Report** what was launched: command, PID, and log path. Stop the process when the run is cleaned up, or leave it running and say so. Behavior should match how the web preview server is handled.

## Observable behaviors (draft)

| Id | Trigger | Expected result | Failure behavior |
|---|---|---|---|
| D-1 | Build completes for a project detected as a desktop app, attended | Uncle prints the detected framework and launch command and asks to launch | Detection is ambiguous: say so, show the candidate commands, and launch nothing |
| D-2 | User confirms | The app window opens; Uncle prints PID and log path | Launch command exits non-zero or crashes within a short grace period: report the exit code and the tail of the log, and mark the preview as failed (never as passed) |
| D-3 | Unattended run (`WORKFLOW_UNATTENDED` or no TTY) | No GUI is launched and the command is printed for later | Never block waiting for input |
| D-4 | Headless environment (no display, CI, SSH session) | Skip with a clear reason | Never report a launch that did not happen |
| D-5 | Opt-out (`WORKFLOW_PREVIEW_DESKTOP=0`) | Nothing is detected or launched | n/a |
| D-6 | Web project | No behavior change | n/a |

## Invariants

- Launching is a convenience, **not evidence**. It writes no test report row and never turns a manual check into PASS (same rule as the preview build).
- Nothing is launched without confirmation in an attended run, and never in an unattended one.
- The launched process is owned and tracked (pid file in `.uncle/workflow/`) so it cannot be orphaned silently.
- Launching never alters tracked files or the working tree.

## Open questions

- Should this extend `preview-build.sh` (early preview from the brief) as well, or only run at the end of the build? The request is the end of the build, so start there.
- Which frameworks are in scope first? Suggest Electron, then Tauri.
- Should the launch happen from the issue/change worktree or from the source checkout? Worktrees are removed after a PR, so the app must be stopped before removal.
- Windows and Linux launch quirks (display detection, `npm` shims).

## Verification ideas

- Unit tests for desktop detection over fixture `package.json` files (Electron, Tauri, plain web, ambiguous).
- Driver test with a stub launch command: attended confirm, attended decline, unattended, headless, crash-on-start, opt-out.
- Manual check: build a minimal Electron app with Uncle and confirm the window opens.

## Non-goals

- Packaging or signing installers.
- Automated GUI testing of the launched app.
- Mobile apps.

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
