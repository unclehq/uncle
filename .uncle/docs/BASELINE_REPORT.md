# Baseline: Issue 254

Omitted sections: Reproduction (reproduced by code reading, not execution); Existing failures (driver baseline is authority)

## 1. Change-request summary
See CHANGE_REQUEST.md (Issue 254). PR body always ends `Closes <origin>` for a bound issue, even over NOT_READY, override, or BLOCKED acceptance rows. Wanted: `Closes` only for finished work, else `Refs` + "Still open" list; README update.

## 2. Repository architecture
Shell/Python workflow driver. `scripts/lib/change-pr.sh` embeds Python that builds and publishes the PR from a journal `j`. `scripts/lib/attestation.py` embeds the attestation block into the body.

## 3. Relevant code paths
- `scripts/lib/change-pr.sh:1781-1825` body assembly; Closes appended at 1823-1825.
- `change-pr.sh:1785-1808` banners (release_skipped, unattended waiver, override record via `override_record()` :995).
- `change-pr.sh:1882` draft decision.
- `change-pr.sh:464` `blocking_findings()` parses FINAL_AUDIT.md table rows where last cell is YES.
- `change-pr.sh:525` `release_blocked_reason`.
- `scripts/lib/attestation.py:318-335` `attach_body` strips trailing lines starting `Closes ` as a trailer.
- `scripts/README.md:405-413` documents Closes.
- Acceptance tables: `## Acceptance delivery` (IMPLEMENTATION_NOTES.md, cols ID|Status|...) and `## Acceptance gate` (VERIFICATION_REPORT.md, cols ID|Required|Status|Evidence); see `scripts/tests/acceptance-test.sh:20`, `plan-executability-test.py:321`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Publish with bound origin, any verdict | body ends `Closes owner/repo#N` | change-pr.sh:1823 | Only when finished |
| B-2 | Publish without origin | no Closes line | change-pr.sh:1823, README:412 | Yes |
| B-3 | Failing audit/override | banners + draft PR | :1785-1808, :1882 | Yes |
| B-4 | attach_body with trailing Closes | block inserted before trailer | attestation.py:325, attestation-test.py:310 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Attestation block precedes trailer lines | attestation.py:325 | attestation-test.py:310,413 | High |
| I-2 | Creating PR never closes issue / writes issue-closed | README:405 | not located | Medium |

## 6. Interface contracts
PR body text only; journal `j` fields origin (tab-separated repo, number, ...), release_skipped, body. No schema change.

## 7. Existing automated-test coverage
attestation-test.py and attestation-statement-test.py cover Closes trailer. pr-auto-publish-test.sh, pr-publish-reason-test.sh, pr-verdict-binding-test.sh drive publish with a fixture origin (`pr-auto-publish-test.sh:13`). Shell runner and Python runner use separate temp dirs and no shared ports, so they can run in parallel (documented in task contract).

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (existing). No results produced here; driver baseline in `.uncle/workflow/green-check.baseline.tsv` is authority. Some Python suites may already fail on clean checkout per Uncle convention.

## 12. Likely change surface
`scripts/lib/change-pr.sh` (1823-1825), `scripts/lib/attestation.py` (325), `scripts/README.md` (405-413), new shell test, `scripts/tests/attestation-test.py`, `scripts/tests/critical-suites.txt`.

## 13. Regression-sensitive components
attach_body trailer handling; unattended publish path; PR body re-reading by attestation verification.

## 14. Outside the change
Audit verdict computation, release gating, draft logic, reopening #235/#236 (manual post-fix action).

## 15. Unknowns and assumptions
- Verdict source for READY vs READY_WITH_NON_BLOCKING_ISSUES vs NOT_READY at body time: assumed derivable from FINAL_AUDIT.md verdict text and release_skipped; to be confirmed during implementation by inspecting how `waived_stages`/verdict_run are read.
- Unparseable/missing acceptance tables treated as not blocked only if no table exists.

## 16. Risk
Medium-low: small localized change; risk is false `Refs` on READY work (safe direction) or false `Closes` if parsing misses BLOCKED rows.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

