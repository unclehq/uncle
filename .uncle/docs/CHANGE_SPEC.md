# Change spec: Issue 246

Omitted sections: Migration (none); Prototype isolation (n/a); Rollback folded into 12

## 1. Change type
Feature.

## 2. Problem statement
`--noui` builds give no sign of the preview or the app while building, unlike TUI builds.

## 3. Current behavior
Baseline B-1.

## 4. Desired behavior
While the build runs, the headless runner prints plain-text lines announcing the preview URL and the app URL/status as they become available (and again if they change), and a final app-launch status line at the end.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | ADD | Driver publishes a live preview URL (`preview-server.url` with live `preview-server.pid`) during the run | Nothing printed | One line `Preview: <url>` with elapsed prefix printed within about 1 s, while the build still runs | headless-preview test with fake driver |
| SB-2 | ADD | Preview URL changes (static to dev handoff) | Nothing | A new `Preview:` line for the new URL; unchanged URL is not repeated | test |
| SB-3 | ADD | App dev server URL published (`app-server.url` or `preview-vite.url` with live pid) | Nothing | `App: <url>` line, once per distinct URL | test |
| SB-4 | ADD | Driver exits and `.uncle/launch.json` exists | Nothing | Final line `App: <how to run>` (command, page path, or `none`) before exit, never after the exit decision | test |
| SB-5 | ADD | Stale url file whose pid is dead or missing, or non-loopback/invalid content | Nothing | Nothing printed | test |
| SB-6 | PRESERVE | Any run | Exit codes, signal handling, gate stop, masking, escape filtering, stdin handling | Identical | existing suites |
| SB-7 | PRESERVE | UI (non-noui) build | TUI behavior | Unchanged | existing suites |
| SB-8 | MODIFY | `docs/noui.md` | No mention | Documents the Preview/App lines | doc grep test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | EXISTING | Exit-code mapping and precedence unchanged | headless | `classify_exit` | headless-run-test |
| SI-2 | EXISTING | No curses, no escape sequences, secrets masked | headless output | `EscapeFilter`, `redact` | headless-run-test |
| SI-3 | NEW | Announcements never split a partially written driver line | headless output | watcher emits only at line start, or after a forced newline at final flush | headless-preview test |
| SI-4 | NEW | Watcher failure (unreadable or malformed files) never changes the exit code or aborts streaming | headless | try/except around watcher | test |
| SI-5 | NEW | Only loopback http(s) URLs from live-pid state files are announced | headless | URL validator | test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Driver stdout lines unchanged; added lines only. Scripts parsing `Finished build:` blocks are unaffected because added lines are separate and prefixed `Preview:` / `App:`.

## 8. Failure behavior
Missing, unreadable, oversize (>2048 bytes) or invalid state files are ignored silently.

## 10. Security
Only loopback URLs printed; output passes through `redact`.

## 12. Rollback
Revert the commit; no persisted state.

## 14. Non-goals
Starting servers from the headless runner, opening a browser, curses, new exit codes, changing the TUI, changing driver scripts.

## 15. Assumptions
A1-A3 of the baseline.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With a fake driver that publishes a live `preview-server.url` mid-run and keeps running, the headless output contains a `Preview: <url>` line before the driver exits. | headless-preview test asserts line order against a later driver line |
| AC-2 | A changed preview URL yields a new Preview line; an unchanged URL is printed once only. | headless-preview test |
| AC-3 | A live `app-server.url` or `preview-vite.url` yields an `App: <url>` line; `.uncle/launch.json` yields a final `App:` status line. | headless-preview test |
| AC-4 | State files with a dead/missing pid, non-loopback URLs, or garbage produce no announcement and no error. | headless-preview test |
| AC-5 | Announcements never appear inside a partially written driver line, carry the elapsed prefix, and contain no escape sequences. | headless-preview test with a driver printing a partial line |
| AC-6 | Exit codes 0/1/3/130/143 and all existing --noui behavior are unchanged. | bash scripts/run-python-tests.sh and bash scripts/run-shell-tests.sh pass as at baseline |
| AC-7 | docs/noui.md documents the Preview/App lines. | headless-preview test greps the doc |

