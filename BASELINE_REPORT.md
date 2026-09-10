# Baseline report
Omitted sections: none

## 1. Change-request summary
See CHANGE_REQUEST.md, Motivation; PR handoff already exists.

## 2. Repository architecture
scripts/README.md: Bash drivers, CLI adapters, curses UI, `.uncle/workflow` state.
`packaging/debian/control:7` requires Bash ≥3.2, Python ≥3.9, Git, jq, curl, certificates, and gh.
Packaging: `scripts/install/build-package.py:15`.

## 3. Relevant code paths
PR = `scripts/lib/change-pr.sh`; CF = `scripts/tests/close-flow-test.sh`.

| ID | Path | Role |
|---|---|---|
| P-1 | scripts/change-workflow.sh:1786,1939 | Freeze/bind audit; COMPLETE dispatch |
| P-2 | PR:301 | Prompt, commit, push, create/reconcile PR |
| P-3 | scripts/from-issue.sh:172,388 | Git fallback guard; seeded summary |
| P-4 | uncle_tui.py:1546 | Prompt detection and editable default |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Git completion | PR with closing reference | CF:1128 | Yes |
| B-2 | Title prompt | 72-character summary or fallback | PR:193; CF:1309 | Yes |
| B-3 | Publication prompt | Requests summary/manual steps/consent | PR:338 | UNRESOLVED: §15 |
| B-4 | Decline/EOF/auth failure | PR remains pending | CF:1174 | Yes |
| B-5 | No `.git` | Legacy immediate-close gate remains | scripts/change-workflow.sh:1939; CF:822 | Yes: no PR |
| B-6 | Disabled/unattended | No PR prompt | PR:4 | Yes |
| B-7 | Resume created PR | No duplicate create | CF:1150 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Content matches audit | PR:153 validate | CF:1183 | High |
| I-2 | Unknown outcome blocks recreate | PR:321 | CF:1249 | High |
| I-3 | PR leaves issue open | PR:301 handoff | CF:1150 | High |
| I-4 | Legacy close requires owned READY/hash/origin | scripts/lib/issue-close.sh:issue_close_eligible | CF:892,919 | High |

## 6. Current API, schema, and interface contracts
| ID | Contract | Evidence |
|---|---|---|
| C-1 | Version-1 `.uncle/workflow/pr/journal.json`; seven phases | PR:138 |
| C-2 | Origin TSV: repo/issue/method; legacy=curl | scripts/lib/issue-close.sh:origin_fetch_method |
| C-3 | Prompt terminates `]:`; chunked Unicode supported | scripts/tests/pr-prompt-test.py |
| C-4 | `WORKFLOW_CLOSE_ISSUE=0` suppresses handoff | PR:4 |

## 7. Existing automated-test coverage
CF isolates Git/gh fixtures; covers drift, forks, retries, worktrees and closure.

## 8. Exact build and test commands executed
```sh
bash -o pipefail -c 'bash scripts/tests/close-flow-test.sh 2>&1 | tail -12'
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/pr-prompt-test.py -q
bash -n scripts/change-workflow.sh scripts/from-issue.sh scripts/lib/change-pr.sh scripts/lib/issue-close.sh
bash -o pipefail -c 'bash scripts/tests/tui-session-panel-test.sh 2>&1 | tail -8'
```

## 9. Baseline test results
| ID | Command position | Result |
|---|---|---|
| T-1 | 1 | PASS: 231 checks, 28 Python tests |
| T-2 | 2 | PASS: 5 tests |
| T-3 | 3 | PASS: syntax |
| T-4 | 4 | PASS: 14 tests |

## 10. Existing failures, warnings, and flaky behavior
All checks exit 0; no warnings. Flakiness unverified: single run.

## 11. Reproduction result for the reported bug, if applicable
No bug steps in CHANGE_REQUEST.md; feature exercised by CF.

## 12. Likely change surface
Inferred: P-1–P-4, CF.

## 13. Regression-sensitive components
I-1–I-4; remote identity resolution (PR:231), shared prompt parsing (P-4).

## 14. Areas explicitly outside the change
ASSUMPTION: new-app driver/installers/adapters; request gives no exclusions.

## 15. Unknowns and assumptions
UNRESOLVED: 25 staged paths include PR code (`git status --short`); pre-feature behavior requires historical checkout.
UNRESOLVED: live merge closure, Windows/TTY, builds and wider suites require platform/full-suite checks.
UNRESOLVED: B-3 versus automatic description; needs request clarification.

## 16. Initial risk assessment
High impact: I-1/I-2 regressions permit unaudited publication/duplicate PRs.
