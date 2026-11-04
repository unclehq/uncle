# Change spec (issue 145)

Omitted sections: Migration (none); Prototype isolation (not a prototype); Performance (only the grace period, in AC)

## 1. Change type
Feature.

## 2. Problem statement
At the end of a build of a desktop app the operator must find the launch command themselves; the web preview has no desktop equivalent.

## 3. Current behavior
Baseline B-1..B-6.

## 4. Desired behavior
After a successful workflow, for a project detected as Electron or Tauri, Uncle shows the framework and command, asks (attended) before launching, launches the project's own command with a pid file and log under `.uncle/workflow/`, reports command/PID/log, and stops it when the run is cleaned up (same as the web preview). Unattended or headless runs print the command and launch nothing.

## 5. Observable behavior table
| ID | Class | Trigger | Current | Expected | Verification |
|---|---|---|---|---|---|
| D-1 | ADD | Build completes, attended, desktop detected | Nothing | Prints framework + command, asks to launch; ambiguous detection lists candidates and launches nothing | unit detection + TUI test |
| D-2 | ADD | User confirms | n/a | App starts; PID and log path printed. Exit non-zero or crash within grace period (default 3 s, `WORKFLOW_PREVIEW_DESKTOP_GRACE`): exit code and log tail reported, status failed, never passed | stub-command driver test |
| D-3 | ADD | Unattended (`--unattended`, `WORKFLOW_UNATTENDED=1`, or no TTY) | n/a | Nothing launched, command printed and recorded in `.uncle/workflow/desktop-launch.json`; never waits for input | driver test |
| D-4 | ADD | Headless (no DISPLAY/WAYLAND_DISPLAY on Linux, `CI` set, SSH session) | n/a | Skip with clear reason; no launch reported | env-matrix test |
| D-5 | ADD | `WORKFLOW_PREVIEW_DESKTOP=0` | n/a | No detection, no launch, no output | test |
| D-6 | PRESERVE | Web or non-desktop project (B-1..B-5) | as baseline | unchanged | existing suites + fixture test |
| D-7 | MODIFY | Desktop project, desktop flow enabled | web `CompletionPreview` may open browser (B-6) | desktop flow replaces web completion preview and early-preview browser open for that project | TUI test |
| D-8 | ADD | `.uncle/config` has `desktop.launch_command` | n/a | That command (shell-split to argv) overrides guessing | unit test |
| D-9 | ADD | Run cleanup (stop_workflow/quit) with app running | n/a | Process tree killed, pid file removed | test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | Launching is not evidence: writes no test-report row, never turns a check into PASS | all launches | desktop_launch.py writes only desktop-launch.json/log/pid | test asserts no report files touched |
| I-2 | NEW | No launch without confirmation attended; no launch ever unattended | desktop flow | gate function `launch_decision` | decision-matrix test |
| I-3 | NEW | Launched process is tracked by pid file in `.uncle/workflow/` and killed on cleanup | desktop flow | launch/stop functions | test |
| I-4 | NEW | Launch never alters tracked files; only untracked `.uncle/workflow/*` written | desktop flow | write paths restricted | git-status test |
| I-5 | EXISTING | Launch commands are argv arrays | all | no shell=True | test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
launch.json schema, existing env vars and web preview unchanged.

## 8. Error behavior
Ambiguous detection, headless, crash, missing executable (OSError), stale live pid file: each reports a one-line reason, launches nothing or marks failed, and never blocks.

## 10. Security
Argv arrays only; command from `.uncle/config` is the operator's own; no network.

## 12. Rollback
Set `WORKFLOW_PREVIEW_DESKTOP=0`, or revert the commit; no persisted schema change beyond untracked runtime files.

## 14. Non-goals
Packaging/signing, GUI testing, mobile, early preview for desktop, Windows/Linux live verification.

## 15. Assumptions
- Scope: Electron first, Tauri second; end-of-build only (resolves open question 1, 2).
- Launch from project root (`_project_root()`), killed before worktree removal because cleanup kills it (open question 3).
- Windows/Linux quirks are handled by display detection and `launch_command`; not live-verified.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Detection returns framework+argv for fixture package.json with electron (start script), Tauri (src-tauri + scripts.tauri), none for plain web, and ambiguous (with candidate list) for electron with both start and dev scripts or electron with no run script | scripts/tests/desktop-launch-test.py detection cases |
| AC-2 | `.uncle/config` key `desktop.launch_command` overrides guessed command | desktop-launch-test.py config case |
| AC-3 | Attended confirm launches the stub command, prints PID and log path, and writes pid file and log under .uncle/workflow/ | desktop-launch-test.py and tui-desktop-launch-test.py with stub command |
| AC-4 | Attended decline launches nothing and prints the command | tui-desktop-launch-test.py |
| AC-5 | Unattended (flag, env, or no TTY) never launches, never prompts, prints command and records it | decision-matrix test |
| AC-6 | Headless (Linux without display, CI set, SSH session) skips with a stated reason and reports no launch | env-matrix test |
| AC-7 | Stub that exits non-zero within the grace period is reported failed with exit code and log tail; pid file removed | crash-on-start test |
| AC-8 | WORKFLOW_PREVIEW_DESKTOP=0 performs no detection and launches nothing; web/non-desktop projects behave as before | opt-out test plus existing completion-preview-test.py and tui-complete-dialog-test.py pass |
| AC-9 | Cleanup kills the launched process tree and removes the pid file; launching leaves tracked files and git status unchanged and writes no test-report rows | cleanup test and git-status assertion |
| AC-10 | Both repository runner commands show no regression versus the baseline | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh |

