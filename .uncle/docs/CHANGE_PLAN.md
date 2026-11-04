# Change Plan

Issue 151

Seeded from [unclehq/uncle#151](https://github.com/unclehq/uncle/issues/151).

Omitted sections: Schema/persistence (none); Migration (none); Feature flag (none, additive); Concurrency (none beyond per-invocation temp dir); Observability (none)

## 1. Selected technical approach

In `uncle`, add a shared shell function `read_stdin_option OPT` used by `--application` and `--housekeeping`. In the argument loop, after `shift`, a value exists iff `$# -gt 0 && "$1" != --*`; otherwise the option only records a pending stdin option (`UNCLE_PENDING_STDIN_OPT`). After the loop has parsed every argument successfully, `read_stdin_option OPT` runs once: refuse on TTY, require python3, make `UNCLE_CR_DIR`, call `housekeeping_input.py --label OPT PRIVATE_DIR`, set `UNCLE_STARTUP_TEXT_FILE`. Add `--application=*` / `--housekeeping=*` cases taking the value after `=`. `housekeeping_input.py` gains optional `--label OPT` (default `--housekeeping`) for messages and strips exactly one trailing newline. `uncle_tui.py` `create_app` falls back to the text file as `housekeeping` already does.

Ordering (AR-002): in the arg loop, `--application` / `--housekeeping` without a value only record a pending stdin option (`UNCLE_PENDING_STDIN_OPT`); the mutual-exclusion check still runs at option entry. `read_stdin_option` (TTY refusal, python3 check, mktemp, helper call) runs once, after the loop has parsed every argument successfully. An unknown argument (e.g. `--application --bogus < f`) therefore exits 1 with `Unknown argument` before any stdin read or temp-file creation, and a test asserts that stdin stays unread and no temp file exists. AR-015 rule: positional text beginning with `--` is never text. The launcher treats such an argument as an option (so for `--OPT --text` the pending stdin option is kept and `--text` is then an unknown argument, exiting 1 before any stdin read); text starting with `--` must be given as `--OPT=--text`. The unknown-argument error for an argument starting with `--` adds the hint: `to pass text beginning with --, use --application=TEXT or --housekeeping=TEXT`.

## 2. Alternatives considered
- Extend `change_request_stdin.py` with a destination: touches the out-of-scope `--change-request` path and its CHANGE_REQUEST.md check.
- New common module imported by both helpers: more churn than needed; parity is instead pinned by a test.
- Keep `$(cat)`: rejected, skips limits and loads text into env.

## 3. Why preferred
Smallest surface; reuses an existing validated reader; `--change-request` remains byte-identical in behavior; stdin text avoids env/argv.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
`scripts/lib/change_request_stdin.py`, `--issue` parsing, driver scripts, existing assertions in existing tests.

## 6. Data-flow changes

Stdin -> `housekeeping_input.py` (validate, strip one newline) -> 0600 file in the 0700 `UNCLE_CR_DIR` mktemp dir -> `UNCLE_STARTUP_TEXT_FILE` -> TUI `_read_startup_text_file` -> create_app/housekeeping. Value case: argv -> `UNCLE_STARTUP_TEXT` as today, with `UNCLE_STARTUP_TEXT_FILE` empty. Env contract (AR-003, AR-007): in the stdin case the launcher sets only `UNCLE_STARTUP_TEXT_FILE` and leaves `UNCLE_STARTUP_TEXT` empty; in the value case it sets only `UNCLE_STARTUP_TEXT` and leaves `UNCLE_STARTUP_TEXT_FILE` empty. Precedence: if both are set (e.g. caller-exported env), the TUI reads the file and ignores `UNCLE_STARTUP_TEXT`. Cleanup (AR-012): the text file exists only inside the 0700 dir at mode 0600 and is removed on every exit path. The EXIT trap removes the dir on non-exec exits; because `exec` replaces the shell and the trap never fires, the TUI deletes the text file and its private dir right after reading it.

## 8. Interface changes

CLI: `--application [TEXT]`, `--application=TEXT`, `--housekeeping=TEXT`. Helper: `housekeeping_input.py [--label OPT] PRIVATE_DIR [--text TEXT]` (label optional; old invocation valid). Usage and docs updated. D-1 decision: TTY error text: `Error: --OPT requires TEXT or piped stdin (empty input): use --OPT "TEXT" or pipe/redirect, e.g. --OPT < file.md`. The D-1 message, including the substring `empty input`, is used for both `--application` and `--housekeeping`, and tests assert that substring for both options.

## 10. Compatibility

Value forms unchanged; housekeeping TTY message retains `empty input`; `UNCLE_STARTUP_TEXT` still set in value case (only `UNCLE_STARTUP_TEXT`, no file). D-2: housekeeping stdin text now arrives via file not env: only `UNCLE_STARTUP_TEXT_FILE` is set and `UNCLE_STARTUP_TEXT` is empty in that case; TUI already supports it. D-6: `UNCLE_STARTUP_TEXT_FILE` takes precedence over `UNCLE_STARTUP_TEXT` in the TUI; a test sets both and asserts the file text is used. No `--application` message retains `requires an argument` (bare `--application` now reads stdin or gives the D-1 TTY message); any existing assertion on that text is recorded in IMPLEMENTATION_NOTES.md as a deviation, not silently edited.

D-6 (exception to the 'value forms unchanged' statement above): a positional value beginning with `--` (e.g. `--application "--foo bar"`, which works today) is no longer taken as text. It is treated as the next option, and the option itself falls back to stdin. This regression is accepted and documented: text beginning with `--` must use the `=` form (`--application="--foo bar"`, `--housekeeping=--text`). It is pinned by a test in launcher-stdin-text-test.sh that asserts the positional form does not deliver the text and the `=` form does. Usage text and docs state the `=` form for such text.

## 12. Error and recovery

Helper failure exits 1 before any action; `UNCLE_CR_DIR` cleanup by the existing EXIT trap on non-exec exits. On the exec path the trap does not fire, so the TUI deletes the 0600 text file and its private dir after reading it (AR-012); a test asserts no residue after both a normal exit and an exec'd TUI run. `--application=` empty refused as empty. D-3: if python3 is missing, `Error: --OPT requires python3` (matches `--change-request`).

## 14. Rollback plan
Revert the commit (launcher, helper, TUI, docs, tests). No state to migrate.

## 16. Automated-test strategy

New `scripts/tests/launcher-stdin-text-test.sh` (fake python3 TUI as in launcher-args-test.sh): S-1..S-9, S-11, S-12 for both options, option orders, boundaries (1048576 pass, +1 fail, NUL, control, tab/LF/CR pass, invalid UTF-8), parity with `change_request_stdin.py`, pty TTY test with timeout, I-4 unread-pipe test, no TMPDIR residue, doc greps. AR-001 case: `--OPT --other` with empty non-TTY stdin (e.g. `< /dev/null`) exits 1 with `Error: --OPT text cannot be empty` for both options, and `--OPT=--text` delivers `--text` as the text. New case in `scripts/tests/startup-action-test.py` for create_app with text file. Defect injection per AC-11 recorded in IMPLEMENTATION_NOTES.md. Authority note: edits to existing test files are additive only; no existing assertion changes expected (R-3). Before step 3, the existing housekeeping stdin cases are run against the new validated reader; any conflict (control chars, CRLF, large text, env-vs-file delivery) is stop-and-ask, never an assertion edit.

AR-018 test: for both options, the empty value forms (`""` and `--OPT=`) are run with non-empty piped stdin; the test asserts exit 1, `text cannot be empty`, that the pipe was not consumed (writer still holds unread bytes), that stdin is never used as a fallback, and that no helper call or temp file occurred.

AR-015 test: `--application --text-like` and `--housekeeping --text-like` are not taken as text (unknown-argument exit 1 with the `=` form hint, or stdin read when the argument is a known option); `--application=--text-like` and `--housekeeping=--text-like` succeed with that exact text.

## 17. Regression-test strategy
Existing launcher-args-test.sh, housekeeping-launcher-test.sh, launcher-tui-lock-test.sh and startup-action-test.py must pass unchanged; verification commands are the two runners in the baseline.

## 18. Manual verification
Pipe a multi-paragraph brief into `uncle --application` (and `< file --housekeeping`); confirm the build starts from it. Run `uncle --application` in a real terminal; confirm immediate refusal.

## 20. Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Invariants I-2 | I-2 | Never block on TTY stdin | `[[ -t 0 ]]` before any read | feasible; same as uncle:133 | CAP-bash | CODING |
| R-5 | DESIGN | Adversarial review AR-013 | I-2 | Stdin read has no timeout | No timeout is added. The read is bounded in bytes (cap 1048576 + 1) but not in time. A non-TTY stdin that never reaches EOF (open FIFO, idle CI pipe) blocks until the writer closes it or the caller interrupts. This is the same behavior as `--change-request`. The limitation is stated in the usage text and README, and no test asserts a timeout. | The `[[ -t 0 ]]` guard covers only the interactive case. A timeout would be a new behavior and would diverge from `--change-request`. | CAP-bash | CODING |
| R-2 | USER | CHANGE_REQUEST Non-goals | S-13 | `--change-request` unchanged | do not edit change_request_stdin.py or its case | inspected uncle:128-146 | CAP-bash | CODING |
| R-3 | REPOSITORY | CLAUDE.md rule 7 / protected tests | AC-8 | Do not weaken tests | additive tests only; keep `empty input` substring; run existing housekeeping stdin cases before step 3 and treat any conflict as stop-and-ask | existing test greps it | CAP-bash | CODING |
| R-4 | DESIGN | CHANGE_REQUEST Reuse | I-3 | Reuse reader, no bare `cat` | `housekeeping_input.py --label` | inspected symbol lines 26-50; scope: I-3 identical validation applies to the stdin path only. Value-form text (argv, --OPT=VALUE) is NOT passed through housekeeping_input.py --text and stays unvalidated by the launcher, as today (preserves compatibility). | CAP-python3 | CODING |

Runner binding: bash + python3 (installed; launcher already requires python3). Pty test uses python3 `pty` module, as housekeeping-launcher-test.sh does. No live-verification prerequisites; no credentials.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle` | stdin/`=` handling for both options, usage text | core request | Medium: arg-loop parsing | new + existing launcher tests |
| `scripts/lib/housekeeping_input.py` | `--label`, strip one trailing newline | shared validated reader | Low | new boundary/parity tests |
| `uncle_tui.py` | create_app falls back to startup text file | stdin text delivery | Low | startup-action-test.py |
| `README.md`, `docs/quickstart.md` | document stdin form | S-10 | None | doc greps |
| `scripts/tests/launcher-stdin-text-test.sh` | new suite | AC coverage | None | itself |
| `scripts/tests/startup-action-test.py` | add create_app file case | AC-10 | None | itself |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 (including: a next argument beginning with `--` is never text; with empty non-TTY stdin the launcher exits 1 with `Error: --OPT text cannot be empty`, and `--OPT=--text` supplies such text) | S-1, S-2, S-4 | I-1 | uncle | launcher-stdin-text-test.sh | pipe brief |
| AC-2 | S-6 | I-1, I-3 | uncle | launcher-stdin-text-test.sh | pipe housekeeping |
| AC-3 | S-5 | I-2 | uncle | pty case (both --application and --housekeeping; asserts the D-1 message including `empty input` for both) | real terminal run |
| AC-4: stdin text for --application and --housekeeping is validated identically (size cap, UTF-8, no NUL/control, non-empty) via housekeeping_input.py; the size cap of 1048576 applies to raw stdin bytes before CRLF normalization and newline stripping (1048576 bytes pass, 1048577 fail); value-form text (argv, --OPT=VALUE) is explicitly unvalidated and unchanged. | S-7 | I-3 | housekeeping_input.py | boundary + parity (raw-byte cap: 1048576 pass, 1048577 fail, 1048576 bytes ending in newline passes only if total raw bytes <= cap) | n/a |
| AC-5: Empty value forms (`--OPT ""` and `--OPT=`) are refused with `Error: --OPT text cannot be empty` and exit 1 without reading stdin; `--OPT=` never falls back to stdin. Stdin is left unread (I-4). | S-3, S-8 | I-4 | uncle | launcher-args-test.sh:45, unread-pipe test, empty-value-form test: `--application ""`, `--application=`, `--housekeeping ""`, `--housekeeping=` each with a piped non-empty stdin; assert exit 1, empty-text error, stdin unconsumed, no temp file | n/a |
| AC-6 | S-11 | I-1 | uncle | launcher-stdin-text-test.sh (incl. AR-015: `--OPT --foo` never text, hint names `=` form; `--OPT=--foo` works) | n/a |
| AC-7: on the stdin path only, housekeeping_input.py normalizes CRLF/CR to LF, then strips exactly one trailing LF, then applies the emptiness check; the --text path is never stripped. | S-12 | I-3 | housekeeping_input.py | launcher-stdin-text-test.sh: stdin 'x\r\n' and 'x\n\n' yield 'x' and 'x\n'; '\n' alone is refused as empty; --text 'x\n' is not stripped | n/a |
| AC-8 | S-9, S-13 | I-5 | uncle | existing suites, launcher-stdin-text-test.sh: second mode option with piped stdin exits 1 with mutually-exclusive error, stdin left unread, no temp file | n/a |
| AC-9 | S-10 | n/a | docs, usage | doc greps | read help |
| AC-10 | S-1 | I-3 | uncle_tui.py | startup-action-test.py | pipe brief |
| AC-11 | S-7 | I-3 | tests | defect injection | n/a |

## Implementation sequence

1. Shared reader: add `--label` and single trailing-newline strip to the helper.
   Stdin processing order (AR-004): (1) cap check on raw bytes: read CAP+1 bytes and reject if more than 1048576, so exactly 1048576 raw bytes passes while a 1048576-byte body plus a trailing newline fails; (2) UTF-8 decode; (3) normalize CRLF/CR to LF; (4) strip exactly one trailing LF (stdin branch of housekeeping_input.py only; `--text` is never stripped); (5) control-character check; (6) emptiness check. The cap applies before decoding, CRLF normalization and newline stripping. Boundary tests pinned for 1048576 and 1048577 raw bytes.
   (IDs R-4; D-4: label defaults to old text)
   Owns: `scripts/lib/housekeeping_input.py`
2. TUI: create_app reads the text file when no text is given. Owns two rules of the env contract: when UNCLE_STARTUP_TEXT_FILE is set the TUI prefers it over UNCLE_STARTUP_TEXT, and after reading the file the TUI deletes it and its private dir (exec skips the launcher's EXIT trap). Step 3 owns the launcher side (UNCLE_STARTUP_TEXT empty in the stdin case); the two are paired.
   Independent of step 1
   Owns: `uncle_tui.py`
3. **Existing housekeeping stdin conflict check** — Before editing `uncle`, run the existing housekeeping stdin cases (housekeeping-launcher-test.sh, launcher-args-test.sh) and review them for stdin inputs with control characters, CRLF, large text or env-delivered text, against the validated reader from step 1 (`housekeeping_input.py` stdin path). Record the result in IMPLEMENTATION_NOTES.md. If any existing assertion conflicts with the stricter validation or with file-based text delivery, STOP and ask the user; do not edit existing assertions and do not proceed to step 3.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 1, 2
4. Launcher: shared stdin function, `=` forms, usage text.
   
   Parse ordering: the argument loop only records a pending stdin option; `read_stdin_option` is invoked once after the whole argument list parses successfully, so unknown-argument errors exit 1 before any stdin read or temp file/dir is created. The mutually-exclusive check stays at the top of every mode-option case and runs before `read_stdin_option`: a second mode option (`--application --application`, `--application --housekeeping`, `--housekeeping --application`, etc.) exits 1 with the mutually-exclusive error before any stdin is read, before python3 is invoked and before any temp file is made. AC-8 tests include a case proving no stdin read or temp file on a second mode option.
   
   Value rule: after `shift`, only a next argument beginning with `--` is an option (stdin mode); any other next argument, including `-h`, `verify`, single-dash words and the empty string, is the value. Empty value forms (`--OPT ""` and `--OPT=`) are refused with `Error: --OPT text cannot be empty` without reading stdin and never fall back to stdin. Add launcher tests for `--application -h`, `--application verify` and `--application ""` treated as values, and for `--OPT=` refused without stdin read (AC-5).
   
   Env contract: stdin case sets only `UNCLE_STARTUP_TEXT_FILE` and leaves `UNCLE_STARTUP_TEXT` empty (TUI prefers the file); value case sets only `UNCLE_STARTUP_TEXT`. Tests assert both the stdin and value cases for both options.
   
   Temp file: stays in the 0700 `UNCLE_CR_DIR` at 0600; the EXIT trap covers non-exec exits and the TUI removes the file and dir after reading, since exec skips the trap (AR-012).
   
   Usage text documents that text beginning with `--` requires the `=` form (D-6); a test pinning this is added in step 5.
   Owns: `uncle`
   Depends on: 1, 2, 3
5. Docs.
   Owns: `README.md`, `docs/quickstart.md`
   Depends on: 4
6. Tests: new launcher suite and startup-action case. The fake TUI records both UNCLE_STARTUP_TEXT and UNCLE_STARTUP_TEXT_FILE, checks the file exists, then deletes it as the real TUI does. Cases: stdin case has empty TEXT and set FILE; value case has TEXT set and FILE empty; both set -> file wins; `--application --bogus` and second-mode-option cases with piped stdin (exit 1, stdin unread, no temp file); helper tests for stdin vs --text newline handling, CRLF order, raw-byte cap with trailing newline and CRLF-expanded input at cap; value-form text unvalidated; no TMPDIR residue after exec and failure paths.
   Owns: `scripts/tests/launcher-stdin-text-test.sh`, `scripts/tests/startup-action-test.py`
   Depends on: 4
7. Defect injection and notes: run new suite with a bare-`cat` defect, revert, record.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 6

## 21. Scope cuts under time pressure

Cut first: `--opt=VALUE` form (S-11), then startup-action-test.py extra case, then quickstart edits. Never cut: TTY refusal, validation, option-as-text fix, the rule that a `--`-prefixed next argument is never text.

AR-015: the `=`-form hint in the unknown-argument error is cut together with the `--opt=VALUE` form (S-11).

## 22. Risks and unresolved questions

- Inherited non-TTY stdin (cron/CI `/dev/null`) yields `text cannot be empty`: accepted as correct; message names the option.
- Existing test assumptions about housekeeping env text are unverified beyond lines 1-40; step 5 re-runs suites and records any conflict as a deviation rather than editing assertions.
- Trailing-newline decision D-5: on the stdin read path only (inside housekeeping_input.py), normalize CRLF/CR to LF, then strip exactly one trailing LF, then apply the emptiness check; `--text` input is never stripped (a test pins both).

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The next-argument-starting-with-`--` case with an empty non-TTY stdin was unspecified; the proposed rule is consistent with the existing option-vs-text design. | s1.1 now states a `--`-prefixed next argument is never text, stdin is read, empty input exits 1; s11.1 adds a test and AC-1 reflects it. |
| AR-002 | Accepted | Real gap: reading stdin inside the arg loop would consume input and create a temp file before a later unknown argument exits 1. | Added a parse-ordering block to s1 and updated step-3 so stdin is read only after the whole argument list parses. |
| AR-003 | Accepted | Precedence between UNCLE_STARTUP_TEXT and UNCLE_STARTUP_TEXT_FILE was unspecified; the file must win and the launcher must keep the env var empty in the stdin case. | Edited s6.1 data flow and s8.1 compatibility to state file-wins precedence and empty UNCLE_STARTUP_TEXT in the stdin case. |
| AR-004 | Accepted | The strip position relative to normalization, emptiness check and --text was undefined; the proposed order is sound and consistent with the existing reader. | Step 1 and AC-7 now fix order: normalize CRLF/CR, strip one trailing LF (stdin only), then emptiness check; --text never stripped. |
| AR-005 | Accepted | The existing exclusivity check runs on option entry, so the plan must pin that it precedes any stdin read for repeated or mixed mode options. | step-3 text requires the mutual-exclusion check before read_stdin_option; AC-8 tests add a case proving no stdin read or temp file on a second mode option. |
| AR-006 | Accepted | The TTY message replaces the old `requires an argument` text, so the plan should state explicitly that no --application message keeps it. | s7.1 and s8.1 state no --application message retains `requires an argument`; any existing assertion on it is recorded as a deviation. |
| AR-007 | Accepted | The plan left the env/file contract for startup text unspecified; defining it removes ambiguity and a precedence hazard. | Edit s6.1 and s8.1: stdin case sets only UNCLE_STARTUP_TEXT_FILE with empty UNCLE_STARTUP_TEXT; value case sets only UNCLE_STARTUP_TEXT; TUI prefers the file. |
| AR-008 | Accepted | The validated reader is stricter than the old whitespace-only check, so existing housekeeping stdin cases could conflict; checking them before the launcher edit is cheap. | New step before step 3 runs existing housekeeping stdin cases; any conflict is stop-and-ask. Step 3 depends on it. R-3 and s11.1 updated. |
| AR-009 | Accepted | The `--*` guard does regress `--application "--foo bar"`, which works today; the regression is a deliberate trade for stdin mode and should be stated and pinned. | Added a Compatibility exception (s8) and a step-3 requirement for a test pinning that text beginning with `--` needs the `=` form. |
| AR-010 | Accepted | Real gap: reading stdin inline in the arg loop could consume stdin and create a temp file before a later unknown argument exits. | Section 1 and step 3: the loop only records a pending stdin option; stdin is read after the whole argument list parses successfully. |
| AR-011 | Accepted | housekeeping_input.py shares one validation path for --text and stdin, so the strip must be explicitly confined to the stdin read path. | Edit s1.1 and s19.1.i3 to state the strip applies only on the helper's stdin read path, never to --text. |
| AR-012 | Accepted | exec replaces the shell so the EXIT trap never fires; the stdin text file would otherwise leak. | Edit s6.1, s9.1 and step-3 to state the file lives in a 0700 dir at 0600 and the TUI deletes it after reading. |
| AR-013 | Accepted | A non-TTY stdin that never closes blocks the read; a timeout would add behavior the request does not ask for, so the plan documents it as accepted. | Adds restriction R-5 in section 20 (s14.1): no stdin read timeout, blocking on a never-closing non-TTY stdin is accepted and documented. |
| AR-014 | Partially accepted | Validating value-form text would change working argv behavior (compatibility); instead the plan states I-3 covers stdin only and value-form text is unvalidated by the launcher. | R-4 rationale and AC-4 requirement now scope I-3 validation to the stdin path and state value-form text (argv, --OPT=VALUE) is not validated. |
| AR-015 | Accepted | A next argument starting with `--` is never positional text; users need the `=` form, and the error should point to it. | s1.1 states the rule and error hint; s11.1 and AC-6 add a test for `--OPT --text` and the hint. |
| AR-016 | Accepted | Ordering of normalization, strip and empty check was unspecified; the proposed order is sound and safe for --text. | Edit step-1, AC-7 and D-5 (s19.1.i3) to fix order: CRLF/CR to LF, strip one trailing LF on stdin path only, then empty check. |
| AR-017 | Accepted | The helper reads CAP+1 raw bytes and checks length before decoding, so the cap counting raw bytes before normalization and strip is the existing behavior and must be pinned. | Step-1 and AC-4 now state the cap applies to raw stdin bytes before CRLF normalization and newline stripping; boundary tests pinned. |
| AR-018 | Accepted | The plan did not say whether stdin is read for empty value forms; making it explicit removes ambiguity in the I-4 test. | Edit AC-5, step-3 and s11 to state that empty value forms ("" and --OPT=) are refused without reading stdin and never fall back to stdin, and add tests. |
| AR-019 | Accepted | The value rule needs an unambiguous definition so -h, verify, single-dash words and empty string are all values, matching the existing --housekeeping check. | Step 3 text states: only arguments beginning with -- are options; any other next argument (including -h, verify, empty string) is the value. |
| AR-020 | Rejected | Reading stdin at the option contradicts AR-002 and AR-010, which settle that stdin is read only after the whole argument list parses, so parse errors win and no temp file is made. | No edit; parse-versus-read ordering is owned by the AR-002/AR-010 dispositions. |
| AR-021 | Accepted | The D-1 message already contains `empty input` for both options; making that binding and asserted for both removes the mismatch with AC-3, which only required it for housekeeping. | s7.1 states the D-1 message with `empty input` applies to both options; AC-3 tests assert it for both. |
