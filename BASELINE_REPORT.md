# Baseline report
Omitted sections: none

## 1. Change-request summary
CR-1: §8/6: missing-file failure; wrong-file creation unconfirmed.

## 2. Repository architecture
A-1: Bash drivers/Python UI/helpers/prompts (`scripts/README.md`); dependencies: `packaging/debian/control`; build: `scripts/install/build-package.py`.

## 3. Relevant code paths
C-1: `uncle:576`, `uncle_tui.py:1015,2502` pass --new to C-3.
C-3: `scripts/from-issue.sh:351,429,508,519` selects/seeds/dispatches.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | --new, absent requirements | Exit 1; neither document created | §8/6 | No |
| B-2 | --new, brief marker exists | Keep prefix; replace brief through EOF | C-3; static | Yes |
| B-4 | Auto mode | Select change for existing request/code | C-3; static | Assumed |
| B-5 | --change, EOF confirmation | Seed only | §8 command 2; C-3:142 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Writes target selected project | C-3:6–12 | §9/T-5 | High |
| I-2 | Protect active run ownership/edits | C-3:60,91,521 | §9/T-7 | High |
| I-3 | Close requires run/origin/audit match | scripts/lib/issue-close.sh | §9/T-7 | High |
| I-4 | New seed requires exact brief marker | C-3:508 | None found | High; §8/6 |

## 6. Current API, schema, and interface contracts
K-1: Number/URL, --change/--new; gh→curl, Python/jq (`C-3:244–343`).
K-2: New mode only seeds (`scripts/README.md:206`).
K-3: State/origin grammars: `scripts/lib/state.sh:4`, `scripts/lib/issue-close.sh:5`.

## 7. Existing automated-test coverage
T-1: §9 suites isolate temporary fixtures/ports; bytecode disabled.
T-2: New seeding untested; other suites/builds unrun.

## 8. Exact build and test commands executed
```sh
bash -n uncle scripts/from-issue.sh
bash -o pipefail -c 'bash scripts/tests/issue-project-root-test.sh 2>&1 | tail -8'
bash -o pipefail -c 'PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/menu-input-test.py -q 2>&1 | tail -12'
bash -o pipefail -c 'PYTHONDONTWRITEBYTECODE=1 bash scripts/tests/close-flow-test.sh 2>&1 | tail -12'
bash -n scripts/from-issue.sh
python3 -B -c 'import os,pathlib,subprocess,tempfile; root=pathlib.Path.cwd(); t=tempfile.TemporaryDirectory(); p=pathlib.Path(t.name); gh=p/"gh"; gh.write_text("#!/bin/sh\nprintf '\''{\"title\":\"Example\",\"body\":\"Details\"}'\''\n"); gh.chmod(0o755); r=subprocess.run(["bash",str(root/"scripts/from-issue.sh"),"https://github.com/example/project/issues/42","--new"],env=dict(os.environ,UNCLE_PROJECT_ROOT=str(p),PATH=str(p)+os.pathsep+os.environ["PATH"]),capture_output=True,text=True); print("exit:",r.returncode,"requirements:",(p/"REQUIREMENTS.md").exists(),"change:",(p/"CHANGE_REQUEST.md").exists()); print(r.stdout.strip()); raise SystemExit(r.returncode)'
```

## 9. Baseline test results
| ID | Command | Result |
|---|---|---|
| T-4 | 1,5 | Exit 0; shell syntax |
| T-5 | 2 | Exit 0; passed |
| T-6 | 3 | Exit 0; 8 tests OK |
| T-7 | 4 | Exit 0; 231 checks passed |
| T-8 | 6 | Exit 1; B-1 reproduced |

## 10. Existing failures, warnings, and flaky behavior
F-1: T-8 fails; flakiness unverified.

## 11. Reproduction result for the reported bug, if applicable
R-1: Mocked issue fetch reproduces inability to create requirements; wrong-file creation with explicit --new was not reproduced (§8/6).

## 12. Likely change surface
S-1: C-3, tests and docs.

## 13. Regression-sensitive components
S-2: B-2/B-4 and I-1–I-3.

## 14. Areas explicitly outside the change
S-3: ASSUMPTION: runners/packaging/closing excluded; owner confirmation needed.

## 15. Unknowns and assumptions
U-1: UNRESOLVED: original UI steps/files; reporter fixture needed.
U-2: UNRESOLVED: markerless preservation; owner to clarify.

## 16. Initial risk assessment
R-2: Medium: overwrite/ownership risks (B-2/I-2).

## Parallel verification groups
```text
2 3 4
```
