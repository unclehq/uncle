# Change Plan — Issue 275

Seeded from [unclehq/uncle#275](https://github.com/unclehq/uncle/issues/275).

Issue 275

Omitted sections: Schema/persistence (none); State-transition (no new state); Concurrency (installer runs serially before the background probe); Observability beyond report narrative (none)

## 1. Selected technical approach

1. `preflight.py`: add `command`/`which` handling (probe the word after `-v`/directly), and make unlisted executables a presence check via `shutil.which` that raises `Missing runtime: NAME` or records `NAME found at PATH` without executing.
2. New `scripts/lib/toolchain_install.py`: given the commands file, parse each command line independently (reusing the preflight tokenizer); record and skip malformed/unparseable lines with a reason, then continue discovering missing executables from the valid lines. Map missing executables to apt packages from a fixed table (unmapped tools are skipped with a recorded reason), and when `is_hosted()` install via `sudo -n apt-get install -y --no-install-recommends` (argv arrays, timeout, never fatal). Writes a JSON record to `$STATE_DIR/toolchain-install.json` and prints a summary.
3. `change-workflow.sh`: at PREFLIGHT, in hosted runs, call the installer synchronously (before the background probe and implementation), then run preflight so its result reflects the installed tools. The record text is appended to the PF-RUNTIME narrative via an env/file read in `change_preflight_run`.
4. Prompts: add a short hosted-toolchain paragraph to `prompts/change/baseline.md`, `change-plan.md`, `implement-change.md`, and `prompts/implement.md`.

## 2. Alternatives considered
| Alternative | Rejected because |
|---|---|
| Only prompt changes | Agent lacks reliable sudo discipline; issue shows it won't install |
| Let the implementer run apt itself | Unlogged, unbounded, and non-deterministic; kept as fallback in prompt only |
| Install via opam/ghcup/rustup | Slow, network-heavy; apt took 5s |

## 3. Why preferred
Deterministic, logged, hosted-gated, no model call, and fixes preflight so the signal is correct.

## 4. Decisions

| ID | Decision | Reason |
|---|---|---|
| D-1 | Package map (exactly one package per executable): ocaml, ocamlc, ocamlopt -> `ocaml`; ocamlfind -> `ocaml-findlib`; dune -> `ocaml-dune`; ghc -> `ghc`; cabal -> `cabal-install`; stack -> `haskell-stack`; java, javac -> `default-jdk-headless`; dotnet -> `dotnet-sdk-8.0`; opam -> `opam`. Packages are deduplicated, in first-seen order, before the install argv is built. | Debian names; a single unambiguous package per executable lets installer code and argv assertions agree; unmapped tools are skipped, not guessed |
| D-5 | The four prompt updates (baseline.md, change-plan.md, implement-change.md, implement.md), all D-1 package mappings, and the preflight narrative record are required deliverables and may not be cut without an approved scope revision. This supersedes the cut list in section 21: only the order of work may change under time pressure, never the scope. The preflight fix and the hosted gate also remain uncuttable. | Keeps implementation scope identical to BH-5/BH-8 and the acceptance checks (AR-001). |
| D-2 | Gate: `UNCLE_HOSTED=1` and `WORKFLOW_TOOLCHAIN_INSTALL!=0` | Matches request item 1 and rollback |
| D-3 | Install all deduplicated mapped packages in ONE `sudo -n apt-get install -y --no-install-recommends` invocation, with no retry. The whole installer shares a single 300-second deadline (not per package). If the deadline expires, no further install is attempted and any unattempted packages are recorded as skipped, then the run continues to preflight. The installer starts apt in its own process group/session (`start_new_session=True`). On timeout it terminates the entire process tree, including privileged descendants (sudo, apt-get, dpkg, maintainer scripts): SIGTERM to the group, a short grace period, then SIGKILL, and it reaps the child. If a direct signal is denied because `sudo -n` ran the group as root, it signals through `sudo -n kill`. Cleanup completes before the record is written and before preflight resumes, so no package mutation runs concurrently with verification. The record states the timeout and the cleanup outcome; if cleanup cannot be confirmed, the record says so and the run continues. A test in toolchain-install-test.py uses a fake `apt-get` that spawns a persistent child, forces the timeout, and asserts that no descendant is alive afterward. `apt-get update` is not run (package lists present on hosted images). | Bounded total hosted delay (matches the 300s cap in the risk table) and minimal. One invocation under one deadline gives installer tests a single oracle for argv, failure and timing. Killing and reaping the whole tree stops privileged descendants from outliving the timeout and mutating the system during verification. |
| D-4 | `PATH`-only presence check for unlisted tools; no execution | Preserves INV-1/INV-2 |

## Restrictions
| R-ID | source_kind | Source | Requirement IDs | Required property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST item 1 | BH-5, INV-3 | Install only in hosted builds | `is_hosted()` check in installer | Exact-1 predicate | CAP-HOSTED | CODING |
| R-2 | DESIGN | spec 10 | INV-4 | No plan text becomes a package name | Fixed map | Avoid injection | CAP-PKGMAP | CODING |
| R-3 | DESIGN | spec 8 | INV-5, BH-6 | Installer never fatal | Always exit 0, record failure | Run continues | CAP-NONFATAL | CODING |
| R-4 | REPOSITORY | preflight.py:42-44 | INV-1, INV-2 | Never execute unlisted tools | `shutil.which` only | Observed in `probe()` lines 105-111 | CAP-PRESENCE | CODING |
| R-5 | PLATFORM | Debian apt, sudo | BH-5 | Non-interactive privilege | `sudo -n`, `-y` | A password prompt would hang | CAP-SUDO | LIVE_VERIFICATION |

Feasibility: `shutil.which` use observed at preflight.py:106; hosted predicate at hosted.py:10; apt/sudo are not available on this macOS machine, so the tests use fakes (CODING) and a real install is LIVE_VERIFICATION (live check LV-1: in a hosted Debian sandbox run `UNCLE_HOSTED=1 python3 scripts/lib/toolchain_install.py <commands> <record>` for a file containing `ocaml -version`; no secrets needed).

## 4a. Components to modify
See change-impact table. Not modified: `install_warm.py`, supervisor, test-file recognition, `hosted.py`, `stage-config.sh`.

## 6. Data-flow changes
verification commands file -> installer (hosted) -> record JSON -> preflight narrative; preflight then runs on the updated PATH.

## 8. Interface changes
New CLI `toolchain_install.py <commands> <record-json>`; exit always 0 unless usage error (2). preflight.py CLI unchanged.

## 10. Compatibility
Non-hosted flow byte-for-byte unchanged apart from preflight accepting more lines (previously a BLOCKED-SETUP).

## 12. Error and recovery

Install failure, timeout, missing sudo/apt: recorded and the run continues. After any install outcome preflight checks actual PATH availability and reports `Missing runtime` only for tools still absent; tools that installed despite a failed batch are not reported. On timeout the whole installer process tree, including privileged descendants, is terminated and reaped before preflight resumes.

## 13. Migration
None.

## 14. Rollback plan
Revert the commit, or set `WORKFLOW_TOOLCHAIN_INSTALL=0`. Installed system packages are not removed (harmless, additive).

## 15. Containment
Hosted-only gate plus env kill switch.

## 16. Automated-test strategy

New suites `scripts/tests/preflight-toolchain-test.py` (AC-1..3) and `scripts/tests/toolchain-install-test.py` (AC-4..8), fixture git use none. Fake `sudo`/`apt-get` shell stubs in a temp PATH. The default runner only runs `critical-suites.txt`, so regression coverage uses explicit full-suite selection: run both baseline regression runners (python and shell) with their full-suite option, not the default critical tier. Retain `bash scripts/run-python-tests.sh -- preflight-toolchain` and `bash scripts/run-python-tests.sh -- toolchain-install` as additional targeted verification commands recorded for the driver; do not add the new suites to the critical tier.

## 17. Regression-test strategy

Cases in preflight-toolchain-test.py pin B-3, B-4, B-5. toolchain-install-test.py also pins: exact deduplicated argv `sudo -n apt-get install -y --no-install-recommends ocaml ocaml-findlib ocaml-dune` for ocaml/ocamlfind/dune; one apt-get call with a timeout record and exit 0 when the fake sleeps past the deadline; a test-only short-deadline override with several missing tools asserting total wall time is bounded and remaining packages are recorded as skipped; a fake apt-get spawning a persistent child (pid file) asserting no descendant is alive after timeout; a partial-success case where preflight reports only the still-absent tool; and a mixed valid/malformed commands file. Full python and shell runners (explicit full-suite selection) must show no new failures.

## 18. Manual-verification strategy
LV-1 above on a Debian sandbox; plus a full hosted hello-world OCaml build, expected READY with AC rows IMPLEMENTED (BLOCKED-SETUP in this environment: needs a model and sandbox).

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/preflight.py` | command/which probe; presence check for unlisted tools | BH-1..3 | Medium (tokenizer allowlist) | preflight-toolchain-test.py |
| `scripts/lib/toolchain_install.py` | new installer | BH-5..7 | Low (new, gated) | toolchain-install-test.py |
| `scripts/change-workflow.sh` | call installer at PREFLIGHT when hosted; narrative append | AC-8 | Medium (large driver) | toolchain-wiring-test.py source assertion; driver suites |
| `prompts/change/baseline.md`, `prompts/change/change-plan.md`, `prompts/change/implement-change.md`, `prompts/implement.md` | hosted toolchain paragraph | BH-8 | Low (prompt size budgets) | toolchain-wiring-test.py content check; existing prompt suites |
| `scripts/tests/preflight-toolchain-test.py`, `scripts/tests/toolchain-install-test.py` | new | verification | n/a | self |

## Traceability
| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| Request 3 | BH-1..3 | INV-1, INV-2 | preflight.py | preflight-toolchain-test.py | none |
| Request 1 | BH-5..7 | INV-3..5 | toolchain_install.py, change-workflow.sh | toolchain-install-test.py | LV-1 |
| Request 2 | BH-8 | n/a | prompts | toolchain-install-test.py | review |
| Request 4 | BH-9 | n/a | all | AC-7 simulated test | live OCaml build (BLOCKED-SETUP) |

Bug regression test: `preflight-toolchain-test.py::test_command_v_probes_name` fails before the fix (raises Unrecognized executable: command) and passes after.

## Implementation sequence

1. Preflight probe fix and its test
   Owns: `scripts/lib/preflight.py`, `scripts/tests/preflight-toolchain-test.py`
2. Installer helper and its test (reuses the tokenizer from step 1's `prerequisites`; builds on step 1's change to `preflight.py` without editing it). The test includes a mixed valid/malformed commands-file case: malformed lines are recorded and skipped, and missing tools from the valid lines are still discovered and installed.
   Owns: `scripts/lib/toolchain_install.py`, `scripts/tests/toolchain-install-test.py`
   Depends on: 1
3. Driver wiring at PREFLIGHT. After every install outcome (success, nonzero exit, timeout, missing sudo/apt), run preflight against actual tool availability: it reports `Missing runtime` only for tools still absent, so tools that were installed despite a failed or timed-out batch are not forced into BLOCKED-SETUP. toolchain-install-test.py must include a partial-success case (installer fails after one tool becomes available; preflight lists only the remaining absent tool).
   Owns: `scripts/change-workflow.sh`
   Depends on: 2
4. Prompt paragraphs (independent of 1-3)
   
   Verification commands: the two baseline commands, each run with explicit full-suite selection (not the default critical-only tier), plus the additional targeted commands `bash scripts/run-python-tests.sh -- preflight-toolchain` and `bash scripts/run-python-tests.sh -- toolchain-install`. Protected paths: the two new test files.
   Owns: `prompts/change/baseline.md`, `prompts/change/change-plan.md`, `prompts/change/implement-change.md`, `prompts/implement.md`
5. **Wiring and prompt assertions** — New test `scripts/tests/toolchain-wiring-test.py` asserts the installer call and narrative append in `scripts/change-workflow.sh` and the hosted-toolchain paragraph in the four prompt files; toolchain-install-test.py stays limited to the installer helper. Verification commands additionally include `bash scripts/run-python-tests.sh -- toolchain-wiring`. Protected paths: the three new test files (preflight-toolchain-test.py, toolchain-install-test.py, toolchain-wiring-test.py).
   Owns: `scripts/tests/toolchain-wiring-test.py`
   Depends on: 3, 4

## 21. Scope cuts under time pressure

The four prompt updates, all D-1 package mappings, the PF-RUNTIME narrative record, the preflight fix and the hosted gate are required deliverables and may not be cut without an approved scope revision. Only the order of work may change under time pressure; if time expires, stop and report unfinished required items rather than silently dropping them.

## 22. Risks and unresolved questions

| Risk | Mitigation |
|---|---|
| Wrong Debian package name | Map limited to well-known names; failure is non-fatal and recorded |
| Driver size/prompt-budget tests fail on added text | Keep paragraphs to a few lines; run full runners |
| Installer slows hosted runs | Only runs when something is missing; one grouped apt-get call with a single 300s timeout, no retry |
| Live end-to-end not verifiable here | LV-1 and the hosted OCaml build are explicit BLOCKED-SETUP checks |

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The scope cuts in section 21 would drop deliverables that BH-5/BH-8 and section 1 require, so scope and acceptance criteria disagreed. | Added decision D-5 in section 4 making the four prompt updates, all D-1 mappings and the narrative record non-cuttable and superseding the section 21 cut list. |
| AR-002 | Accepted | D-1 listed ambiguous OCaml mapping and two dune package names; one package per executable is needed so installer code and argv assertions agree. | D-1 now maps ocaml/ocamlc/ocamlopt->ocaml, ocamlfind->ocaml-findlib, dune->ocaml-dune, with deduplication. |
| AR-003 | Accepted | D-3 said 300s per install while the risk table promised a 300s cap; one shared deadline makes both agree and gives timeout tests one oracle. | D-3 now sets one shared 300-second deadline for all install attempts, with remaining-time per attempt and skipped records after expiry. |
| AR-004 | Accepted | Plan and spec conflict on partial success; preflight must judge actual availability after any install outcome. | Edit step-3 text to require preflight to report Missing runtime only for tools still absent after any install outcome, plus a partial-success test. |
| AR-005 | Accepted | The default runner only runs critical suites, so full regression coverage needs explicit selection alongside the two targeted suites. | Edit s14.1 and step-4 so verification commands run both runners with full-suite selection plus the two targeted suite commands. |
| AR-006 | Accepted | A per-install timeout lets several packages multiply the hosted delay past the promised 300s cap, so one shared deadline is needed. | D-3 now sets one shared 300s deadline for all installer subprocesses, with remaining packages recorded as skipped when it expires. |
| AR-007 | Accepted | Timing out only the sudo process can leave apt-get or package scripts mutating the system while preflight runs, so the timeout must kill the whole process tree. | D-3 now requires the installer to run in its own process group and, on timeout, kill and reap the whole tree before preflight resumes, with a persistent-child test. |
| AR-008 | Accepted | D-1 gave ambiguous OCaml and competing dune package names, so installer code and argv assertions could diverge. | D-1 now fixes one package per executable, with deduplication before the install argv is built. |
| AR-009 | Accepted | Per-install timeout vs 300s cap was ambiguous; one grouped apt-get call with a single 300s timeout gives tests one oracle. | D-3 now specifies one apt-get invocation for all deduplicated packages, one 300s timeout, no retry; s21.1.r3 mitigation aligned. |
| AR-010 | Accepted | A malformed line next to valid ones had no defined recovery scope; per-line parsing removes the ambiguity. | Section 1 item 2 now parses each line independently, records and skips malformed lines; step-2 adds a mixed valid/malformed test case. |
