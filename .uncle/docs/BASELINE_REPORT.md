# Baseline report (Issue 233)

Omitted sections: Reproduction result (reproduced by reading code, not by a run; see 11 note); Areas outside change merged into 14.

## 1. Change-request summary
Hand-off mode (`UNCLE_PUBLISH_MODE=handoff`) never writes `.uncle/attestation.json`/`.sig`, so `handoff.json` omits them and `uncle verify <pr>` has nothing to read. See `.uncle/docs/CHANGE_REQUEST.md`.

## 2. Repository architecture
Bash driver `scripts/lib/change-pr.sh` embeds a Python program (`pr_code` heredoc, line 367 on) invoked per action (`main()` at ~1860). `scripts/lib/handoff_export.py` is a separate script run by the hand-off branch. `scripts/lib/attestation.py` seals the PR-body summary; `scripts/lib/envelope.py` builds/signs the Statement. `scripts/uncle-verify.py` verifies.

## 3. Relevant code paths
- change-pr.sh:207-213 hand-off branch (runs handoff_export.py, returns; never calls attest).
- change-pr.sh:615-682 `attest(j)`: release envelope, Statement, signature, `write_attestation_files`, `audited_tree=commit_tree`, `commit_tree=snapshot(True, attestation=True)`; raises AttestationError when `blocking_reason` and no `release_skipped`.
- change-pr.sh:565-576 `consent_entry`; :420-432 `sealed_attestation`; :450 `envelopes_enabled`; :727 `save`; :919 `load`.
- change-pr.sh:1753-1766 normal publish call site; :2012-2019 AttestationError -> `PR pending: Attestation blocked: ...`, exit 3.
- handoff_export.py:60-80 `changes`; :83-122 `main` (tree from `commit_tree` :89, sealed summary :94-97, handoff dict :113-116).
- uncle-verify.py:424-426 reads attestation from PR head.
- GITHUB_INTEGRATION.md:75-83 hand-off docs.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Hand-off with envelopes | `handoff.json` `changes` lacks attestation files; `tree` = bind-time tree | handoff_export.py:89,112 | No (modify) |
| B-2 | Hand-off, run predating envelopes | Hand-off with summary only, exit 0 | handoff_export.py:94-97; test `test_applying_handoff_gives_the_audited_tree` | Yes |
| B-3 | Hand-off, missing journal | exit 1 `Hand-off failed` | handoff-export-test.py:78 | Yes |
| B-4 | Normal publish with envelopes | attest(j), attestation files in commit | change-pr.sh:1753 | Yes |
| B-5 | Hand-off, tracked `.uncle/allowed_signers` | in tree, not deleted | change-pr.sh:780-782 | Yes |
| B-6 | Hand-off success | exit 0, `CHANGE_PR_EXTRAS_REASON=handoff` | change-pr.sh:208-210 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Applying `changes` to `base_commit` yields exactly `tree` | `changes()` is a full diff-tree | handoff-export-test.py:56 | High |
| I-2 | Bind-time snapshot excludes attestation files; they enter only via `snapshot(attestation=True)` | change-pr.sh:827-832,884-890 | attestation tests (unverified which) | Medium |
| I-3 | Blocking policy refuses before any git write unless `release_skipped` | change-pr.sh:652-653 | unverified | Medium |
| I-4 | Hand-off never pushes or calls gh/remote | hand-off branch returns early | handoff-export-test.py | Medium |

## 6. Interface contracts
`handoff.json` schema (`SCHEMA` in handoff_export.py): base_commit, head_branch, base_repo, commit_message, pr_title, pr_body, draft, audit_verdict, tree, attestation, changes[]. Journal keys `commit_tree`, `audited_tree`, `statement`, `signature`, `attestation`. Driver exit codes: 0 ok, 1 failure, 3 attestation blocked. Schema consumers: `scripts/tests/implementation-handoff-schema-test.sh` (unclear whether it covers handoff.json; verify).

## 7. Existing automated-test coverage
`scripts/tests/handoff-export-test.py` (fixture has no `envelopes` dir, so exercises the summary-only path). `attestation-test.py`, `attestation-statement-test.py`, `build-attestation-test.py`, `tree-attested-final-audit-test.sh`. No test covers hand-off with envelopes. Shell and Python runners are independent (separate temp dirs), so grouped.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (CLAUDE.md/stage instructions). Not run here; the driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites may already fail on a clean checkout (documented by the stage instructions); not enumerated.

## 10. Existing failures
None documented in repo beyond the note above. UNRESOLVED until driver baseline lands.

## 11. Reproduction
Static: hand-off branch returns before any `attest` call, and `changes()` diffs bind-time `commit_tree`. Not executed.

## 12. Likely change surface
change-pr.sh (new action + hand-off branch + consent_entry), handoff_export.py, tests, GITHUB_INTEGRATION.md.

## 13. Regression-sensitive components
normal publish `attest()`; `consent_entry`; the `attestation` journal field consumed by publish resume; handoff.json consumers (hosts).

## 14. Outside the change
Normal publish flow, stagegate.sh new-project path, uncle-verify.py logic, `.gitignore` handling, envelope.py format.

## 15. Unknowns and assumptions
- Whether envelope.py/uncle-verify accept a non-human `approved_by` on the publication approval for hand-off (assumed: free-form string; implementer verifies by symbol read).
- Whether implementation-handoff-schema test constrains handoff.json keys (assumed no).

## 16. Risk
Medium: edits shared `attest()` call context and consent entry; mitigated by new action leaving normal path untouched.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- handoff-export
```

## Parallel verification groups

```text
1 2
```

