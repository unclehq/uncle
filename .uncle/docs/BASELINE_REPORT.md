# Baseline Report — Issue 275

Omitted sections: Reproduction result (not run; the issue's evidence is a hosted run, and the preflight refusal is reproducible by reading `preflight.py`); Areas explicitly outside the change (folded into section 12)

## 1. Change-request summary
See CHANGE_REQUEST.md. Hosted builds (`UNCLE_HOSTED=1`) never install a missing language toolchain; `preflight.py` refuses `command -v X` and non-listed toolchains; prompts treat a missing compiler as a fact to work around.

## 2. Repository architecture
Bash driver `scripts/change-workflow.sh` (state machine; states incl. PREFLIGHT, MODULE_INTERFACES, IMPLEMENT) sources `scripts/lib/*.sh` and shells to Python helpers in `scripts/lib/`. Prompts live in `prompts/` and `prompts/change/`. Hosted switch: `scripts/lib/hosted.py:is_hosted` and `scripts/lib/stage-config.sh:47 uncle_is_hosted` (both require exactly `UNCLE_HOSTED=1`). Tests: `scripts/tests/*-test.py|sh`, default tier listed in `scripts/tests/critical-suites.txt`.

## 3. Relevant code paths
- `scripts/lib/preflight.py:12-19` PROBES/BUILTINS; `:42-44` raises `Unrecognized verification executable`; `:105-120` `probe()` raises `Missing runtime: <name>` when `shutil.which` fails; `:123` `run()`; `:143-153` CLI exits 2 with `Deterministic preflight needs diagnosis`.
- `scripts/change-workflow.sh:3599-3626` `change_preflight_run` (writes PF-RUNTIME row; failure => BLOCKED-SETUP row, non-blocking); `:4430-4449` PREFLIGHT state runs it in the background beside implementation unless `WORKFLOW_PREFLIGHT_BLOCKING=1`; `:4189` `install_warm_start`.
- `scripts/lib/install_warm.py` / `install-warm.sh`: warms npm and Playwright caches only.
- Prompts: `prompts/change/baseline.md:155-161` (install guidance for npm only), `prompts/change/change-plan.md`, `prompts/change/implement-change.md`, `prompts/implement.md`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Verification line `ocaml -version`, `ghc`, `dune`, `java`, ... | preflight exits 2: `Unrecognized verification executable: <name>` | preflight.py:42-44 | Replace for unknown executables |
| B-2 | Line `command -v ocaml` / `which ocaml` | same refusal on `command`/`which` | preflight.py:12-19 | Replace |
| B-3 | Line `node --version` etc. for a PROBES name that is installed | PASS row, `<name> --version exited 0` | preflight.py:105-120 | Yes |
| B-4 | A PROBES name not installed | `Missing runtime: <name>` exit 2 | preflight.py:109 | Yes |
| B-5 | Shell expansion / embedded `bash -c` / PATH assignment in a line | refused as needs model preflight | preflight.py:30-33,40-41 | Yes |
| B-6 | Hosted run, toolchain missing | nothing installs it; prompts allow hand-tracing | issue 275 | No (change) |
| B-7 | Non-hosted run | no installs by driver | install_warm.py | Yes |
| B-8 | Preflight failure | PF-RUNTIME BLOCKED-SETUP row, run continues | change-workflow.sh:3616-3622 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Preflight never executes plan commands, only fixed `--version`/no-op probes | PROBES table, tokenizer | none direct found | Medium |
| I-2 | Preflight never evaluates shell expansions | preflight.py:30-33 | none direct found | Medium |
| I-3 | Hosted only when `UNCLE_HOSTED` is exactly `1` | hosted.py, stage-config.sh:47 | hosted-mode-test.py Predicate | High |
| I-4 | Verification commands do not change the repo; baseline runs twice | baseline prompt rules | none | Low |

## 6. Interface contracts
`python3 preflight.py <commands-file> <report-json>`; exit 0 and writes acceptance-report JSON with row PF-RUNTIME; exit 2 with stderr message on failure. Report schema `uncle.artifact/v1` kind `acceptance-report`.

## 7. Existing automated-test coverage
No test file imports `preflight.py` directly (grep of `scripts/tests` shows only `preflight_readonly`, a different module, and stage-level suites). `hosted-mode-test.py` covers the hosted predicate and model-setting fallback. Python suites run through `scripts/run-python-tests.sh`, shell suites through `scripts/run-shell-tests.sh`; they use separate temp dirs, so they run as one parallel group.

## 9. Baseline test results
Commands come from the repository runners (`scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh`) per the stage contract. Not executed here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout.

## 10. Existing failures, warnings, flaky behavior
None documented in-repo for this surface. UNRESOLVED until the driver baseline lands.

## 12. Likely change surface
`scripts/lib/preflight.py`; a new hosted toolchain installer helper and its wiring at the PREFLIGHT state in `change-workflow.sh`; prompt text in `prompts/change/baseline.md`, `change-plan.md`, `implement-change.md` (and `prompts/implement.md` for the greenfield driver); new tests. Outside the change: `install_warm.py` cache warming, supervisor start-up in headless builds (#274), test-file recognition (#262), non-hosted behavior.

## 13. Regression-sensitive components
`preflight.py` tokenizer (I-1, I-2); the PREFLIGHT state ordering (background probe vs. implementation); `uncle_is_hosted` predicate; prompt files measured by size budgets and prompt tests (e.g. `reviewer-prompt-kind-test.py`).

## 15. Unknowns and assumptions
- Whether the host has passwordless sudo and a package manager: assumed only on hosted machines; installer must detect, not assume.
- Exact package names per toolchain (e.g. `ocaml`, `dune`, `ghc`, `cabal-install`, `default-jdk`) are chosen in the plan.
- The hosted end-to-end build in the issue's request item 4 cannot run in this environment (needs a model and a Debian sandbox).

## 16. Initial risk assessment
Medium. Installing system packages is outward-facing on the host; it must be hosted-only, bounded, logged and never fatal to the run. Widening the preflight allowlist must not weaken I-1/I-2.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

