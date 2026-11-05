# Change spec - Issue 160 `--noui`

Omitted sections: Migration (none); Prototype isolation (not a prototype); Performance (no new requirement beyond not slowing the TUI path)

## 1. Change type
Feature (with a small refactor extracting shared run duties).

## 2. Problem
A startup action always runs in curses (forced via `--noinput` without a tty). Headless use (CI, cron, ssh, docker) is unsupported.

## 3. Current behavior
Baseline B-1..B-8.

## 4. Desired behavior
`uncle --noui` (or `UNCLE_NOUI=1`) runs the selected startup action headlessly with the same results as the TUI, plain text output, documented exit codes.

## 5. Observable behavior table
| ID | Class | Trigger | Current | Expected | Verification |
|---|---|---|---|---|---|
| N-1 | ADD | `--noui --application TEXT` | no flag | Build runs, plain progress, no curses imported, no escapes | launcher test with fake driver + stubbed TUI |
| N-2 | ADD | `--noui --issue N / --change-request / --housekeeping` | no flag | Same per workflow with same text/stdin handling | launcher tests x4 |
| N-3 | ADD | `--noui` without tty | TUI forced | Works; never needs tty; never starts TUI | piped-stdio test |
| N-4 | ADD | `--noui` unattended | n/a | No prompt, finished-build summary printed, failing check -> non-zero | headless run test |
| N-5 | ADD | `--noui --attended` | n/a | Gate prompt printed, answer read from stdin, recorded as human; no usable stdin -> refuse, exit 2, never unattended | pty test + refusal test |
| N-6 | ADD | `--noui` no startup action | n/a | Usage error, exit 2, nothing started | launcher test |
| N-7 | ADD | any `--noui` output | n/a | Plain text, no cursor/alt-screen escapes, stage lines carry elapsed time | byte-assert test |
| N-8 | ADD | exit status | n/a | 0 finished; 1 driver failed; 2 refused; 3 blocked at gate/needs signed commit; 130/143 signals | exit-code tests |
| N-9 | ADD | same inputs via TUI path vs `--noui` | n/a | Same artifacts, state, attestation fields, PR content ignoring timestamps | equivalence test |
| N-10 | ADD | SIGINT/SIGTERM | n/a | Run stops, state resumable, no orphan children | signal test |
| N-11 | ADD | `UNCLE_NOUI=1` | n/a | Same as flag; flag wins; only value `1` enables | launcher test |
| P-1 | PRESERVE | all existing launcher/TUI invocations without `--noui` | per baseline | Unchanged output, exit codes, startup behavior (B-1..B-7) | existing suites via both runners |
| P-2 | PRESERVE | `--noinput` | TUI w/o keyboard | Unchanged; `--noui` plus `--noinput` is refused (exit 2) | launcher test |
| P-3 | PRESERVE | line menu | non-tty fallback | Retained | existing test |
| M-1 | MODIFY | duties: finish line, banner parse, finish_decision, desktop decision, brief text, driver argv | inline in TUI | One shared implementation in `run_duties.py` called by TUI and headless | unit tests + defect injection |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement | Verification |
|---|---|---|---|---|---|
| I-1 | NEW | `--noui` never changes what is built, checked, approved or published | run | headless runner passes driver argv/env unchanged except display/prompt env | equivalence test |
| I-2 | NEW | Gates recorded identically; human answer in attended noui = human, delegated = delegated | gates | driver records; headless forwards stdin only | pty test inspects state |
| I-3 | NEW | TUI and headless call the same shared functions; no duplicate | code | `run_duties.py`; TUI imports it | grep-style test + defect injection |
| I-4 | NEW | `--noui` output never contains cursor-move, clear-screen or screen-switch escapes (including from driver output) | output | `EscapeFilter` | byte-assert test |
| I-5 | NEW | Exit status reflects run result only | exit | `classify_exit` | exit-code table test |
| V-1..V-5 | EXISTING | Per baseline section 5 | - | - | existing suites |

No RELAXED or REMOVED invariants.

## 7. Compatibility
No change without the flag. `uncle_tui.finish_decision` remains importable.

## 8. Error and failure behavior
Refusals print a reason on stderr and exit 2 before any state is written. Driver failure exits 1 with reason. Gate stop / signing handoff exits 3 with the state left resumable. Signals forward to the driver's process group, then exit 130/143.

## 10. Security
Startup text file trust rules (V-1) apply identically; secrets in env are redacted from echoed output; no `eval` of text.

## 12. Rollback
Remove the `--noui` branch from `uncle` and revert `run_duties` delegation; TUI behavior is otherwise unchanged.

## 14. Non-goals
Replacing the TUI, a GUI, JSON events, stage/gate/check changes, config editing headlessly.

## 15. Assumptions
- Direct-path (no supervisor draft) is the parity target for `--application`.
- Attended mode requires a tty on stdin (a pipe cannot reliably answer gates; `--change-request` consumes stdin). Recorded as a decision; CR N-5 refusal wording is satisfied.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `uncle --noui` with each of the four startup actions starts the correct driver with the same argv, text and env a TUI run would use, and never imports or starts curses. | Launcher test with fake drivers and a stub uncle_tui.py that fails if executed; run for all four actions. |
| AC-2 | `--noui` without a startup action, combined with `--noinput`, or attended without a usable tty on stdin refuses with a message and exit 2, starts nothing, and never falls back to unattended or the menu. | Launcher/headless tests asserting exit code, stderr and absence of driver start. |
| AC-3 | Output of a piped (no pty) `--noui` run contains no cursor-control, clear-screen or alternate-screen escape sequences, even when driver output contains them, and progress lines carry stage names and elapsed time. | Byte-level assertions in headless-run-test.py on captured stdout/stderr. |
| AC-4 | Exit codes: 0 finished; 1 driver failure; 2 refused; 3 stopped at a gate or needs a signed commit; 130/143 on SIGINT/SIGTERM; never 0 for a run that stopped at a gate or failed a check. Documented in `uncle --help` and README. | Exit-code table tests for finished, failed check, blocked gate, refused, signal, missing stdin; help text grep. |
| AC-5 | An unattended `--noui` run prints the finished-build summary produced by the same shared functions the TUI uses; skipping the summary or the desktop decision fails a test. | Run-duties and headless tests plus defect injection (monkeypatch headless to skip each) confirming failure. |
| AC-6 | `--noui --attended` on a pty prints the gate prompt, reads one line from stdin, and the gate is recorded as a human approval. | pty test via pty_helper.py inspecting recorded state. |
| AC-7 | Same inputs through the TUI path and `--noui` produce the same artifacts, state and attestation fields (ignoring timestamps), including worktree creation for non-issue runs, CHANGE_REQUEST write and brief write. | headless-equivalence-test.py with a fixture driver. |
| AC-8 | SIGINT/SIGTERM stops the driver process group with no orphans and exits 130/143, leaving state resumable. | Signal test checking child pids gone. |
| AC-9 | `UNCLE_NOUI=1` behaves as `--noui`; any other value does not; the flag wins when both given. | Launcher test matrix. |
| AC-10 | Without `--noui`, existing launcher and TUI behavior is unchanged: both documented runners show no new failures vs the baseline; `uncle_tui.finish_decision` and banner parsing remain behaviorally identical. | `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` compared to baseline. |
| AC-11 | README and `uncle --help` document `--noui`, `UNCLE_NOUI`, exit codes, the attended requirement, and the difference from `--noinput`. | Doc grep in launcher test; manual read. |

