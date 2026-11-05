# Change plan - Issue 160 `--noui`

Issue 160

Seeded from [unclehq/uncle#160](https://github.com/unclehq/uncle/issues/160).

Omitted sections: Schema/persistence (none); Migration (none); Feature flag (the flag itself is the containment); Observability beyond stdout/stderr lines (none)

## 1. Selected technical approach

Headless runner is Python (`scripts/lib/uncle_headless.py`) launched by `uncle` instead of `uncle_tui.py`; curses is never imported. The launcher already resolves startup action, text file, and mode and exports them; the headless runner reads that same environment, performs the TUI's non-UI run setup, and runs the driver with the existing streaming/escape filter. Shared pure logic lives in `scripts/lib/run_duties.py` and is called by both TUI and headless.

Decisions:

| ID | Decision | Reason |
|---|---|---|
| D-1 | Entry point: launcher execs the headless Python module directly; no TUI `--noui` mode | avoids loading curses (I-3, N-1) |
| D-2 | Keep `--noinput`; refuse `--noui --noinput`; document the difference | avoid confusion, no behavior change (P-2) |
| D-3 | Keep the line menu as the non-tty fallback | P-3; out of scope to retire |
| D-4 | Text output only; JSON events deferred | CR non-goal |
| D-5 | Output rule: driver stderr is merged into stdout; every output line (including stage banners, which pass through unchanged otherwise) is prefixed with elapsed time; values of env vars whose names match *KEY*/*TOKEN*/*SECRET*/*PASSWORD* are redacted from all streamed output | N-7, CR section 10; resolves D-5 vs AC-3 conflict, one uniform rule |
| D-6 | Attended requires a tty on stdin; otherwise refuse exit 2. Also refuse exit 2, before any write: multiple startup actions, empty startup text, `--attended` without `--noui`, and `--change-request` combined with `--attended` (stdin carries the CR text, so no tty is available for gates). EOF or a blank answer at an attended gate means not approved: the run stops and exits 3. | piped stdin cannot safely answer gates; `--change-request` consumes stdin; ambiguous input combinations must be refused deterministically (AR-004) |
| D-7 | Parity target for `--application` is the direct brief path (no supervisor draft) | matches `uncle_tui.py:4205` |
| D-8 | Existing uncommitted prior attempt is audited, then completed in place; nothing is discarded unread. The regression baseline is committed HEAD (not the working tree): behavior of `uncle` and `uncle_tui.py` is compared against HEAD. | it already matches the file layout; uncommitted edits to `uncle` and `uncle_tui.py` must not become the accepted baseline by default |
| D-9 | Shared `run_duties.build_driver_command(action, text, attended, root_dir, issue_mode)` mirrors `cmd_for`; TUI `cmd_for` delegates to it. `action` must be one of the four allowlisted startup actions; any other value raises and the runner exits 2. Driver argv is built only from fixed driver names under `root_dir` plus the resolved text, never from env-supplied paths. | I-3 |
| D-10 | Worktree creation for non-issue runs via the same `worktrees.sh worktree_auto` call, extracted to a shared helper in `run_duties` and used by TUI `_enter_run_worktree` | N-9, B-5 |

## 2. Alternatives considered
(a) `uncle_tui.py --headless` mode: loads curses module and the 8k-line TUI; rejected. (b) Run drivers directly from bash: duplicates startup text/worktree/finish logic in bash; rejected.

## 3. Why preferred
Smallest surface, honors I-3 by extracting rather than duplicating, no curses import.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
All drivers (`scripts/*.sh` workflows), stage libs, TUI dialogs, config editing, line menu, `desktop_launch.py` and `terminal_title.py` (called, not changed).

## 6. Data-flow changes
launcher env -> `uncle_headless.main` -> `run_duties` (text resolve, brief/CR write, worktree, argv) -> driver subprocess -> filtered stream -> `BannerCollector` -> finish summary, desktop decision -> exit code.

## 8. Interface changes

New flag `--noui` and env `UNCLE_NOUI=1` (exactly `1`). Exit codes per AC-4. `uncle_headless.py` internal CLI: `[--attended] [--root DIR] -- DRIVER...` remains for tests; with no `--`, it derives the driver from `UNCLE_STARTUP_ACTION` (new). `UNCLE_STARTUP_ACTION` is a trust boundary: it must be exactly one of the four allowlisted actions, otherwise the runner exits 2 before any write; the driver argv is never built from env-supplied paths (only fixed driver names under the root plus the trust-checked text file).

## 10. Compatibility

No behavior change without the flag; `uncle_tui.finish_decision` re-export retained; `_read_banner` delegates with identical results. Headless output format: single merged stdout/stderr stream, each line prefixed with elapsed time, escapes stripped, secret env values redacted. Every `uncle_tui` attribute referenced by existing tests (including `cmd_for`, `_enter_run_worktree`, `_read_banner`, `finish_decision`, and any other name found by grepping `scripts/tests` and TUI suites for `uncle_tui.` references and patches) stays defined on `uncle_tui`. Delegation to `run_duties` goes through the `uncle_tui` name (thin wrapper that looks up and calls the shared function at call time), so `mock.patch('uncle_tui.<name>')` still takes effect. Step 1 audit produces this attribute list in IMPLEMENTATION_NOTES.md, and step 3 must not remove or rebind any listed name.

Secret redaction (AR-012): `run_duties.redact_secrets(line, env)` is a pure function applied by `uncle_headless._stream` to every driver output line (stdout with stderr merged), after `EscapeFilter` and before the elapsed-time prefix and write. It replaces every occurrence of the value of any environment variable whose name case-insensitively contains KEY, TOKEN, SECRET or PASSWORD with `[REDACTED]`; values shorter than 8 characters are not redacted, to avoid corrupting ordinary output. Tests: `run-duties-test.py` unit-tests the function (match and non-match names, short values, multiple occurrences, defect injection that disables it), and `headless-run-test.py` runs a fixture driver that echoes a secret env value and asserts, at byte level on captured stdout and stderr, that the value is absent and `[REDACTED]` is present. This adds no behavior without `--noui`; the TUI path is unchanged.

## 11. Concurrency
Driver in its own session/process group; signal handler forwards to the group; stdout streamed by a single reader; worktree locking stays in the drivers.

## 12. Error and recovery

Exit codes and precedence. Refusals exit 2 before any write; exit 2 occurs only before the driver starts (a signal during refusal/setup still yields 130/143, with no driver started). Text-file trust: the runner re-validates the text file (symlink, ownership, permissions) with the shared `run_duties` trust check immediately before reading it, never relying on the launcher's earlier validation, and exits 2 on failure with no driver started. Once the driver has started, precedence is: signal (130 for SIGINT, 143 for SIGTERM) > gate/signing stop (3) > driver nonzero or failed check (1) > finished cleanly (0). Classification is `run_duties.classify_exit(returncode, output_lines)`, which takes the driver's exit status and its streamed output lines: exit 3 is chosen when the driver exits nonzero AND the output contains the gate/signing-handoff marker (the driver's human-gate stop or signing-handoff line); every other nonzero driver exit is 1; a driver exit 0 is classified 1 if `classify_exit` finds the failed-check marker in the output (detected from the driver's own record, not scraped prose); 0 only if the driver exited 0 with no gate/signing stop, no failed check, and no signal. Signals -> 130/143: the runner forwards the signal to the driver's process group and waits a 10 s grace period, then sends SIGKILL to the group; a second signal received during the grace period kills the process group immediately with SIGKILL. `UNCLE_NOUI` with any value other than exactly `1` (empty, `0`, `true`, etc.) is ignored silently and the launcher behaves as without the flag. State untouched so `/resume` works.

## 14. Rollback plan
Revert the `--noui` block in `uncle` and the `run_duties` delegations in `uncle_tui.py`; delete `uncle_headless.py` and new tests. No persisted data or schema is affected. Verify by running both runners and comparing with baseline.

## 16. Automated-test strategy

Per AC: `run-duties-test.py` (pure functions, defect injection), `headless-run-test.py` (pipes, escapes, exit codes, signals, attended refusal, pty via `pty_helper.py`), `headless-equivalence-test.py` (TUI-path vs headless, fixture driver), `launcher-noui-test.sh` (flags, env, refusal, four actions, no curses). Tests must disable git signing in fixtures (`git -c commit.gpgsign=false`, `--no-gpg-sign`). Verification commands are the baseline's two runners. Required cases: (1) table-driven `run_duties.classify_exit` and headless tests for signal+gate, gate+nonzero, nonzero without marker, zero-with-failed-check-marker, asserting the stated precedence, each with defect injection (precedence swapped, marker ignored). (2) Fixture driver emitting the gate marker vs a plain nonzero exit asserts 3 vs 1. (3) Unattended gate: fixture driver reaches a gate with stdin that fails on read; assert exit 3, gate named on stderr, no stdin consumption, no approval record, with defect injection simulating auto-approval. (4) Refusal matrix (launcher and headless tables): multiple actions, empty text, `--attended` without `--noui`, `--attended` with `--change-request` each exit 2 before any write; EOF or blank at an attended gate exits 3. (5) Output: fixture driver writing to stdout and stderr; every line carries the elapsed prefix and both streams appear on stdout; byte-level redaction of *KEY*/*TOKEN*/*SECRET*/*PASSWORD* env values. (6) Launcher: UNCLE_NOUI=0, empty and 2 take the TUI path with no headless exec. (7) Golden test (tui-delegation-golden-test.py) includes a defect-injection case proving a mutated delegate fails it. (8) Patchability check enumerates `uncle_tui` names referenced by existing tests, asserts they exist, and asserts delegated calls resolve through `uncle_tui` so patches intercept them. (9) Text-file trust: symlinked, wrong-owner and swapped-after-launcher text files exit 2 with no driver launch. (10) Invalid UNCLE_STARTUP_ACTION (unknown, empty, path-like) exits 2 with no subprocess spawned. (11) Signals: SIGTERM-ignoring child is SIGKILLed after grace and a second signal kills immediately, with the grace configurable via an internal test-only override for speed (default 10 s); no orphans remain.

## 17. Regression-test strategy
Both full runners vs the driver baseline; targeted check that existing `finish_decision`, banner, `cmd_for` and startup tests still pass.

## 18. Manual-verification strategy
Real small build via `ssh host -T` (no pty) and `docker run` without `-t`; attended run in a real terminal. LIVE_VERIFICATION phase only; not a coding prerequisite.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CR I-4, N-7 | AC-3 | No cursor/screen escapes; env secrets never printed | `EscapeFilter` on driver output (headless writes none); a redaction pass replaces values of env vars matching *KEY*/*TOKEN*/*SECRET*/*PASSWORD* with a fixed mask before the elapsed-time prefix is added; stderr is merged into the same stream | Driver may emit escapes | CAP-PY | `uncle_headless.py:37` inspected | CODING |
| R-2 | USER | CR I-3 | AC-5, AC-7 | No duplicated duties | Shared `run_duties` | One implementation | CAP-PY | `run_duties.py:65-140` | CODING |
| R-3 | REPOSITORY | CLAUDE.md signing rules | AC-10 | Tests never sign | Fixture git flags | Avoid pinentry | CAP-GIT | CLAUDE.md | CODING |
| R-4 | DESIGN | D-6 | AC-2, AC-6 | Attended needs tty; refused input combinations exit 2 | `os.isatty(0)` check; combination check (multiple actions, empty text, `--attended` without `--noui`, `--change-request` with `--attended`) before any write; EOF/blank at gate -> not approved, exit 3 | Safe gates | CAP-PTY | `uncle_headless.py:142` | CODING (pty test); real-terminal check LIVE_VERIFICATION |
| R-5 | REPOSITORY | `scripts/run-python-tests.sh` | AC-10 | New Python tests named `<name>-test.py` | Hyphenated names | Runner pattern | CAP-PY | runner header | CODING |

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/run_duties.py` | Add `build_driver_command`, `prepare_worktree`, startup-text/CR/brief helpers, exit classification; keep existing pure helpers | I-3, N-9 | Low (new) | `run-duties-test.py` |
| `scripts/lib/uncle_headless.py` | Derive driver from `UNCLE_STARTUP_*` when no `--`; resolve text file; refuse CR existing; worktree; real desktop decision; finish summary; title; exit codes | N-1..N-11 | Medium | `headless-run-test.py`, equivalence test |
| `uncle` | Pass through to headless runner when `--noui` or `UNCLE_NOUI=1` (exactly `1`); keep refusals and help. With no `--noui` and `UNCLE_NOUI` unset or not exactly `1` (including `0` and empty), the launcher produces the identical exec argv and exported environment as before the change. | launcher | Medium (argument order) | `launcher-noui-test.sh` (enabled and disabled matrices: argv/env capture compared against committed HEAD launcher output), shell suites |
| `uncle_tui.py` | `cmd_for`, `_enter_run_worktree`, `_read_banner` delegate to `run_duties`; keep `finish_decision` re-export | I-3 | Medium-high | existing TUI suites plus `tui-delegation-golden-test.py` (exact golden match of `cmd_for` for four actions x issue/non-issue, `_enter_run_worktree` calls, `_read_banner` results) |
| `README.md` | Document flag, env, exit codes, attended, `--noinput` | AC-11 | None | launcher doc grep |
| `scripts/tests/run-duties-test.py`, `headless-run-test.py`, `headless-equivalence-test.py`, `launcher-noui-test.sh`, `pty_helper.py` | Extend to cover gaps above, defect injection | AC-1..AC-9 | Low | self |

## Traceability

Testable rule for AC-4/AC-6: unattended `--noui` never reads stdin and never records a human approval; reaching a human gate exits 3 and names the gate on stderr. Refusals (non-tty `--attended`, `--change-request` with `--attended`) exit 2. EOF or blank input at an attended gate is not approval and exits 3.

Gate rule (AR-011, applies to AC-4 and AC-6): unattended `--noui` never answers a gate. It stops at the gate, records nothing as human-approved, names the gate on stderr, and exits 3. Test: `headless-run-test.py` runs a fixture driver that blocks on a gate and asserts exit 3, the stderr gate name, no bytes written to the driver's stdin, and no approval record created.

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | N-1, N-2 | I-1 | uncle, headless | launcher-noui-test.sh | ssh/docker build |
| AC-2: Attended `--noui` requires a tty on stdin. Multiple startup actions, empty startup text, `--attended` without `--noui`, or `--change-request` with `--attended` refuse with exit 2 before any write. EOF or a blank answer at an attended gate means not approved, exit 3. | N-5, N-6 | I-5 | uncle, headless | launcher + headless tests | - |
| AC-3 | N-7 | I-4 | headless | headless-run-test.py (escape stripping, elapsed-time prefix on every line, stderr merged, byte-level secret redaction) | review output |
| AC-4: exit codes. 0 finished; 1 driver nonzero without a gate/signing-handoff marker, or a failed check; 2 refusal before the driver starts; 3 gate or signing stop (classify_exit matches the gate/signing-handoff marker in a nonzero driver run); 130/143 signal. Precedence: signal (130/143) > gate/signing stop (3) > driver nonzero or failed check (1) > 0; 2 occurs only before start. Unattended --noui never reads stdin and never answers a gate; a run reaching a human gate stops, records nothing as human-approved, names the gate on stderr, and exits 3. | N-8 | I-5 | headless, run_duties | headless-run-test.py: one case per code plus combinations (driver nonzero + gate marker -> 3; driver nonzero without marker -> 1; driver exit 0 + failed-check marker -> 1; driver exit 0 -> 0; gate marker + signal -> 130/143; signal during setup -> 130/143; refusal before start -> 2), run-duties-test.py classify_exit unit cases | - |
| AC-5: shared duties. Unattended --noui must not auto-delegate or auto-approve any human gate (I-2: delegated = delegated only when a human delegates). | N-4 | I-3 | run_duties | run-duties-test.py, injection | - |
| AC-6: Unattended `--noui` never reads stdin and never answers a human gate; when the driver reaches a human gate it stops, records nothing as human-approved, names the gate on stderr, and exits 3. Only `--attended` with a tty on stdin may relay a person's answer from the terminal; in that mode EOF or blank input at a gate is treated as not approved and exits 3. Non-tty `--attended`, and `--change-request` combined with `--attended`, are refused with exit 2. | N-5 | I-2 | headless | pty test | attended run |
| AC-7 | N-9 | I-1, I-3 | run_duties, TUI | equivalence test | - |
| AC-8 | N-10 | I-5 | headless | signal test: first signal forwarded to group, SIGKILL after 10s grace, second signal during grace kills the group immediately, no orphan processes remain | Ctrl+C |
| AC-9: `UNCLE_NOUI=1` (exactly) behaves like `--noui`; any other value (unset, empty, `0`, `true`, etc.) is ignored silently, and with `--noui` absent the launcher produces the identical exec argv and exported env as before. A second signal during the 10 s grace period kills the driver process group immediately. | N-11 | - | uncle | launcher test (enabled matrix: UNCLE_NOUI=1 enables), launcher test (disabled matrix: unset, 0, empty, true, other values ignored silently; exec argv and env identical to HEAD launcher), signal test (second signal during grace kills group immediately) | - |
| AC-10 | P-1..P-3, M-1 | V-1..V-5 | TUI, uncle | both runners, tui-delegation-golden-test.py | - |
| AC-11 | - | - | README, help | launcher grep | read |

Unattended gate rule (AR-003): without --attended, headless never reads stdin. When the driver reaches a human gate, the runner stops the run, nothing is recorded as human approval or delegation, the gate is named on stderr, and the exit code is 3. Tested in headless-run-test.py with a fixture driver that reaches a gate (stdin closed or unread, assert exit 3, stderr names the gate, no approval record written).

## Implementation sequence

1. Audit prior attempt: read `uncle_headless._stream` and `run_duties` against the plan; diff `uncle` and `uncle_tui.py` against committed HEAD (the regression baseline) and confirm the `uncle_tui.py` diff contains only delegation to shared functions with no non-delegation behavior change (any other change is reverted or recorded as a deviation); list gaps in IMPLEMENTATION_NOTES.md.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
2. Shared duties: extend `run_duties.py` with driver argv, worktree prep, startup-text and CR/brief helpers, exit classification (D-9, D-10); `build_driver_command` validates the action against a four-action allowlist and never takes paths from env; tests first, including rejection of unknown/empty/path-like actions.
   Owns: `scripts/lib/run_duties.py`, `scripts/tests/run-duties-test.py`
   Depends on: 1
3. TUI delegation to shared functions, no behavior change.
   Owns: `uncle_tui.py`
   Depends on: 2
4. Headless runner completion: environment-driven driver selection, setup, desktop decision, finish summary, title, exit codes, signals.
   Owns: `scripts/lib/uncle_headless.py`, `scripts/tests/headless-run-test.py`, `scripts/tests/pty_helper.py`
   Depends on: 2
5. Launcher wiring and refusals. Add a launcher-noui-test.sh case capturing exec argv and exported env with `--noui` absent and UNCLE_NOUI unset, 0 and empty, asserting identity with committed HEAD launcher output. Step 5 also owns reverting any unrelated `uncle` change found in the step 1 audit.
   Owns: `uncle`, `scripts/tests/launcher-noui-test.sh`
   Depends on: 4
6. Equivalence test and docs.
   
   Steps 3 and 4 touch disjoint files and may run in parallel.
   Owns: `scripts/tests/headless-equivalence-test.py`, `README.md`
   Depends on: 3, 4, 5

Audit reconciliation (AR-010): the step 1 audit runs against committed HEAD and its diff-audit result is recorded in IMPLEMENTATION_NOTES.md. Step 3 owns reverting any non-delegation change in `uncle_tui.py` found by the audit (or recording it as a deviation); step 5 owns reverting any unrelated change in `uncle`. The golden-output test is generated from committed HEAD functions and must pass against them before step 3 begins.

## 21. Scope cuts under time pressure
Cut first: documentation polish; the signal-orphan test depth; desktop-decision parity beyond recording; the equivalence test breadth (keep one fixture build). Never cut: AC-1..AC-4, I-4, TUI no-regression.

## 22. Risks and unresolved questions

| Risk | Mitigation |
|---|---|
| TUI delegation breaks existing tests patching `uncle_tui.*` | Keep re-exports; run both runners |
| Env-driven driver selection drifts from `cmd_for` | Single shared `build_driver_command` (D-9) |
| Prior attempt contains unreviewed code | Step 1 audit |

Resolved (AR-004): N-5 wording (stdin line-by-line) vs tty-only is settled by D-6. Attended needs a tty; `--change-request` with `--attended`, multiple startup actions, empty text, and `--attended` without `--noui` refuse exit 2; EOF or blank at an attended gate means not approved, exit 3.

No blocking planning decisions remain.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Exit code precedence was unspecified; tests need one deterministic code when several conditions hold. | Section 12 (s10.1) and AC-4 now state precedence: signal > gate/signing stop (3) > driver nonzero or failed check (1) > 0; 2 only before start. |
| AR-002 | Accepted | Gate stop versus plain driver failure needs a defined classification input so tests and users get a deterministic code. | Section 12 (s10.1) defines classify_exit's marker-based contract; AC-4 requirement and tests updated to match. |
| AR-003 | Accepted | Unattended gate behavior was unspecified; stopping with exit 3 without reading stdin is the only safe option. | Edit AC-4 and AC-5 traceability rows and add a gate-behavior note after s17.1. |
| AR-004 | Accepted | Input combinations were genuinely unspecified; D-6 conflicts with --change-request consuming stdin. | Edited D-6, AC-2, AC-6, R-4; replaced risk row s20.1.r4 with a prose note defining refusals (exit 2) and EOF/blank at gate (exit 3). |
| AR-005 | Accepted | Output rules were ambiguous: prefixing, stderr merging and redaction lacked a rule, mechanism and test. | D-5 restated; R-1 adds redaction mechanism; AC-3 row gets redaction test; s8.1 states output format. |
| AR-006 | Accepted | Real gap: UNCLE_NOUI values other than 1 and repeated-signal behavior were unspecified; the suggested rules are simple and safe. | Section 12 (s10.1) states the UNCLE_NOUI rule and second-signal immediate group kill; AC-9 requirement and tests updated to match. |
| AR-007 | Partially accepted | Delegation of cmd_for, _enter_run_worktree and _read_banner is the riskiest edit and existing suites alone may not pin exact outputs. (1 edit(s) could not be placed in the plan and were left out.) (1 edit(s) could not be placed in the plan and were left out.) | Added golden-capture step before TUI delegation, a golden-equivalence test, and updated s16.1.r4 coverage and AC-10 and step-3 text. |
| AR-008 | Accepted | Real gap: the plan only tests the enabling side of the launcher; the no-flag path must be byte-identical to preserve P-1..P-3. | Edit s16.1.r3 to state the identical-argv/env rule when --noui absent or UNCLE_NOUI is not exactly 1, and extend AC-9 with a disabled-side test. |
| AR-009 | Accepted | Existing tests may patch uncle_tui names that move to run_duties, so the plan must keep those names on uncle_tui and route delegation through them. | Section 10 (Compatibility) now requires every uncle_tui attribute referenced by existing tests to stay on uncle_tui, with delegation through it so patches still take effect. |
| AR-010 | Accepted | Uncommitted prior-attempt edits to uncle and uncle_tui.py exist, so the regression baseline must be committed HEAD and the audit must prove the TUI diff is delegation-only. | Edit D-8 and step-1 to set committed HEAD as the baseline and require the audit to confirm no non-delegation change in uncle_tui.py. |
| AR-011 | Accepted | The plan only implied via exit 3 that unattended runs never auto-approve a gate; an explicit rule is needed to prevent AI approval of human gates. | Traceability section: AC-6 requirement states the unattended rule, and a new prose block under s17 makes it a testable rule for AC-4/AC-6. |
| AR-012 | Accepted | Spec section 10 promises redaction but the plan had no enforcement point or test. | Added a redaction rule (pure `run_duties` function applied in the headless stream, byte-level test) to the Compatibility section. |
| AR-013 | Accepted | Real gap: the plan did not say where the text-file trust check runs in the headless runner. | Section 12 (s10.1) now states the runner re-validates the text file with the shared trust check immediately before reading and exits 2 on failure. |
| AR-014 | Accepted | Env-derived startup action is a new trust boundary and the runner is directly invocable, so it must be allowlisted. | Edited D-9, s7.1 (interface) and step-2 to require a four-action allowlist, exit 2 otherwise, and no env-supplied paths in argv. |
| AR-015 | Accepted | Grace period and repeated-signal behavior were unspecified and orphans could hold worktree locks. | Section 12 (s10.1) states a 10s grace then SIGKILL to the group, and an immediate SIGKILL on a second signal; AC-8 test requirement updated. |
| AR-016 | Accepted | Exit-code precedence and failed-check detection were unspecified, so tests could not know the expected code. | Section 12 (s10.1) now states precedence and failed-check detection; AC-4 row requirement and tests agree. |
