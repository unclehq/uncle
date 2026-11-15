# Baseline report

Omitted sections: Reproduction result (feature, not a bug); Baseline test results as run (driver supplies them, see section 9)

## 1. Change-request summary
Issue 283 (`.uncle/docs/CHANGE_REQUEST.md`): add an `--oss` launcher flag so a change run against an upstream open-source issue follows that project's submission and testing guidelines, records each with a source, surfaces conflicts at a human gate, stops before PR creation if the project forbids AI-assisted PRs, and leaves behavior unchanged without the flag.

## 2. Repository architecture
* `uncle` (bash launcher, 1203 lines): parses flags, exports env (`UNCLE_NO_FOOTPRINT`), dispatches to `scripts/from-issue.sh` / `scripts/change-workflow.sh`.
* `scripts/change-workflow.sh` (5323 lines): existing-code driver; stage prompts live in `prompts/change/*.md`.
* `scripts/lib/change-pr.sh` (2357 lines): embedded Python publishes the PR; run journal at `.uncle/workflow/pr/journal.json`.
* `scripts/lib/footprint.py` (140 lines): pure no-footprint rendering and vocabulary scan (Issue 280).
* Tests: `scripts/tests/*-test.py` (Python), `*-test.sh` (shell); default tier listed in `scripts/tests/critical-suites.txt`.

## 3. Relevant code paths
| Path | Lines | Role |
|---|---|---|
| `uncle` | 127, 165, 344, 351, 440 | `--no-footprint` help text, flag var, revalidate arg allow-list, parse, typo-hint list |
| `scripts/change-workflow.sh` | 2097-2120 `bind_change_request_source` | appends the change request to baseline/change-spec/change-plan/updated-change-plan/adversarial-review/manual-checklist prompts |
| `scripts/lib/change-pr.sh` | 33-48, 1523, 1663-1672, 1716-1717, 2147, 2244 | no-footprint detection, branch prefix, tracked-`.uncle` refusal, journal flag, publish body check |
| `scripts/lib/footprint.py` | 89-120 | `render_body`, `render_message`, `scan` |
| `scripts/stagegate.sh` | 480-482 | skips attestation under no-footprint |
| `README.md` | 213-228 | `--no-footprint` documentation |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `uncle ... --oss` | refused as `Unknown argument` / typo hint | `uncle:344`, `uncle:440` | No (changes) |
| B-2 | Change run without `--oss` | Uncle default verification, Uncle-style PR | `scripts/lib/change-pr.sh` | Yes |
| B-3 | `--no-footprint` run | bare tree, maintainer-style body, disclosure, vocabulary scan, `change/` branch | README 213-228; `scripts/tests/no-footprint-test.py` | Yes |
| B-4 | Change stages | prompts carry bound change request only; no upstream-guideline discovery | `change-workflow.sh:2097-2120` | Yes without flag |
| B-5 | PR body | built from `footprint.render_body` (no-footprint) or Uncle audit body; project PR template ignored | `footprint.py:89` | Yes without flag |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | No-footprint publication contains no Uncle artifacts or vocabulary | `footprint.scan`, `change-pr.sh:1663`, `2147` | `no-footprint-test.py` | High |
| I-2 | Mode is fixed in the journal at start; resume cannot flip it | `change-pr.sh:33-41, 1716` | `no-footprint-test.py` | Medium |
| I-3 | Human gates are never bypassed; publication only after audit gate | `stagegate.sh`, change-pr | `gates`, `pr-auto-publish` suites | High |
| I-4 | Unknown launcher args are refused | `uncle:344` | launcher suites | Medium |

## 6. Current interface contracts
* CLI flags and env vars in `uncle` usage text; `UNCLE_NO_FOOTPRINT=1` env contract.
* Journal JSON keys (`no_footprint`, etc.) at `change-pr.sh:1710-1717`.
* Artifact JSON schema `uncle.artifact/v1`.

## 7. Existing automated-test coverage
`scripts/tests/no-footprint-test.py` covers footprint rendering and wiring. PR publication is covered by `pr-auto-commit`, `pr-auto-publish`, `pr-closes-refs` (critical tier). Shell and Python runners are independent (separate temp dirs, no shared ports; per scripts guidance they run together in about the time of the shell suites alone), so they form one parallel group. No test covers guideline discovery, AI-policy refusal or PR-template rendering.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh` and the project's runner guidance. No results were produced in this stage; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites are known to fail on a clean checkout per the runner guidance. Command 3 runs only the new suite, which does not exist yet and is expected to fail or find no tests before the change.

## 10. Existing failures, warnings, flaky behavior
Some Python suites already fail on a clean checkout (documented in the repo runner guidance; names come from the driver baseline). No other known issue.

## 12. Likely change surface
`uncle`, `scripts/change-workflow.sh`, `scripts/lib/change-pr.sh`, new `scripts/lib/oss.py`, new `prompts/change/oss-guidelines.md`, `scripts/tests/oss-test.py`, `scripts/tests/critical-suites.txt`, `README.md`.

## 13. Regression-sensitive components
`uncle` flag parsing (every run), `bind_change_request_source` (every change stage prompt), `change-pr.sh` publish path (the only outward-facing action), no-footprint behavior.

## 14. Areas explicitly outside the change
New-application driver (`workflow.sh`, `stagegate.sh` stages), approval-gate logic, attestation, TUI, reviewer panel prompts other than the bound-request appendix.

## 15. Unknowns and assumptions
* Exact interplay of `--oss` with fork-based PRs depends on remote/`gh` state; assumed unverifiable offline.
* Wiki-only guidance cannot be fetched deterministically.

## 16. Initial risk assessment
| Risk | Level |
|---|---|
| Heuristic AI-policy detection misses or over-matches | Medium |
| Prompt appendix leaks into non-`--oss` runs | Low if gated on env |
| Interaction with no-footprint vocabulary scan | Medium |

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- oss
```

## Parallel verification groups

```text
1 2
```

