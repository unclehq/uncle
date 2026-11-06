# Change plan: Uncle must create and push a PR when appropriate

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (none); Feature flag (none, containment is revert).

Issue 0

## 1. Selected technical approach

Reproduce the skip with a stub-engine harness, then (a) make `change_pr_publish` record a distinct `CHANGE_PR_EXTRAS_REASON` and a stderr line on each early return and on handoff failure/success, (b) stop `change_pr_complete` overwriting the reason, (c) add labels in finished_extras.py, (d) fix any proven defect on the skip path. The AC-5 fix may correct gate inputs (as with the FINAL_AUDIT.json artifact path) but may not remove or loosen any gate, including the `issue_close_eligible ... || return 0` and `assert_tree_matches_attested` checks; any such change is a deviation needing human approval.

## 2. Alternatives
- Make publish return nonzero: rejected; driver treats rc!=0 as `--stopped` and exit semantics B9 must stay.
- Parse engine stdout for the reason: rejected; fragile.

## 3. Why preferred
Smallest change; no gate touched; reporting only plus proven fix.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
change-workflow.sh, engine Python gating/attestation, home_agent_session.py, gate_answer.py, supervisor, dialogs, existing tests.

## 6. Data flow
Reason flows: publish sets CHANGE_PR_EXTRAS_REASON -> complete keeps it -> change_pr_extras_print -> finished_extras.py.

## 8. Interfaces

New reason keys: published, published-draft-unreviewed, validate-failed, verdict-not-ready, issue-not-eligible, tree-mismatch, handoff-failed. Fallback publication-pending when publish sets none. Publishing over a non-READY verdict (an operator override, or UNCLE_AUTO_PUBLISH) records published-draft-unreviewed instead of published when handoff exits 0; its stderr line is 'PR published as unreviewed draft: published-draft-unreviewed: verdict <class>'. Static text only: no engine/gh output, URLs or env values. Mapping for the early returns in change_pr_publish after `change_pr_engine validate`: validate exit 3 with no override available (neither interactive nor UNCLE_AUTO_PUBLISH), or with `verdict-override` declined or failing, sets verdict-not-ready; any other nonzero validate exit (including exit 1), and a failing re-validate after a successful override, set validate-failed. Each of these four early returns still returns 0, with the key set first.

Render rule: finished_extras.py renders a label only for allowlisted reason keys (the new keys above plus the existing ones); any other or malformed value, including empty, multi-line or unknown text, renders as the publication-pending label and is never echoed verbatim. The spec's claim that unknown keys already fall back safely is not relied on; the allowlist is verified by test.

## 10. Compatibility
Bash 3.2: no associative arrays, no `${var,,}`; exit status unchanged.

## 12. Error and recovery
Handoff exit status captured (`rc=0; change_pr_engine handoff || rc=$?`) then reported; still `return 0`.

## 14. Rollback plan
Revert the change commit; no persisted state altered.

## 16-17. Automated and regression tests

New `scripts/tests/pr-publish-reason-test.sh` sources change-pr.sh and covers success and each failure path (AC-1..4) with `change_pr_engine`, `issue_close_eligible`, `assert_tree_matches_attested`, `origin_field` and `origin_fetch_method` stubbed for those unit paths, plus a grep that the engine push has no force flag (SI3). The AC-5 regression test is different: it runs the real `issue_close_eligible` and `assert_tree_matches_attested` (and the real engine) on a fixture repo with signing disabled; only `gh` and network are stubbed. It is added once step 1 identifies the path and must fail on pre-fix code. Existing pr-auto-publish-test.sh must still pass untouched.

## 18. Manual verification

Handoff exit status captured (`rc=0; change_pr_engine handoff || rc=$?`) then reported; still `return 0`. `published` is set only when handoff exits 0 and the journal phase is `created`; exit 0 with any other phase (declined or early-return paths) records `handoff-incomplete`; nonzero exit records `handoff-failed`. Tests cover each outcome.

Also confirm the printed `PR not created:` line, when one appears, contains no URL, token or tool output.

## 19. Observability
One stderr line per no-PR path; accurate finished-block label.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Constraints | SI1, SI2 | Gates unchanged: no gate in change_pr_publish may be removed or loosened; AC-5 may correct gate inputs only | No edits to gate conditions; a fix may change the inputs a gate receives but never its pass criteria; any gate removal or loosening is a deviation needing human approval | Request | none | change-pr.sh:120-159 inspected | CODING |
| R-2 | USER | CHANGE_REQUEST Constraints | SI3 | No force push | No push edits; test greps | Request | none | change-pr.sh:1589 inspected | CODING |
| R-3 | USER | CHANGE_REQUEST Constraints | AC-6 | Bash 3.2 | Plain bash constructs | Request | none | existing style | CODING |
| R-4 | DESIGN | plan | SB1-2 | Reporting via env var reason | CHANGE_PR_EXTRAS_REASON | Existing channel | none | change-pr.sh:15-20 | CODING |

Live GitHub verification needs `gh auth` and a remote (CAP-LIVE-GH, LIVE_VERIFICATION phase only); it does not block coding. Live check: manual section 18; no secrets recorded.

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/change-pr.sh` | Reasons and stderr lines in change_pr_publish; stop overwrite in change_pr_complete; fix proven defect | SB1-SB3 | Medium: publish ordering | pr-publish-reason-test.sh, pr-auto-publish-test.sh, pr-verdict-binding-test.sh |
| `scripts/lib/finished_extras.py` | Add labels for new keys | AC-4 | Low | new test |
| `scripts/tests/pr-publish-reason-test.sh` | New suite | AC-1..5 | None | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1. When ORIGIN_FILE is empty the issue gate (issue_close_eligible) is skipped and publication proceeds to the tree assertion and handoff; the test matrix in pr-publish-reason-test.sh includes this case, asserting no issue-not-eligible reason is recorded. | SB1 | SI1, SI2 | change-pr.sh | pr-publish-reason-test.sh | Section 18 |
| AC-2: each no-PR path adds exactly one new stderr line formatted 'PR not created: <key>: <detail>', in addition to (never replacing) existing diagnostics such as assert_tree_matches_attested stderr output, 'Publish refused', and the engine's stdout 'PR pending:'. | SB2, SB5 | SI4 | change-pr.sh | pr-publish-reason-test.sh | Section 18 |
| AC-3: change_pr_complete never assigns CHANGE_PR_EXTRAS_REASON after change_pr_publish returns, at any of its three call sites (unattended change-pr.sh:70, headless :98, interactive :104). The unconditional `CHANGE_PR_EXTRAS_REASON=publication-pending` assignments after publish at :70 and :98 are deleted; publication-pending is set only when publish left the reason empty. The handoff-disabled assignment at :93 is kept. The interactive path at :104 already preserves the reason. | SB1 | SI4 | change-pr.sh | pr-publish-reason-test.sh | Section 18 |
| AC-4 | SB2 | SI4 | finished_extras.py | pr-publish-reason-test.sh | Finished block |
| AC-5: any proven defect on the skip path is fixed with a regression test that fails on pre-fix code; the fix may correct gate inputs but may not remove or loosen any gate (SI1/SI2). | SB3 | SI1-3 | change-pr.sh | pr-publish-reason-test.sh (regression; real issue_close_eligible and assert_tree_matches_attested on a fixture, only gh and network stubbed) | Section 18 |
| AC-6 | SB4 | SI3 | all | both runners | none |

## Implementation sequence

1. Reproduce: using a throwaway repro script kept outside the repo (e.g. under /tmp), build a fixture (temp git repo, signing disabled, bare local remote, `gh` stubbed on PATH) and run change_pr_publish with the REAL issue_close_eligible, assert_tree_matches_attested and engine to find which path skips publication; record the path in IMPLEMENTATION_NOTES.md. This step does not touch scripts/tests/pr-publish-reason-test.sh, which step 4 alone owns.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
2. Reporting changes in change_pr_publish/change_pr_complete and fix of any proven defect; builds on step 1 harness only for verification, edits a different file. Reason keys and stderr: on each no-PR path add exactly one new stderr line 'PR not created: <key>: <detail>'; existing stdout/stderr messages are left untouched. change_pr_publish clears CHANGE_PR_EXTRAS_REASON on entry (no stale reason on a direct call) and sets a non-empty key on every no-PR return. Validate mapping: exit 3 with no override, or a declined/failed verdict-override -> verdict-not-ready; any other nonzero validate exit, and a failing re-validate after override -> validate-failed. Gate branches: empty ORIGIN_FILE skips the issue gate and sets no reason (never issue-not-eligible); under a non-READY override the issue gate is not run and no issue-not-eligible is recorded (issue stays open, publication continues); issue-not-eligible is set only when issue_close_eligible actually runs and fails; empty commit-tree (fallback attested="") with a failing assert_tree_matches_attested records tree-mismatch. Existing gate conditions and `|| return 0` returns are kept; only a reason assignment is added before each. Handoff outcome: capture the exit code (`rc=0; change_pr_engine handoff || rc=$?`); any nonzero rc (declined consent, PR pending exits 1 or 3) records handoff-failed with the exit code in the stderr line; rc 0 with journal phase not `created` records handoff-incomplete (add to the key set); rc 0 with phase `created` (including already-created rerun and override-created PRs) records published, or published-draft-unreviewed when the verdict class is not READY/READY_WITH_NON_BLOCKING_ISSUES (override or UNCLE_AUTO_PUBLISH), with a stderr line naming the verdict and stating draft vs ready so a draft is never reported as ready. A handoff exit 0 is never recorded under any other key. publish still returns 0. change_pr_complete never assigns CHANGE_PR_EXTRAS_REASON after change_pr_publish returns, except publication-pending when still empty: delete the unconditional assignments at change-pr.sh:70 (unattended) and :98 (headless) and replace each with an if-empty fallback; the :104 attended call has no assignment and stays consistent; the handoff-disabled assignment at :93 stays since publish is not called there. The fix may correct gate inputs but must not remove or loosen any SI1/SI2 gate (issue_close_eligible, tree assertion); any such change is a recorded deviation needing human approval. Verify against the step 1 real-gate fixture (real issue_close_eligible and assert_tree_matches_attested; only gh and network stubbed). Step 4 tests cover the empty-ORIGIN_FILE, empty-commit-tree, rerun and override-created cases.
   Owns: `scripts/lib/change-pr.sh`
   Depends on: 1
3. Add labels for new reason keys in finished_extras.py, and make rendering allowlist-only: any value not in the allowlist renders as publication-pending, never verbatim. Test unknown, empty and malformed values.
   Owns: `scripts/lib/finished_extras.py`
4. Create and finalize scripts/tests/pr-publish-reason-test.sh (sole owner), capturing stderr. Matrix with exact-key assertions: (1) validate exit 1 -> validate-failed; validate 3 with declined override -> verdict-not-ready; validate 3 then failing re-validate -> validate-failed; (2) empty ORIGIN_FILE bypasses issue gate and reaches handoff, no issue-not-eligible; non-READY verdict under override; issue_close_eligible failure -> issue-not-eligible; empty commit-tree failing assert -> tree-mismatch; ineligible issue or mismatched tree yields no handoff call (gates intact); (3) handoff stub exit 0 (rerun with phase created, override-created) -> published, exit 1 (decline) and 3 -> handoff-failed with the exit code in the line; release_skipped draft stated in line; UNCLE_AUTO_PUBLISH=1 with non-READY verdict -> published-draft-unreviewed naming the verdict; handoff exit 0 without phase created -> handoff-incomplete; (4) CHANGE_PR_EXTRAS_REASON preset to a sentinel is replaced on every path, including success; (5) exactly one stderr line beginning 'PR not created: <key>' per no-PR path, including tree-mismatch with multiple existing stderr lines, existing messages intact; (6) canary token and credentialed URL emitted by stub engine/gh never appear in the reason line; (7) change_pr_complete table test over unattended, headless and interactive paths: publish stub's reason survives, empty becomes publication-pending, handoff-disabled unchanged; (8) finished_extras.py invoked from this suite with each allowlisted key, an unknown key and a malformed value, asserting labels and publication-pending fallback; (9) AC-5 regression using real gates, shown failing on pre-fix code; diff check that no gate condition was removed. Add the suite to the plan's verification commands and protected paths.
   Owns: `scripts/tests/pr-publish-reason-test.sh`
   Depends on: 1, 2, 3

## 21. Scope cuts
Cut first: the live-fixture reproduction harness fidelity (keep stubbed engine tests); then finished_extras labels (fallback label stays valid). Never cut reason reporting or gate preservation.

## 22. Risks

- Root cause may be outside change-pr.sh (e.g. state files); then record a deviation and stop for new authority.
- Stubs in other suites define change_pr_publish; new variables must not break them.
- The `PR not created: <key>` stderr line contains only the reason key and a fixed static message (plus the numeric handoff exit code where applicable), never engine/gh output, remote URLs, tokens or environment values; tests assert this with a credentialed-URL canary in the stub remote.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | change_pr_publish has four silent return-0 branches after validate; the plan listed keys without mapping exits to keys. | s7.1 gains an explicit exit-to-reason mapping; step-2 text requires implementing it. |
| AR-002 | Accepted | change-pr.sh:70 and :98 unconditionally overwrite the reason after change_pr_publish; naming those lines makes AC-3 scoped and testable. | AC-3 and step-2 now delete the post-publish assignments at change-pr.sh:70 and :98, fall back to publication-pending only if empty, keep handoff-disabled. |
| AR-003 | Accepted | Handoff exit 0 can mean an already-created PR and a declined consent exits 1, so 'published' needs a strict definition. | Step 2 now states published means handoff exit 0 only; any nonzero exit (including declined consent) is handoff-failed with the exit code in the stderr line. |
| AR-004 | Accepted | The gate branches after validate (empty ORIGIN_FILE, non-READY override, empty commit-tree) had no stated reason mapping. | Step 2 text now maps each branch to a reason; step 4 tests the empty-ORIGIN_FILE and empty-commit-tree cases. |
| AR-005 | Accepted | Existing stderr/stdout diagnostics (Publish refused, PR pending) must stay; a single added, uniformly formatted line avoids conflict with them. | AC-2 requirement and step-2 now specify exactly one added stderr line 'PR not created: <key>: <detail>', leaving existing messages untouched. |
| AR-006 | Accepted | change_pr_publish only inherits a reset from change_pr_complete, so a direct call could report a stale reason; clearing on entry fixes that. | Step 2 now requires change_pr_publish to clear CHANGE_PR_EXTRAS_REASON on entry and set a non-empty key on every no-PR return. |
| AR-007 | Accepted | change_pr_complete's unattended (line 70) and headless (line 98) branches unconditionally overwrite the reason after change_pr_publish, making AC-3 ambiguous about call sites. | Edit step-2 and AC-3 to remove both post-publish assignments and set publication-pending only when publish left the reason empty. |
| AR-008 | Accepted | The four silent return-0 sites in change_pr_publish (change-pr.sh:120-129) need an explicit exit-to-key mapping or SI4 cannot hold. | Section 8 text gains a validate-exit-to-reason mapping, and step 2 is amended to implement it. |
| AR-009 | Accepted | Handoff exit 0 also occurs on the already-created rerun and on override-created PRs, so the plan must say exactly when published is recorded. | Step 2 text now states published is set only when handoff exits 0, including rerun and override paths; any nonzero exit is handoff-failed. |
| AR-010 | Accepted | Handoff exit 0 can be a draft PR over a failed audit, and nonzero exits include declined consent, so success and failure need precise definitions. | Step 2 now specifies: handoff-failed for any nonzero rc; published only on rc 0; stderr line states draft vs ready. |
| AR-011 | Accepted | change_pr_publish only inherits the reset done in change_pr_complete, so a direct call could surface a stale reason. | step-2 now requires change_pr_publish to clear CHANGE_PR_EXTRAS_REASON on entry and set a non-empty key on every no-PR return. |
| AR-012 | Accepted | The reason line could leak engine/gh output, URLs or tokens if not constrained; a static-content rule is cheap and safe. | Add a content rule to s19.1 and a test assertion to s12.1 that the stderr reason line holds only the key and a static message. |
| AR-013 | Accepted | The render rule for unknown or malformed reason values was unstated, and the spec's 'fall back safely' claim was uncited. | s7.1 now states finished_extras.py renders only allowlisted keys and anything else as publication-pending; step-3 owns implementing and testing it. |
| AR-014 | Accepted | Publishing a draft over a non-READY verdict via override or UNCLE_AUTO_PUBLISH must not be reported as plain 'published' once complete stops overwriting the reason. | Section 8 adds key published-draft-unreviewed with stderr line naming the verdict; step-2 implements it. |
| AR-015 | Accepted | The plan allowed fixing any proven defect but did not say the SI1/SI2 gates in the wrapper may not be loosened; the finding is correct. | Edit s1.1(d), R-1, step-2 and AC-5 so fixes may correct gate inputs but not remove or loosen a gate, and any such change is a deviation needing human approval. |
| AR-016 | Accepted | Stubbing the real gate functions would hide the likely silent skip at change-pr.sh:145-148/159, so the AC-5 regression must run them for real. | Edit s11.1, AC-5 traceability row and step-2 text: AC-5 regression runs real issue_close_eligible and assert_tree_matches_attested on a fixture; only gh and network are stubbed. |
| AR-017 | Accepted | The four silent return-0 paths after validate need explicit reason keys; the plan listed keys without a mapping. | Section 8 text and step-2 now map validate exit 1/other failures and failing re-validate to validate-failed, exit 3 with no or declined override to verdict-not-ready. |
| AR-018 | Accepted | Real gap: lines 69-71 and 97-99 overwrite the reason while 104 does not, and the plan never states a per-path rule. | Step-2 and AC-3 now require change_pr_complete to never assign the reason after publish returns, except publication-pending when empty, on all three call sites. |
| AR-019 | Accepted | Existing stderr and engine stdout diagnostics make 'one stderr line' ambiguous; the added line must be defined as additive and fixed in format. | AC-2 requirement and step-2 now say each no-PR path adds exactly one new stderr line 'PR not created: <key>: <detail>', leaving existing diagnostics untouched. |
| AR-020 | Accepted | Handoff exit 0 also occurs on declined/early-return paths, so exit status alone cannot prove a PR exists. | step-2 and s12.1 require published only when handoff exits 0 and the journal phase is created; otherwise handoff-incomplete. |
| AR-021 | Accepted | The empty ORIGIN_FILE path skips the issue gate and is a real untested branch of change_pr_publish. | Add an empty-ORIGIN_FILE case to the test matrix (step-2 note, AC-1 requirement) and state the issue gate is skipped there. |
