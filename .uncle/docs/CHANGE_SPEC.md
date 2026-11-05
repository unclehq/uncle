# Change Spec (Issue 164)

Omitted sections: Performance (none beyond existing turn timeouts); Migration beyond ignored legacy config; Prototype isolation (not a prototype)

## 1. Change type
Refactor plus Feature (remove a mode, upgrade the idle supervisor).

## 2. Problem
Two home-chat modes with different powers; neither is a general assistant. See CHANGE_REQUEST.md.

## 4. Desired behavior
One home-chat agent. With no build running it is a persistent Claude session with tools under Claude's normal permission system; it can start builds only by emitting a validated action the app executes. While a build runs, the existing tool-free supervisor applies.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S-1 | MODIFY | 'fork unclehq/uncle', no build | Housekeeping deny-list agent | Tool agent runs the command, reports real result; failure shown with output | TUI test, fake runner scripted tool result |
| S-2 | ADD | 'make directory demo and move into it' | Not possible | Directory created, app project root becomes it, status bar and title show it; on failure root unchanged | TUI test: `_project_root()` before/after |
| S-3 | ADD | clone, then 'build issue 34' | Not possible | Issue build targets the clone; mismatch refused with reason | TUI test: launched command cwd and root |
| S-4 | PRESERVE | 'build issue 34' | github_issue action | Same validated action | golden transcript test |
| S-5 | PRESERVE | hello-world C request | brief plus create_app | Same | golden transcript test |
| S-6 | PRESERVE | Any message while build runs | Tool-free supervisor | Tool-free session; command requests declined noting a build is running | TUI test: session argv has no tools; defect injection |
| S-7 | REMOVE | `uncle --housekeeping ...` | Runs driver | Unknown option, usage, exit non-zero, nothing started, no suggestion naming it | launcher shell test |
| S-8 | REMOVE | `/housekeeping`, `/mode housekeeping`, `/mode` | Recognized | Unknown command like any other | TUI test |
| S-9 | REMOVE | Configure > Miscellaneous | Housekeeping entry | No entry | TUI test and launcher menu test |
| S-10 | ADD | `.uncle/config` with `housekeeping.*` keys | read by housekeeping_config | Ignored, no error, nothing enabled | config test |
| S-11 | ADD | Command needing approval | deny list refusals | Claude permission flow: tool denied by Claude is surfaced in the TUI as a pending approval; user approves or declines; nothing bypasses silently | session test with fake runner emitting a denial |
| S-12 | ADD | `--unattended` or `--noui` run | housekeeping available | No home chat agent exists (no chat in those modes) | existing headless tests unchanged |
| S-13 | PRESERVE | create_change, run_app, run_change, stop_build, clear_build, resume_build | work | work | home-actions-test.py |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | NEW | No code, flag, setting, test or doc mentions housekeeping, except a migration note and this issue's removal tests | repo | static test | `no-housekeeping-test.py` |
| I-2 | EXISTING | Builds start only through the validated action path | home chat | `parse_home_action` + `_home_action`; driver entry points denied to the agent | action test, agent-argv test |
| I-3 | STRENGTHENED | While a build runs the supervisor has no tools | home chat | session creation chooses tool-free argv when build running | TUI test plus defect injection |
| I-4 | EXISTING | Agent completion claims rest on real results | prompt plus app messages | agent prompt; app reports action outcome itself | prompt test, action test |
| I-5 | EXISTING | Claude permission system; no bypass flags | agent argv | argv builder | argv test rejects `--dangerously-skip-permissions` and `bypassPermissions` |
| I-6 | NEW | Project root changes only to an existing absolute directory the app validated | cwd tracking | app-side validation | TUI test |

No RELAXED or REMOVED invariants. The housekeeping deny-list safety boundary is removed by design (it is a mechanism, not an invariant in the baseline).

## 7. Compatibility
Old `UNCLE_HOUSEKEEPING_*` env vars and `housekeeping.*` config keys are ignored silently. Other flags and stdin rules unchanged.

## 8. Errors
Runner not claude or claude missing: idle chat falls back to the tool-free supervisor with one note. Agent crash: restarted next message. Invalid cwd report: ignored, root unchanged, noted.

## 10. Security
Untrusted text (repos, issues, web) is data, never instruction; stated in the agent prompt; the permission prompt is the control. No env secrets passed beyond the existing STRIP_ENV treatment. Per-turn deadline retained.

## 12. Rollback
Revert the commit; no persisted format changes.

## 14. Non-goals
Build/gate/PR changes; new permission model; keeping any deny list as a safety boundary; tools during a build; codex/kimi tool agents.

## 15. Assumptions
Resolved here: unattended/noui have no home chat; Claude only; one persistent session per idle period, closed when a build starts and re-created (cwd = current root) when it ends; cost bounded by existing per-call settings plus turn deadline. Issues #148, #151, #155, #160 are updated manually by the user (out of code scope).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `uncle --housekeeping` and `--housekeeping=x` exit non-zero as unknown options, start nothing, and usage/did-you-mean text never mention housekeeping; remaining exclusivity and stdin rules hold. | New launcher shell test plus updated launcher-stdin-text and launcher-noui tests. |
| AC-2 | `/housekeeping`, `/mode`, the Configure housekeeping entry (launcher menu and TUI) and the `housekeeping` startup action no longer exist. | TUI Python test. |
| AC-3 | No file in the repository mentions housekeeping (case-insensitive) except the migration note and the removal tests, excluding .git, .uncle and FINAL_AUDIT.md. | no-housekeeping-test.py. |
| AC-4 | With no build running and a claude runner, a home message goes to a tool-enabled persistent session; a scripted fake-runner tool result is shown to the user and completion is reported only from that result. | TUI and session tests with fake runner. |
| AC-5 | When the agent reports a new directory, the app validates it, sets the project root, status bar and title show it, and a following build request targets it; invalid paths leave the root unchanged. | TUI test. |
| AC-6 | 'build issue 34' and the hello-world request map to the same validated actions as before; builds start only via the app's action path and the agent argv denies the driver entry points. | Golden transcript tests in home-actions-test.py; argv test. |
| AC-7 | While a build runs the supervisor session argv has no tools; giving it tools makes the test fail. | TUI test and recorded defect injection. |
| AC-8 | The agent argv uses Claude's permission mode default with no bypass flags; a denied tool is surfaced for user approval; headless runs offer no chat agent. | Session test; existing headless tests. |
| AC-9 | Legacy `housekeeping.*` config keys and old env vars are ignored without error. | Test loading a config containing them via the TUI/launcher paths. |
| AC-10 | Both verification commands pass with no regression versus baseline. | Driver re-run of verification_commands. |

