# Change Spec — Issue 275

Omitted sections: Performance (none beyond bounded install time); Migration (none); Prototype isolation (not a prototype)

## 1. Change type
Feature + bug fix (hosted toolchain provisioning; preflight probe gap).

## 2. Problem statement
A hosted build lacking a language toolchain finishes NOT_READY with waived acceptance rows and hand-traced output, though the toolchain installs in seconds. Preflight also cannot confirm or report missing toolchains.

## 3. Current behavior
See BASELINE B-1, B-2, B-6.

## 4. Desired behavior
In hosted runs the driver installs a missing toolchain the plan's verification needs, records it, and prompts tell agents to install rather than hand-trace. Preflight reports `Missing runtime: <name>` for any absent executable and understands `command -v`/`which`.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| BH-1 | MODIFY | Command line `command -v NAME` or `which NAME` (NAME a plain word) | Refused: Unrecognized verification executable | Treated as a probe of NAME | preflight unit test |
| BH-2 | MODIFY | Executable not in PROBES, not found by `shutil.which` | Refused as unrecognized | `Missing runtime: NAME`, exit 2 | preflight unit test |
| BH-3 | MODIFY | Executable not in PROBES but present on PATH | Refused as unrecognized | Accepted; probe is presence only (`shutil.which`), never executed; report finding says `NAME found at PATH` | preflight unit test |
| BH-4 | PRESERVE | PROBES names, builtins, expansions, embedded `-c`, PATH assignments | See B-3..B-5 | Unchanged | existing + new tests |
| BH-5 | ADD | Hosted run, preflight reports missing runtimes, a supported package manager and passwordless sudo exist | Nothing installed | Driver installs mapped packages before implementation starts, logs output, records `.uncle/docs/TOOLCHAIN_INSTALL.md`-equivalent record in the preflight report narrative | installer unit test with fake package manager |
| BH-6 | ADD | Install is impossible (not hosted, no sudo, no manager, unmapped tool, install fails) | n/a | Run continues; missing tools stay reported as BLOCKED-SETUP; reason recorded; no hand-trace instruction is lifted | installer unit test |
| BH-7 | PRESERVE | Non-hosted run | No installs | No installs, ever | installer unit test |
| BH-8 | MODIFY | Hosted baseline/plan/implement prompts | Missing compiler is a fact to work around | Prompts say: on a hosted machine with a package manager, install it; do not hand-trace or waive rows because a toolchain is missing | prompt text test |
| BH-9 | ADD | Hosted hello-world build in a language absent from the image | Ends NOT_READY | Toolchain installed, verification commands run, AC rows IMPLEMENTED | simulated test (see AC-7); live check BLOCKED-SETUP |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | EXISTING | Preflight never executes plan commands or evaluates shell expansion | preflight.py | tokenizer + fixed probes | tests |
| INV-2 | NEW | Unlisted executables are checked by presence only (`shutil.which`), never run | preflight.py | probe() | test with a stub that records execution |
| INV-3 | NEW | System packages are installed only when `UNCLE_HOSTED` is exactly `1` | installer | `is_hosted` | test |
| INV-4 | NEW | Only packages from a fixed tool-to-package map are installed; names never come from plan text | installer | map lookup | test |
| INV-5 | NEW | Installer failure never aborts the run | installer + driver | non-fatal exit | test |
| INV-6 | EXISTING | Hosted predicate is exact `1` | hosted.py | is_hosted | hosted-mode-test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Preflight CLI, report schema and exit codes unchanged. Non-hosted behavior unchanged.

## 8. Error and failure behavior
Unparseable or unmapped tool: skipped with recorded reason. Install nonzero or timeout: recorded, run continues, check remains missing. `sudo` needing a password: never prompt (`sudo -n`).

## 10. Security
No shell interpolation of plan text; argv arrays only; `sudo -n`; fixed package map; hosted-only; bounded timeout.

## 12. Rollback
Revert the commit; set `WORKFLOW_TOOLCHAIN_INSTALL=0` to disable the installer at runtime.

## 14. Non-goals
Supervisor in headless builds (#274); test-file recognition (#262); installing on non-hosted machines; installing npm/pip dependencies; live Debian end-to-end run.

## 15. Assumptions
Hosted machines are Debian/Ubuntu-like with apt; other managers (brew, dnf, apk) are detected but only apt-get is mapped in this change. opam/ghcup/rustup are not used; apt packages suffice for OCaml and Haskell.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `command -v NAME` and `which NAME` lines are probed as NAME by preflight.py instead of being refused. | New suite preflight-toolchain-test.py: lines with an installed PROBES name pass; lines with a missing name report Missing runtime. |
| AC-2 | An executable absent from PROBES and absent from PATH yields `Missing runtime: NAME` (exit 2); one present on PATH is accepted by presence check without being executed. | Same suite, using a temp PATH with a stub script that writes a marker if run; marker must not exist. |
| AC-3 | Existing refusals (expansion, embedded bash -c, PATH assignment, malformed shell) and PROBES behavior are unchanged. | Same suite regression cases plus full python runner. |
| AC-4 | In hosted mode with sudo and apt-get available, the installer installs the mapped packages for missing tools (ocaml, dune, ocamlfind, ghc, cabal, java, etc.) and writes a record naming each install and its outcome. | Suite toolchain-install-test.py with fake `sudo` and `apt-get` on PATH recording argv. |
| AC-5 | The installer does nothing when UNCLE_HOSTED is not exactly 1, when WORKFLOW_TOOLCHAIN_INSTALL=0, for unmapped tools, or when sudo -n / apt-get is missing; failure of an install never fails the run. | Same suite; fake apt-get exiting nonzero gives exit 0 for the helper and a recorded failure. |
| AC-6 | Hosted-aware prompt text instructs planner, baseline and implementer to install a missing toolchain on a hosted machine and forbids hand-tracing output or waiving acceptance rows because a toolchain is missing. | Prompt content assertions in toolchain-install-test.py. |
| AC-7 | Simulated hosted hello-world flow: baseline commands naming a missing OCaml toolchain are preflighted, the installer (fake apt-get that creates `ocaml`/`dune` stubs on PATH) installs them, and a second preflight passes. | End-to-end helper-level test in toolchain-install-test.py; the real model-driven READY/IMPLEMENTED run is a live check and is BLOCKED-SETUP here. |
| AC-8 | The driver invokes the installer at the PREFLIGHT state before implementation only in hosted runs, and a preflight failure still produces a non-blocking BLOCKED-SETUP row. | Source-level assertion in test plus existing driver suites passing. |

