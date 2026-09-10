# Baseline report
Omitted sections: none

## 1. Change-request summary
CHANGE_REQUEST.md, Motivation: document-budget fails Windows CI.

## 2. Repository architecture
scripts/README.md: Bash drivers, Python helpers and project-local state.
Dependencies: Formula/uncle.rb, packaging/debian/control, packaging/windows/scoop.json.

## 3. Relevant code paths
| ID | Path / role |
|---|---|
| P-1 | .github/workflows/installers.yml:66: Windows regression runner |
| P-2 | scripts/lib/gates.sh:255: calculation; :338: guard; :398: reviewer handling |
| P-3 | scripts/tests/document-budget-test.sh:163: standalone reviewer fixture |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Budget suite | Exit 1 at diagnostic assertion | §8 commands 2, 6; test:191 | No |
| B-2 | Advisory overflow | Preserves output; continues | Prompt suite; gates.sh:362 | Yes |
| B-3 | Enforced overflow | Decline/EOF blocks; approval saves increase | Prompt suite; gates.sh:366 | Yes |
| B-4 | Windows suite fails | Counts failures; fails CI | installers.yml:73–100, inspected | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Positive limits; artifact override precedence | gates.sh:255 | document-budget-test.sh:12,123 | High; trace passed |
| I-2 | UTF-8 bytes; final unterminated line counted | gates.sh:344 | document-budget-test.sh:9,16 | High; trace passed |
| I-3 | Saved increases scoped to source fingerprint | gates.sh:244 | document-budget-prompt-test.sh:25 | High; passed |

## 6. Current API, schema, and interface contracts
gates.sh:218 defaults: 4000–40000 bytes, 3× source size, 120–1000 lines.
gates.sh:255: global and artifact-specific environment overrides.
gates.sh:338: missing documents fail; overflow follows B-2/B-3.

## 7. Existing automated-test coverage
Commands 2–5 isolate temporary fixtures; no shared ports.
Coverage: budgets, approvals, portability, packaging (install-test.py:22).
UNRESOLVED: other suites unrun; native checks require Windows CI.

## 8. Exact build and test commands executed
```sh
bash -n install.sh scripts/install/homebrew.sh scripts/lib/gates.sh scripts/tests/document-budget-test.sh packaging/windows/python3
bash scripts/tests/document-budget-test.sh
bash scripts/tests/document-budget-prompt-test.sh
python3 -B scripts/tests/windows-portability-test.py -q
python3 -B scripts/tests/install-test.py -q
python3 -B -c 'import subprocess,sys; p=subprocess.run(["bash","-x","scripts/tests/document-budget-test.sh"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True); print("\n".join(p.stdout.splitlines()[-14:])); sys.exit(p.returncode)'
```

## 9. Baseline test results
| ID | Command | Result |
|---|---|---|
| T-1 | 1 | PASS, exit 0 |
| T-2 | 2, 6 | FAIL, exit 1; document-budget-test.sh:191 |
| T-3 | 3 | PASS, exit 0 |
| T-4 | 4 | PASS; 18 run, 2 Windows-only skips |
| T-5 | 5 | PASS; 10 tests including Debian build |

## 10. Existing failures, warnings, and flaky behavior
T-2 repeats; T-3 warnings expected; flakiness unestablished.

## 11. Reproduction result for the reported bug, if applicable
Darwin/Bash 3.2 reproduces suite failure; Windows equivalence UNRESOLVED pending CI.

## 12. Likely change surface
P-3 fixture; P-2 dependencies.

## 13. Regression-sensitive components
P-2 serves both stagegate.sh:942 and change-workflow.sh:1547.

## 14. Areas explicitly outside the change
ASSUMPTION: UI, agents, budget policy excluded; request gives no exclusions.

## 15. Unknowns and assumptions
ASSUMPTION: T-2 reflects omitted repair-acceptance.py (test:164; gates.sh:402). Confirm via hidden rejected output.
Preexisting edits: BASELINE_REPORT.md, CHANGE_REQUEST.md, CHANGE_SPEC.md, README.md (git status; unchanged after tests).

## 16. Initial risk assessment
Moderate: shared guard; Windows and causality unverified.

## Parallel verification groups
```text
2 3 4 5
```
