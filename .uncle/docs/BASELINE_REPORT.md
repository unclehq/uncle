# Baseline report: Issue 152 terminal tab title

Omitted sections: Reproduction result (not a bug report, a feature); Existing failures (none documented in-repo; driver baseline is authority)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md` (T-1..T-8, I-1..I-4). Tab title must carry the project name, be built by one shared function, restore the previous title via xterm title stack, and honour `UNCLE_TERMINAL_TITLE=0`.

## 2. Repository architecture
Bash drivers (`scripts/stagegate.sh`, `change-workflow.sh`, `from-issue.sh`), launcher `uncle` (TUI via `uncle_tui.py`, curses; line-based menu fallback in `uncle`), helpers in `scripts/lib/`. Python suites `scripts/tests/*-test.py`, shell suites `scripts/tests/*-test.sh`.

## 3. Relevant code paths
- `uncle_tui.py:1927-1949` `_write_title`, `_begin_title`, `_end_title`; callers at 2133, 2144, 1953, 3095.
- `uncle_tui.py:6363` status-bar project name: `os.path.basename(_project_root()) or _project_root()`; `_project_root` at 135 (`UNCLE_PROJECT_ROOT` if absolute, else cwd).
- `uncle_tui.py:7911-7914` `__main__`: `curses.wrapper(main)`; no idle title is written.
- `scripts/lib/terminal-title.sh:100-115` `uncle_title_begin/end` (second copy of the format); `--stop-tree` and `uncle_cancel` in same file must stay untouched.
- `scripts/from-issue.sh:37,582-585`; `scripts/change-workflow.sh:470,487,495-497`. `scripts/stagegate.sh` has no title handling and does not source terminal-title.sh.
- `uncle:304-320` TUI launch and line-based menu; no title handling.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | TUI run with issue number, not already owned | OSC 2 `uncle issue #N`; sets `UNCLE_TITLE_OWNER` in child env | uncle_tui.py:1938-1944 | Owner gating yes; text MODIFY |
| B-2 | Run ends / TUI closes | OSC 2 literal `uncle` | uncle_tui.py:1946-1949 | No (replace) |
| B-3 | Run with no issue number, idle TUI, line menu, stagegate.sh | No title written | code read | No (replace) |
| B-4 | Non-tty or TERM empty/dumb | Nothing written | 1929-1930; terminal-title.sh:103-104,113 | Yes |
| B-5 | Driver launched by TUI (owner set) | Driver writes nothing | terminal-title.sh:103 | Yes |
| B-6 | Status bar | `<dir basename> (<branch>)` | uncle_tui.py:6363-6369 | Yes (non-goal) |
| B-7 | `uncle_cancel`, `--stop-tree` | Kill process tree, exit code | cancel-stop-reason-test.sh | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| E-1 | Title written only when stdout and stderr are ttys and TERM not empty/dumb | both copies | none found | High |
| E-2 | Only one owner writes titles per process tree | `UNCLE_TITLE_OWNER` | none found | Medium |
| E-3 | Title issue is digits only | `_title_issue` regex, bash `*[!0-9]*` | none found | High |

## 6. Interface contracts
Env `UNCLE_TITLE_OWNER` (pid), new `UNCLE_TERMINAL_TITLE`. Shell functions `uncle_title_begin <issue>` / `uncle_title_end` (signature kept). Tests mock `_begin_title`/`_end_title` (chat-test.py:647, tui-support-test.py:136, tui-hotkeys-test.py:179), so those method names must stay.

## 7. Existing automated-test coverage
No test asserts OSC bytes or title text (grep for `uncle issue #`, `title_active`, `_write_title` in scripts/tests found only Mock uses). `terminal-title.sh` is exercised via `cancel-stop-reason-test.sh` and `triage-chat-test.py:167` (file copy list). Shell and Python runners use separate temp dirs and ports, so they run as one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh` (CLAUDE.md-mandated runners). Not run by this stage; driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authority. Some Python suites may already fail on a clean checkout.

## 12. Likely change surface
`uncle_tui.py`, `scripts/lib/terminal-title.sh`, new `scripts/lib/terminal_title.py`, `scripts/from-issue.sh`, `scripts/change-workflow.sh`, `scripts/stagegate.sh`, `uncle`, new test `scripts/tests/terminal-title-test.py`.

## 13. Regression-sensitive components
`uncle_cancel`/`--stop-tree` in terminal-title.sh (same file); EXIT traps in from-issue.sh/change-workflow.sh/stagegate.sh/uncle; TUI teardown ordering after curses.

## 14. Outside the change
Status bar rendering, GUI app window titles, per-stage progress titles.

## 15. Unknowns and assumptions
- Whether stagegate.sh/uncle already own an EXIT trap: implementer must read and chain, not replace.
- Terminal support for title stack cannot be detected; plan writes project-only title before popping.

## 16. Initial risk assessment
Medium-low: terminal escapes only, but multiple EXIT traps and two languages. Main risk is unsanitized text reaching the terminal (I-3).

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

