# Change plan: Issue 152 terminal tab title shows project name

Seeded from [unclehq/uncle#152](https://github.com/unclehq/uncle/issues/152).

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (none); Feature-flag (runtime opt-out only, see 15)

Issue 152

## 1. Selected technical approach

New `scripts/lib/terminal_title.py`: pure `sanitize`, `project_name(root)`, `build_title(project, issue)`, `enabled()` guard, and writers `begin(issue)`, `retitle(issue)`, `end()`; CLI `python3 -B terminal_title.py begin|retitle|end [issue]`. `uncle_tui.py` imports it; `terminal-title.sh` calls the CLI. The CLI is invoked from bash with fds 1 and 2 inherited unchanged, so its isatty checks see the same terminal the shell sees. A missing or failing python3 (or CLI error) yields silence and exit 0, never a changed exit code. A non-numeric or empty issue is treated as no issue (title `<project> · uncle`). Decisions: D-1 format `<project> · uncle` / `<project> · uncle issue #N`; D-2 issue kept, no run state, no OSC 1; D-3 `begin()` pushes `CSI 22;2 t` at most once per process and records that it pushed; `end()` writes the project-only title then `CSI 23;2 t` ONLY if begin() pushed in this process, is idempotent, and never acts when nothing was pushed (e.g. guard false); on a run end while the TUI lives, the TUI writes only the idle title `<project> · uncle` and never pops; D-4 `sanitize` first drops every character in Unicode categories Cc (C0/C1/DEL), Cf, Zl and Zp, then trims whitespace; only the project name is then truncated to at most 60 code points; the fixed suffix (` · uncle` or ` · uncle issue #N`, digits never truncated) is appended afterwards so it always survives (the full title may exceed 60 chars); if the sanitized project name is empty the whole title is exactly bare `uncle`; D-5 project = basename of `UNCLE_PROJECT_ROOT` (absolute) else cwd, identical to status bar; D-6 TUI owns the stack for its whole session (begin before `curses.wrapper`, end in `finally` after teardown) and exports `UNCLE_TITLE_OWNER` to children ONLY when its own begin actually pushed (so a TUI that skipped begin, e.g. non-tty or opt-out, leaves it unset); per-run the TUI only retitles on run start and run end (no push, no pop); D-7 shell scripts push only when `UNCLE_TITLE_OWNER` is unset/empty; when it is set, `uncle_title_begin/end` write nothing at all (including on no-issue runs) and only the TUI retitles; the `uncle` line menu likewise exports `UNCLE_TITLE_OWNER` when its begin actually pushed, so child drivers it starts push and retitle nothing; D-8 balance: begin is once-only per process (a second begin is a no-op, tracked by a per-process flag in the TUI and `UNCLE_TITLE_ACTIVE` in bash); end pops only if this process pushed, is idempotent (a second end or an end without begin writes nothing), and runs on every exit path: the TUI `finally`, SIGTERM/SIGHUP handlers that call end then exit, and the shell EXIT trap (including via `uncle_cancel`'s exit); D-9 streams and opt-out: title and stack sequences go to stderr in the TUI and stdout in the shell/CLI path, and are written only when both stdout and stderr are ttys, TERM is set and not dumb, and `UNCLE_TERMINAL_TITLE` is not exactly `0` (only the exact value `0` disables; any other value enables); if any condition fails nothing is written, and end re-checks this full guard at exit.

Title, CLI and ownership rules (resolve AR-003, AR-004, AR-015, AR-016; D-8, D-9). (1) Project name: use `UNCLE_PROJECT_ROOT` only if it is a non-empty absolute path, otherwise use cwd; take the basename, strip control characters and trim whitespace; if the result is empty (e.g. root `/`), the whole title is exactly `uncle` (no ` · uncle` suffix, no issue suffix). (2) D-8 issue: used only if it fully matches `^[0-9]+$`; a non-numeric, empty or flag-like value (e.g. `--x`, `12a`) is treated as no issue and yields `<project> · uncle`; digits are never truncated. (3) Length: the full title is at most 60 characters (code points); only the sanitized project name is truncated so the fixed suffix (` · uncle` or ` · uncle issue #N`) is always kept intact. (4) CLI: the issue is the only argument; the project root is read only from `UNCLE_PROJECT_ROOT` (else cwd), never from argv; the CLI `begin|retitle|end` is stateless. (5) end() re-evaluates the full guard (enabled, stdout and stderr ttys, TERM set and not dumb) at exit time and writes nothing, including no stack pop, if it fails; it also writes nothing unless this process performed the matching begin. (6) D-9 ownership: `UNCLE_TITLE_OWNER` is honored only when it is a positive integer naming a live ancestor PID of the current process (checked with kill -0 and the parent chain); an empty, non-numeric, stale or environment-injected value is treated as unset, so the driver then pushes and retitles itself. When honored, `uncle_title_begin` and `uncle_title_end` are no-ops; when not owned, the bash `uncle_title_end` acts only if this shell's own `uncle_title_begin` pushed, tracked by `UNCLE_TITLE_ACTIVE=1` (reset to 0 on end). Unit tests (terminal-title-test.py) cover relative/empty root, root `/`, all-control-char name, long names with and without an issue, non-numeric/empty/flag-like issues, end() guard failure, and stale/invalid owner values.

## 2. Alternatives considered
A: Bash builder called from Python (slower, sanitizing in sed is fragile). B: duplicate builder in both languages (violates I-1). C: only fix text, no stack (misses restore requirement).

## 3. Why preferred
Python has robust Unicode/control-char handling, one source of truth, bash cost is one short `python3` call per run.

## 4. Exact components to modify
See change-impact table.

## 5. Not to modify
Status-bar rendering beyond swapping the name helper; `--stop-tree`, `uncle_cancel`, `uncle_run` in terminal-title.sh; prompts; other drivers.

## 6. Data-flow changes
Project root -> `project_name` -> `build_title` -> guarded write. Status bar uses `project_name` as well.

## 7. State-transition changes
TUI: untitled -> idle titled (start) -> run titled -> idle titled -> restored (exit). Drivers: untitled -> titled -> restored.

## 8. Interface changes

New module and env `UNCLE_TERMINAL_TITLE`. `uncle_title_begin` now accepts an empty issue. A non-numeric issue (anything not matching ^[0-9]+$) is treated as empty and produces `<project> · uncle`; it is never rejected or echoed into the title.

## 12. Error and recovery

All writes wrapped; helper failure never changes exit codes. EXIT traps chain onto existing ones, not replace. `uncle_title_end` is idempotent and is run from the EXIT trap so it fires on every exit path, including `uncle_cancel` (which calls `exit`); a second `uncle_title_begin` in the same process is a no-op, so push/pop stays balanced.

## 14. Rollback plan
Revert the commit; runtime opt-out `UNCLE_TERMINAL_TITLE=0`. No persisted state.

## 15. Containment
`UNCLE_TERMINAL_TITLE=0` disables everything.

## 16. Automated-test strategy

New `scripts/tests/terminal-title-test.py` (hyphenated, collected by run-python-tests.sh). Contains unit tests (AC-1,AC-7) including the cap order: a 100-code-point project name yields a 60-code-point name plus intact suffix, and controls are stripped before the cap; pty tests via `pty`/`os.openpty` for TUI helpers and bash functions (AC-2..AC-6), including that exit writes the project-only title before `CSI 23;2 t` and that run end writes only the idle title with no pop; a grep guard for no stray `]2;` literals outside the helper (I-1), and a defect-injection test (AC-8) that copies terminal_title.py to a temp dir, applies each of two mutants, and runs the title assertions against the mutated copy, requiring failure for each: (a) end() writes the bare title `uncle` instead of the project-only title; (b) sanitize() disabled (returns input unchanged). The test also asserts the unmutated copy passes. Git fixtures, if any, use signing disabled.

Test file ownership (supersedes the single-file layout above; one owner per file): `scripts/tests/terminal-title-unit-test.py` (step 1: builder, sanitizer, issue/root/cap/opt-out matrices, CLI argv hardening, push/pop balance), `scripts/tests/terminal-title-tui-test.py` (step 2: pty TUI stream, run-end vs exit byte order, signals/exceptions, owner export only when begin wrote), `scripts/tests/terminal-title-shell-test.py` (step 5: bash pty tests for owner-set zero bytes, double begin, idempotent end, uncle_cancel EXIT trap, missing python3, UNCLE_TITLE_ACTIVE gating, forged owner PID) and `scripts/tests/terminal-title-mutation-test.py` (step 5: AC-8 mutants (a) end writes bare `uncle`, (b) sanitize disabled; each must fail the title assertions; never cut). All four are protected verification paths.

## 17. Regression-test strategy
Existing Mock-based tests keep method names `_begin_title`/`_end_title`. `cancel-stop-reason-test.sh` covers terminal-title.sh sourcing. Full suites via baseline commands.

## 18. Manual verification
Open Uncle in two project directories in two tabs, confirm distinct titles; run a worktree issue; exit and confirm previous title restored; try `UNCLE_TERMINAL_TITLE=0` and `uncle | cat`.

## 19. Observability
None.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST I-1 | AC-1 | One builder | terminal_title.py, bash calls CLI | no drift | CAP-PY3 | python3 used by uncle:305, terminal-title.sh:5 | CODING |
| R-2 | USER | I-3, T-6 | AC-1 | Sanitized | sanitize drops Unicode categories Cc, Cf, Zl, Zp, then trims; truncate the project name only to 60 code points; then append the fixed suffix (suffix and issue digits never truncated); empty name -> title exactly `uncle` | OSC injection | CAP-PY3 | n/a | CODING |
| R-3 | USER | I-4, T-8 | AC-5 | tty only (both streams) | Only the exact value `UNCLE_TERMINAL_TITLE=0` disables; unset, empty, or any other value enables. Both isatty(stdout) AND isatty(stderr) are required, plus TERM set and not dumb; if either is not a tty nothing is written. Sequences are written to stderr in the TUI and stdout in the shell; end re-checks the guard. | existing guard | CAP-PTY | stdlib pty available | CODING |
| R-4 | PLATFORM | xterm title stack | AC-2 | Restore | CSI 22;2 t / 23;2 t with project-only fallback | support undetectable | none | design choice, revisable | CODING |
| R-5 | REPOSITORY | CLAUDE.md signing | AC-9 | No signing in fixtures | none needed; no git fixtures | rule | none | n/a | CODING |

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/terminal_title.py` (new) | Builder (strip Cc/Cf/Zl/Zp, trim, truncate project name only to 60 code points, then append suffix; empty -> `uncle`), guards, writers, CLI | I-1,I-3,I-4 | Low | terminal-title-test.py |
| `uncle_tui.py` | Import helper; `_write_title`/`_begin_title`/`_end_title` use it; idle title and stack in `__main__`; status bar uses `project_name` | BH-1..4,BH-10 | Medium: teardown ordering | terminal-title-test.py, existing TUI suites |
| `scripts/lib/terminal-title.sh` | `uncle_title_begin/end` call CLI; accept empty issue; keep `--stop-tree`, `uncle_cancel` | BH-5 | Medium: same file as cancel logic | terminal-title-test.py, cancel-stop-reason-test.sh |
| `scripts/from-issue.sh` | Keep calls; verify trap chain | BH-5 | Low | terminal-title-test.py |
| `scripts/change-workflow.sh` | Call `uncle_title_begin` also when no issue / no origin | BH-3 | Low | terminal-title-test.py |
| `scripts/stagegate.sh` | Source helper, begin after setup, chained EXIT end | BH-5 | Medium: existing traps | terminal-title-test.py, shell suites |
| `uncle` | Source helper, begin/end around line-based menu | BH-5 | Medium: existing traps | terminal-title-test.py |
| `scripts/tests/terminal-title-unit-test.py`, `terminal-title-tui-test.py`, `terminal-title-shell-test.py`, `terminal-title-mutation-test.py` (new) | Tests above | AC-1..AC-8 | None | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: builder output is `<project> · uncle` or `<project> · uncle issue #N`; sanitization drops categories Cc, Cf, Zl, Zp, then trims, before truncation; only the project name is truncated to 60 code points and the fixed suffix is appended afterwards; an empty sanitized name yields exactly `uncle`; a non-numeric or empty issue yields `<project> · uncle`; never returns empty; the helper inherits fds 1/2 unchanged and a missing or failing python3 is silent with exit 0. | BH-8 | I-1, I-3 | terminal_title.py | unit | n/a |
| AC-2: TUI sets project title on start; on exit (normal, exception, SIGTERM/SIGHUP) writes the project-only title then pops the stack, only if this process pushed; end is idempotent. | BH-1, BH-4 | I-4 | uncle_tui.py | pty TUI | two tabs |
| AC-3: during a run the TUI retitles with the issue; on run end it writes the idle title and does not pop the stack. | BH-2, BH-3 | I-2 | uncle_tui.py | TUI title test | run in worktree |
| AC-4 | BH-5 | I-1 | shell scripts | bash pty | each driver |
| Only the exact value UNCLE_TERMINAL_TITLE=0 disables titling; any other value (unset, empty, false) enables it. Titling is also off when TERM is unset or dumb. Title writes go to stderr in the TUI and stdout in shell, and only when both stdout and stderr are ttys; if either is not a tty (including only one being a tty) no title or stack bytes are written to either stream. begin pushes at most once per process and end pops only if this process pushed (idempotent, also on signal paths). | BH-6, BH-7 | I-4 | helper, bash | pty/pipe incl. only-stdout-tty and only-stderr-tty cases, double begin/double end/end-without-begin push-pop balance, SIGTERM during TUI session still pops once | uncle \| cat |
| AC-6: when UNCLE_TITLE_OWNER is set (including by the TUI or the uncle line menu, which export it when they begin), child drivers' shell uncle_title_begin/end push and retitle nothing and write nothing (any issue or none); only the owner writes titles. | BH-9 | I-5 | terminal-title.sh | bash pty | n/a |
| AC-7 | BH-10 | I-2 | uncle_tui.py | consistency | n/a |
| AC-8: defect injection. The test runs terminal_title.py from a temp copy with (a) end writing bare `uncle` and (b) sanitize disabled, and requires the suite's title assertions to fail for each mutant; this check is never cut. | all | all | tests | defect injection: mutant (a) end writes bare uncle; mutant (b) sanitize disabled; unmutated copy passes | n/a |
| AC-9 | BH-10 | E-1..E-3 | all | baseline commands | n/a |

## Implementation sequence

1. Helper module and unit tests (S1) — builder, sanitizer, guards (both stdout and stderr ttys; stream selection), once-only push/idempotent end state, CLI, tests for AC-1,AC-5,AC-7,AC-8 helper parts. Includes D-8 cases: non-numeric, empty, flag-like and very long digit issue arguments (non-digit/empty gives `<project> · uncle`; digits never truncated).
   Owns: `scripts/lib/terminal_title.py`, `scripts/tests/terminal-title-unit-test.py`
2. TUI integration (S2) — swap `_write_title`/`_begin_title`/`_end_title`, idle title and stack in `__main__`, status-bar name via helper; pty TUI tests appended to the test file written in step 1 (shared file: step 2 builds on step 1's test module).
   Owns: `uncle_tui.py`, `scripts/tests/terminal-title-tui-test.py`
   Depends on: 1
3. Shell integration (S3) — rewrite `uncle_title_begin/end` to call the CLI; keep cancel and stop-tree intact. Begin: no-op when `UNCLE_TITLE_OWNER` names a live ancestor PID (validated, not merely non-empty; a forged or stale value is ignored) or when `UNCLE_TITLE_ACTIVE` is already 1 (second begin); drivers push only when the owner is unset. Issue is passed to the CLI only if it matches `^[0-9]+$` (D-8), otherwise no issue; the root is read only from UNCLE_PROJECT_ROOT/cwd, never argv. End: acts only when `UNCLE_TITLE_ACTIVE`=1 from this shell's own begin, clears it first (idempotent), re-checks the full tty/TERM guard and writes nothing on failure, and is reached from the EXIT trap on every exit path including `uncle_cancel` and SIGTERM/SIGHUP. Tests cover owner-set no-op, end-without-begin, issue `12a`/empty/`--x` yielding the no-issue title, root never read from argv, and a forged owner PID being ignored.
   Owns: `scripts/lib/terminal-title.sh`
   Depends on: 1
4. Driver and launcher wiring (S4) — from-issue.sh, change-workflow.sh, stagegate.sh, uncle; chain traps. The `uncle` line menu exports UNCLE_TITLE_OWNER after its begin so child drivers push and retitle nothing. Cut order if time expires: uncle line-menu wiring, then stagegate.sh wiring.
   Owns: `scripts/from-issue.sh`, `scripts/change-workflow.sh`, `scripts/stagegate.sh`, `uncle`
   Depends on: 3
5. Shell pty tests and defect injection (S5) — AC-4,AC-6 (including owner set => zero bytes written, and end only after a matching push), grep guard, mutation check.
   
   Steps 2 and 3 are independent of each other and may be batched. Protected verification paths: `scripts/tests/terminal-title-test.py`. Verification commands: the two baseline commands.
   Owns: `scripts/tests/terminal-title-shell-test.py`, `scripts/tests/terminal-title-mutation-test.py`
   Depends on: 2, 3, 4

## 21. Scope cuts under time pressure

Cut first: line-menu wiring in `uncle`, then stagegate.sh wiring. Never cut sanitization, tty guards, or the AC-8 defect-injection test (mutants (a) end writes bare `uncle`, (b) sanitize disabled).

## 22. Risks and unresolved questions
- Existing EXIT traps in stagegate.sh/uncle: read and chain (decision made: chain). No blocking questions.
- Terminals without title stack keep the project-only title after exit: accepted per request.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Owner semantics conflicted with BH-3/BH-5/BH-9; a single rule resolves it. | s1.1 D-6/D-7 rewritten: when UNCLE_TITLE_OWNER is set, driver begin/end write nothing; only the TUI retitles at run start and end; AC-3/AC-6 updated. |
| AR-002 | Accepted | Exit path must be defined for never-pushed, signal and repeat cases. | s1.1 D-3 now: end writes project-only title and CSI 23;2 t only if this process pushed; runs in finally and on SIGTERM/SIGHUP; idempotent; AC-2 and step-3 updated. |
| AR-003 | Accepted | Non-numeric/empty issue and truncation scope were ambiguous; a fixed rule is needed so the suffix always survives. | Section 1 (s1.1) gains title rules: non-numeric/empty issue gives no-issue title; project name truncated so the full title is at most 60 chars, suffix kept. |
| AR-004 | Accepted | Project-name edge cases (relative/empty root, '/', empty after sanitizing) were undefined and conflicted with project-first format. | Section 1 (s1.1) gains project-name rules: ignore non-absolute UNCLE_PROJECT_ROOT, use cwd; empty name yields exactly `uncle`. |
| AR-005 | Accepted | Opt-out and stream rules were unspecified; the settled rule is clear and consistent with the existing both-ttys guard. | Edit R-3 mechanism and AC-5 requirement to say only exact 0 disables, writes go to stdout, and stdout and stderr must both be ttys. |
| AR-006 | Accepted | Child drivers launched from the line menu would push the stack again; exporting the owner variable prevents mismatched pops. | Edit s1.1 D-7 text and AC-6 requirement so the uncle line menu exports UNCLE_TITLE_OWNER and child drivers push and retitle nothing. |
| AR-007 | Accepted | Plan left driver behavior undefined when the TUI skipped its own begin; ownership must reflect an actual push. | Section 1 D-6/D-7 amended: TUI exports UNCLE_TITLE_OWNER only if it actually began; drivers push only when it is unset. |
| AR-008 | Accepted | Repeat-call and exit-path behavior was unspecified; idempotent end and no-op second begin are needed for balanced push/pop. | Section 12 and step 3 amended: end idempotent and run from EXIT trap on every exit path incl. uncle_cancel; second begin is a no-op. |
| AR-009 | Accepted | The old bash guard rejected non-digit issues while the plan accepts empty ones; a single rule is needed. | Section 8 (s8.1) and AC-1 now state a non-numeric issue is treated as empty, giving `<project> · uncle`. |
| AR-010 | Accepted | Bash now spawns python3 per begin/end, so fd inheritance and missing-python3 behavior must be defined. | Section 1 (s1.1) and R-1 state the helper inherits fds 1/2 unchanged and missing or failing python3 gives silence with exit 0. |
| AR-011 | Accepted | End must not write or pop when this process never performed the matching begin, to keep push/pop balanced. | Section 1 adds rule D-8: end writes nothing unless this process's begin pushed. |
| AR-012 | Accepted | Capping only the project name keeps the issue suffix intact; whole-title truncation could cut it off. | Section 1 D-4 revised: cap project name to 60 code points, then append suffix; R-2 mechanism updated to match. |
| AR-013 | Accepted | Bidi overrides and line/paragraph separators are not C0/C1/DEL but could still corrupt a title; dropping Unicode categories Cc, Cf, Zl, Zp is a cheap, safe strengthening. | Section 1 decision D-4 and restriction R-2 now specify dropping categories Cc, Cf, Zl, Zp before truncation. |
| AR-014 | Accepted | Order and scope of truncation were ambiguous and could cut off the issue suffix. | Section 1 D-4, R-2, and AC-1 now say: strip, trim, truncate only the project name to 60 code points, append fixed suffix; empty falls back to bare `uncle`. |
| AR-015 | Accepted | The CLI is a separate process and must itself enforce the digits-only issue and take the root from the environment, since bash callers may pass arbitrary values. | Section 1 now states the CLI accepts an issue only if it matches ^[0-9]+$ (else no issue) and reads the root only from UNCLE_PROJECT_ROOT/cwd, never argv. |
| AR-016 | Accepted | end must not emit bytes to a non-tty and a forged or stale UNCLE_TITLE_OWNER must not silence the title or pop another process's stack. | Section 1 now states end re-checks the full guard and writes nothing on failure, and UNCLE_TITLE_OWNER is honored only when it names a live ancestor PID; step-3 implements it. |
| AR-017 | Accepted | Push/pop balance for double begin, end without begin, and signal paths was unspecified; a per-process pushed flag and idempotent end fix it. | Section 1 adds D-8 (push at most once, pop only if pushed, idempotent end, signal paths); R-4-adjacent AC-2 and step-1 updated. |
| AR-018 | Accepted | Output stream and one-tty-only behavior were unnamed and R-3/AC-5 disagreed. | Section 1 adds D-9 (stderr in TUI, stdout in shell, both must be ttys, else silent); R-3 and AC-5 updated to agree. |
| AR-019 | Accepted | Run-end versus session-exit behavior must be unambiguous and match BH-4. | Section 1 (s1.1) D-3/D-6 state: exit writes project-only title then CSI 23;2 t; run end writes only the idle title, no pop. |
| AR-020 | Accepted | The cap's scope, unit and order against sanitizing must be defined so tests have a single oracle. | Section 1 (s1.1) D-4 rewritten: strip, trim, truncate project name only to 60 code points, then append suffix; s16.1 R-2 and AC-1 aligned. |
| AR-021 | Accepted | The expected title for non-numeric, empty or very long issue input was undefined; a single rule resolves it. | Section 1 gains decision D-8 (non-digit/empty issue = no issue, digits never truncated); step-1 tests cover it. |
| AR-022 | Accepted | The stateless CLI cannot know whether begin pushed, so the stateful gate must live in the bash wrapper. | Section 1 gains decision D-9 (non-empty UNCLE_TITLE_OWNER makes begin/end no-ops; bash end acts only if UNCLE_TITLE_ACTIVE=1); step-3 text updated. |
| AR-023 | Accepted | AC-8 mutants were unnamed and defect injection was on the cut list, so the critical test could be dropped. | Named mutants (a) end writes bare uncle and (b) sanitize disabled in s12.1 and AC-8; removed defect injection from s20.1 cut list. |
