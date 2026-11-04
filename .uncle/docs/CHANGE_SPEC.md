# Change spec: Issue 152 terminal tab title shows project name

Omitted sections: Performance (negligible), Migration (none), Prototype isolation (not a prototype)

## 1. Change type
Feature.

## 2. Problem statement
Tab titles read `uncle` / `uncle issue #N`, so tabs for different projects cannot be told apart.

## 3. Current behavior
Baseline B-1..B-5.

## 4. Desired behavior
Title is `<project> · uncle` (idle, no-issue runs, line menu, every driver) and `<project> · uncle issue #N` for issue-backed runs. Project is the status-bar name (directory basename of `UNCLE_PROJECT_ROOT` or cwd). On end/exit the previous title is restored with the xterm title stack; the project-only title is written first as fallback. Issue number is kept as before; run state and OSC 1 are not added.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| BH-1 | ADD | TUI idle start, tty | No title | Push `CSI 22;2 t`, write `ESC]2;<project> · uncle BEL` (T-1,T-5) | pty test |
| BH-2 | MODIFY | Run with issue number | `uncle issue #N` | `<project> · uncle issue #N` (T-2) | pty + unit |
| BH-3 | ADD | Run with no issue (TUI or driver) | No title | `<project> · uncle` (T-3) | pty test |
| BH-4 | MODIFY | Run end or exit | Literal `uncle` | Project-only title then `CSI 23;2 t`; never bare `uncle` (T-4) | pty test + defect injection |
| BH-5 | ADD | Line menu, stagegate.sh, change-workflow.sh, from-issue.sh start | No/partial title | Same format and stack discipline (all entry points) | pty test per entry |
| BH-6 | PRESERVE | Non-tty, TERM empty/dumb (T-8) | Nothing written | Nothing written, including stack sequences | pty/pipe test |
| BH-7 | ADD | `UNCLE_TERMINAL_TITLE=0` (T-7) | n/a | No title or stack bytes anywhere | pty test |
| BH-8 | ADD | Name has control chars/ESC/BEL or is very long (T-6) | n/a | Control chars removed, truncated to 60 chars, fallback to `uncle` when empty | unit test |
| BH-9 | PRESERVE | Driver started by TUI (owner set) | Driver silent | Driver silent; no nested push | pty test |
| BH-10 | PRESERVE | Status bar | `<dir> (<branch>)` | Unchanged; project name from same helper (I-2) | consistency test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | NEW | One title builder shared by TUI and shell | all title writes | `scripts/lib/terminal_title.py` | unit + grep test for no literal OSC 2 elsewhere |
| I-2 | NEW | Title project == status-bar project | TUI | shared `project_name()` | consistency test |
| I-3 | NEW | Only sanitized text reaches terminal; no ESC/BEL/control chars in OSC payload | all writes | builder | unit test |
| I-4 | STRENGTHENED (E-1) | Writes only on tty with TERM set and not dumb, and `UNCLE_TERMINAL_TITLE!=0` | all writes | builder guard + bash guard | pty/pipe tests |
| I-5 | EXISTING (E-2) | Single owner per process tree | drivers under TUI | `UNCLE_TITLE_OWNER` | pty test BH-9 |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Shell function names/signatures, `_begin_title`/`_end_title` names, `UNCLE_TITLE_OWNER` semantics kept.

## 8. Error and failure behavior
Unresolvable name: basename fallback, then `uncle`; never empty. Write errors (OSError/ValueError) swallowed. Helper failure in bash never aborts the driver (`|| true`).

## 10. Security
Project, branch and issue text are never trusted: strip C0/C1 controls and DEL; digits-only issue.

## 12. Rollback
Revert the commit; `UNCLE_TERMINAL_TITLE=0` disables at runtime.

## 14. Non-goals
Status bar changes, GUI window titles, per-stage progress, OSC 1, run state in title.

## 15. Assumptions
Terminals lacking the title stack ignore `CSI 22/23;2 t`; fallback title remains project-only. Base project in worktrees is not shown (the directory name already matches the status bar).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | A shared builder returns a title containing the project name first, followed by ` · uncle` (plus ` issue #N` for a numeric issue); sanitizes control/escape characters, truncates to 60 chars, never returns empty. | Unit tests in scripts/tests/terminal-title-test.py: normal, worktree, empty, long, ESC/BEL/newline names, non-numeric issue. |
| AC-2 | The TUI under a pty writes the idle title at start and the title stack push, and at exit writes the project-only title then the pop; no bare `uncle` title is ever written. | pty test asserting exact bytes for start and exit (UNCLE_TUI_TEST_MAIN stub or equivalent). |
| AC-3 | Title during a TUI run includes the issue number when known and the project name when not; run end returns to the project-only title. | Python test driving _begin_title/_end_title with a captured tty and asserting bytes. |
| AC-4 | stagegate.sh, change-workflow.sh, from-issue.sh and the uncle line menu write the same format via the shared builder, including runs without an issue number, and restore on exit. | Bash functions under a pty: source terminal-title.sh, call uncle_title_begin with and without issue, uncle_title_end; assert bytes. Grep test that the drivers source/call it. |
| AC-5 | Nothing is written (no title, no stack sequences) when stdout or stderr is not a tty, TERM is empty or dumb, or UNCLE_TERMINAL_TITLE=0. | pty/pipe tests for Python and Bash paths. |
| AC-6 | A driver started by the TUI (UNCLE_TITLE_OWNER set) writes nothing and does not push the stack. | Bash pty test with UNCLE_TITLE_OWNER set. |
| AC-7 | The status-bar project name and the title project name come from one helper and are equal for a worktree-named root (e.g. grove-issue-33). | Consistency test with UNCLE_PROJECT_ROOT=/tmp/x/grove-issue-33. |
| AC-8 | Defect injection: restoring the literal `uncle` reset or removing sanitization makes the new tests fail. | Run new tests against a temporarily mutated copy (disposable, not the checkout) and record failure in the test report. |
| AC-9 | Existing shell and Python suites do not regress; uncle_cancel/--stop-tree behavior unchanged. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh vs baseline. |

