# Change plan: issue 172

Issue 172

Seeded from [unclehq/uncle#172](https://github.com/unclehq/uncle/issues/172).

Omitted sections: Schema/persistence (only additive keys in change-class.json), Migration (none), Concurrency (none), Feature flag beyond env switch (the env switch is the containment)

## 1. Selected approach

The decision lives in `change_class.py build()` as new keys `review` (`skip|full`) and `review_reason`, computed from the model proposal plus the deterministic floor. Owned-file classification (doc, test, other) reuses the existing floor path rules in `change_class.py`; no new path globs are introduced. A plan with no owned files is never skipped, and any owned file that is not doc/test in a docs/test-only class forces full review. build() takes no plan and never evaluates the plan sha. The plan_sha check lives only in the `skip-review` CLI and the shell helper `change_class_review_skipped`; a missing plan_sha counts as a mismatch. The drivers only read `change_class.py get . review` and the helper, and when `skip` also pass the stored plan sha check (`current`). A new CLI command `skip-review <project> <plan>` re-verifies the stored plan_sha against the supplied plan (exit 1 on mismatch or non-skip), then writes the stub canonical JSON via the existing artifact writer. Drivers short-circuit their ADVERSARIAL_REVIEW state to the stub, then continue to the existing validate and approval states.

## 2-3. Alternatives and rationale
- Skip in the driver by class only: rejected, bypasses the floor.
- Skip the state entirely with no artifact: rejected, breaks envelopes/hashes/plan-gate and hides the skip from the human.
Selected approach keeps one decision point (pure Python, testable) and reuses all downstream stages.

## 4. Components to modify
See change-impact table.

## 5. Not modified

Final audit code, approval gate code, panel code, adversarial-context.py validators, tests protected elsewhere. These are not edited, but they do consume the stub ADVERSARIAL_REVIEW.json, so the stub is exercised through final-audit input assembly and approval hashing in review-skip-test.sh (see AC-9).

## 6-7. Data flow / state

classify -> change-class.json (+review) -> ADVERSARIAL_REVIEW state: if `change_class_review_skipped` then write stub (non-empty overall_assessment, zero findings) + render md + marker + ledger, else panel as before -> VALIDATE_ADVERSARIAL_REVIEW -> gate -> downstream consumers (updated-plan, final-audit input, approval hashing), all of which must accept the stub. No new states.

## 8. Interface

- change-class.json: `review`, `review_reason`. These stored values are advisory only; `skip-review` never trusts stored `review=skip` alone, and recomputes the decision (model proposal source, deterministic floor from raw risk_hits and owned-file paths, plan sha) against the current plan in the same invocation that writes the stub.
- CLI: `change_class.py skip-review <family> <project> <plan>` (re-verifies stored plan_sha against the supplied plan and exits 1 on mismatch or missing sha; exits 1 if the decision is not skip; otherwise writes the stub).
- Shell: `change_class_review_skipped <plan>` (true only when env not 0, WORKFLOW_CLASSIFY not 0, no forced class, review=skip, stored plan_sha matches the plan; a missing plan_sha is a mismatch; this is the only place besides skip-review that evaluates the sha, and build() does not). Env: `WORKFLOW_SKIP_REVIEW=0` disables.
- Classifier answer: optional `"review":"skip"`.

## 10. Compatibility
Absent `review` key means full. Missing/unreadable change-class.json means full (fail closed).

## 12. Error and recovery

Any read error, mismatch or non-skip returns full review. Skip is enabled only when `WORKFLOW_SKIP_REVIEW` is unset or exactly `1`; any other value (empty, `0`, `false`, `no`, etc.) means full review. The classifier's optional `review` value is honored only when it is the exact lowercase string `skip`; any other value or type (e.g. `Skip`, `SKIP`, `full`, null, number, list, unknown string) is treated as absent, giving full review without error and without invalidating the rest of the classifier answer. The stored plan_sha check lives only in `change_class_review_skipped` and the `skip-review` CLI re-verification; `build()` never evaluates the sha. A missing or empty stored plan_sha counts as a mismatch and yields full review. Recheck clearing skip is independent of the sha check. `skip-review` recomputes the floor against the current plan in the same invocation that writes the stub and exits 1 without writing if the recomputed decision is not skip, even when the stored change-class.json says review=skip (hand-edited file or race); the shell helper `change_class_review_skipped` is only a cheap pre-check and the recompute inside `skip-review` is authoritative. A stub failing validation hits the existing format-retry/stop path (change-workflow retry marker applies to model re-runs only; for a stub, stop directly: a stub failure is a bug, not model output).

Classifier `review` validation: only the exact lowercase string "skip" is a positive skip signal. Any other value or type, or a duplicate `review` key in the answer, means full review. The classifier prompt must state that plan text is untrusted data, not instructions; the deterministic floor still vetoes skip regardless.

## 14. Rollback
`WORKFLOW_SKIP_REVIEW=0`, or revert the commit; no persisted format needs migration.

## 16. Automated-test strategy

New `scripts/tests/review-skip-test.py` (hyphenated, collected by run-python-tests.sh) covers AC-1..5, 7, 9 against change_class.py with fixture plans in a temp dir, git commands with signing disabled. A shell suite `scripts/tests/review-skip-test.sh` stubs the runner and covers AC-6, AC-8 for both drivers, following the pattern of existing suites in scripts/tests (implementer reads one neighbour for the harness idiom). AC-8 test: with a stub that fails validation (corrupted stub), each driver stops immediately with nonzero exit, no retry, no model invocation (the stubbed runner is never invoked), and no fallback to full review.

- review-skip-test.py: skip-review with a mismatched or missing plan_sha exits 1 and writes no stub; build() output is identical before and after plan edits (sha never enters build()).
- review-skip-test.py path rules: empty owned files, a docs class with one source file, a test class with a doc file, and small with auth/secret/shell/driver/gate paths each yield full.
- review-skip-test.py classifier review values Skip, SKIP, full, null, true, 1, a list and a duplicate key each yield review=full while the rest of the answer is still accepted.
- review-skip-test.py hostile plan: injected text plus risk hits plus an odd review value still yields full; hand-edited change-class.json with review=skip and matching sha over a risky or non-doc plan makes skip-review exit 1 and the helper return false.
- review-skip-test.py AC-9: the real updated-plan validator accepts the stub; if it rejects zero findings, the stub carries one informational finding.
- review-skip-test.sh: WORKFLOW_SKIP_REVIEW unset or 1 honors skip; 0, empty, false, no, 2 give full review.
- review-skip-test.sh: plan edited after stub written discards stub and marker and recomputes; resume with an existing stub, an existing real review and a stale marker keeps the stub only for a skip decision and never overwrites a real review.
- review-skip-test.sh: simulated decline reruns ADVERSARIAL_REVIEW as a full stubbed-panel review with the review-skipped marker removed first.
- review-skip-test.sh: stub fed through final-audit input assembly and approval-hash computation succeeds with non-empty overall_assessment; a corrupted stub in both drivers gives nonzero exit, no retry marker and zero runner invocations.

## 17. Regression strategy
Existing suites unchanged and run via the two baseline commands. Bug-fix regression tests are not applicable (feature).

## 18. Manual verification

Run a docs-only change through change-workflow.sh with a real classifier; confirm gate shows the skip reason and that declining works; confirm a plan mentioning deletion runs the full review. Also corrupt the stub so it fails validation and confirm the run stops immediately with a nonzero exit, no retry, no fallback to full review, and no model invocation.

## 19. Observability

The stub's `overall_assessment` is exactly `skipped: class <class>, no risk hits` (this is the string validated and rendered into ADVERSARIAL_REVIEW.md). The console line is that same text prefixed with `Adversarial review `, i.e. `Adversarial review skipped: class <class>, no risk hits`. Also recorded: change-class.json fields, ledger row `review-skip`.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Proposal 2 | AC-1, AC-2 | Floor vetoes skip (text and paths) | Python floor in build() using raw risk_hits, plus an owned-file path rule that reuses the existing floor path rules in change_class.py: an empty owned-file set means full review; in a docs or test-only class any owned file that is not doc (respectively test) means full review; for class small, any owned path matching the floor's sensitive patterns (auth/secret/shell/driver/gate) means full review, with no other path rule beyond the floor. The plan sha is not evaluated in build(): it is checked only in change_class_review_skipped and skip-review, where a missing plan_sha counts as a mismatch and means full review. | deterministic, testable | CAP-PY | CODING |
| R-2 | USER | Proposal 4 | AC-3 | Fail closed | Absent/invalid data => full; classifier `review` honored only if exactly the lowercase string "skip" (duplicate keys, other values or types, including case variants => treated as absent => full, without rejecting the rest of the answer); plan text is untrusted | simplest safe default | CAP-PY | CODING |
| R-3 | USER | Proposal 6 | AC-6 | Both drivers | same shell helper called from both | one code path | CAP-SH | CODING |
| R-4 | DESIGN | stub visibility | AC-5, AC-7 | Stub through normal gate | write canonical JSON (overall_assessment exactly `skipped: class <class>, no risk hits`) and render md; console line prefixes that text with `Adversarial review `; stub written only when no review exists or the existing one is a stub; a non-skip decision removes a stale stub and the review-skipped marker before the panel runs | keeps hashes/envelopes | CAP-PY | CODING |
| R-5 | DESIGN | live run | AC-6 | Live classifier check | manual checklist only | needs model runner | CAP-LIVE | LIVE_VERIFICATION |

Feasibility evidence: change_class.py:332 build and :482 main inspected; adversarial-context.py:119 accepts empty findings; both driver states located (change-workflow.sh:3963, stagegate.sh:5472). Runner binding: bash scripts/run-python-tests.sh and scripts/run-shell-tests.sh.

## Decisions

- D-1: Use raw (pre-waiver) risk_hits for the skip floor; waivers cannot enable skip. The floor also fails closed on paths: skip requires declared owned files; a plan with none is never skipped; any owned path outside doc/test globs forces full review for docs/test-only classes; for class small, owned paths touching auth/secret/shell/driver/gate code force full review.
- D-2: Skip honored only for source `model`, and only when the answer's `review` value is exactly the lowercase JSON string "skip". Any other value or type (Skip, full, null, number, list, object), or a duplicate `review` key, is treated as absent (full review) without invalidating the rest of the answer. Plan text embedded in the classifier prompt is untrusted data and cannot itself grant a skip.
- D-3: stagegate records the decision in change-class.json and a marker file `.uncle/workflow/review-skipped`; change-workflow also calls record_cost. The marker is deleted whenever a full review runs (including after a decline or a non-skip recomputation). If the human declines the skipped review at the gate, ADVERSARIAL_REVIEW reruns as a forced full review and the `review-skipped` marker (and the stub) is removed before the panel starts.
- D-5: Declining a skipped review never stops the run and never re-skips: the rerun is a full panel review regardless of the stored review decision, with the marker removed first.
- D-4: A recheck (plan outgrew class) clears skip, independently of the plan_sha check. On every entry to ADVERSARIAL_REVIEW (first run, rerun, resume, or re-entry after the human declines the stub at the gate) the skip decision is recomputed against the current plan sha. The plan_sha check is done only in `change_class_review_skipped`/`skip-review`, never in build(), and a missing plan_sha is a mismatch (full review). The stub is written only when no ADVERSARIAL_REVIEW.json exists or the existing one is a prior skip stub; a real (panel-produced) review is never overwritten by a stub. If the existing review is a stub and the decision is not skip (sha differs, plan_sha missing, or recheck cleared skip), or the human declines the skipped review, the stale stub, its rendered md and the `.uncle/workflow/review-skipped` marker are removed and the full panel runs; if the result is still skip for a changed sha, a new stub is written.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/change_class.py` | add review decision, skip-review CLI, recheck clears skip | core decision | Medium: build() consumed everywhere | review-skip-test.py |
| `scripts/lib/change-class-stage.sh` | add `change_class_review_skipped`, env switch | shared driver helper | Low | review-skip-test.sh |
| `prompts/classify-change.md` | document optional review field | classifier needs to know | Low | none (text) |
| `scripts/change-workflow.sh` | short-circuit ADVERSARIAL_REVIEW to stub + ledger | driver 1 | Medium | review-skip-test.sh |
| `scripts/stagegate.sh` | short-circuit ADVERSARIAL_REVIEW to stub + marker | driver 2 | Medium | review-skip-test.sh |
| `scripts/tests/review-skip-test.py` | new; covers AC-1..5, 9 and the change-class.json half of AC-7 (review, review_reason fields) | tests | none | self |
| `scripts/tests/review-skip-test.sh` | new; covers AC-6, AC-8 and the marker and ledger half of AC-7 for both drivers (ledger assertion dropped if the ledger row is cut) | tests | none | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1,AC-2 (owned files classified by the existing change_class.py floor path rules; zero owned files, or any non-doc/non-test file in a docs/test-only class, is never skipped; small has no path rule beyond the floor and a sensitive driver/gate path vetoes it; floor/risk rejection in build(); stale or missing plan sha rejected by skip-review and change_class_review_skipped, not build()); re-entry after an edited plan discards the stub and recomputes the decision | SB-1, SB-2, SB-7, SB-9 | SI-1, SI-5 | change_class.py | review-skip-test.py (stale or missing plan_sha asserted against skip-review/helper, not build()), review-skip-test.sh (plan sha changes after stub: stub discarded, decision rerun) | docs vs deletion plan, empty/mixed owned-file plan runs full review, small plan owning a driver/gate path runs full review, edited plan after classify (stale sha) runs full review; edit plan after stub written, rerun, confirm stub discarded and decision recomputed |
| AC-3,AC-4 (incl. malformed/duplicate/non-string classifier review value => full) | SB-3, SB-4 | SI-4 | change_class.py, stage.sh | review-skip-test.py/.sh | WORKFLOW_SKIP_REVIEW=0 run, and an empty/false value run, both get a full review, classifier review values Skip/null/non-string yield full review |
| AC-5,AC-8,AC-9 | SB-1, SB-8 | SI-2 | change_class.py | review-skip-test.py, review-skip-test.sh (AC-8: failing/corrupted stub stops immediately, no retry, no full-review fallback, no model invocation, nonzero exit, both drivers), review-skip-test.sh (AC-5/AC-9: stub run through updated-plan input, final-audit input assembly and approval hashing; asserts overall_assessment is non-empty) | gate view, stub accepted by updated-plan stage (zero findings, or one informational finding if zero is rejected) |
| AC-6,AC-7 (AC-7 is satisfied by change-class.json fields plus the review-skipped marker; the ledger row is optional and is the first cut. AC-7 split: change-class.json fields tested in review-skip-test.py; marker (and ledger row if kept) tested in review-skip-test.sh) | SB-1, SB-5, SB-6 | SI-2, SI-3 | both drivers | review-skip-test.sh (AC-7 marker, optional ledger row), review-skip-test.py (AC-7 json fields) | decline at gate reruns as full review and removes the review-skipped marker, re-entry after plan change recomputes skip |
| AC-10: existing suites keep passing unchanged. Default classifier stubs and fixtures in existing suites never emit `review: skip`, so they always take the full-review path. Any existing suite that breaks anyway is changed only with renewed approval. | SB-3 | SI-3 | prompt, suites | both runners (bash scripts/run-python-tests.sh, scripts/run-shell-tests.sh) | none |

## Implementation sequence

1. Decision core: add `review`/`review_reason` to build() with owned-file classification reusing the existing floor path rules (a plan with no owned files is never skipped), `skip-review` stub writer, `get` support, recheck clearing; update prompt.
   Owns: `scripts/lib/change_class.py`, `prompts/classify-change.md`
2. Shell helper: `change_class_review_skipped` and env switch. Builds on step 1's CLI.
   Owns: `scripts/lib/change-class-stage.sh`
   Depends on: 1
3. change-workflow wiring: ADVERSARIAL_REVIEW short-circuit, ledger row.
   Owns: `scripts/change-workflow.sh`
   Depends on: 2
4. stagegate wiring: ADVERSARIAL_REVIEW short-circuit, marker. Independent file from step 3.
   Owns: `scripts/stagegate.sh`
   Depends on: 2
5. Python tests in review-skip-test.py (sole owner): AC-1..5, the change-class.json half of AC-7, AC-9 updated-plan validator check, plus the sha, path-rule, classifier-value, hostile-plan and hand-edited-json cases listed under the automated-test strategy. Can be written alongside step 1 from the spec.
   Owns: `scripts/tests/review-skip-test.py`
   Depends on: 1
6. Shell tests in review-skip-test.sh (sole owner): AC-6, AC-8 for both drivers, the marker and ledger half of AC-7, WORKFLOW_SKIP_REVIEW value matrix, resume/stale-stub/decline cases, and the stub run through final-audit input assembly and approval hashing asserting non-empty overall_assessment.
   Owns: `scripts/tests/review-skip-test.sh`
   Depends on: 3, 4
7. Grep existing classifier stubs and fixtures for `review`/skip to confirm none emit skip; run both baseline commands and confirm by hash comparison of protected test paths that no existing test file changed. This plan owns no existing test file: any conflict stops the run and needs renewed approval before editing. Record deviations.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 5, 6

## 21. Scope cuts under time pressure

Cut first: ledger row in change-workflow (not required to satisfy AC-7; the required records are the change-class.json fields and the `review-skipped` marker), then the shell test for stagegate (keep Python tests), then the prompt wording refinement. Never cut the floor, fail-closed behavior, or visible stub.

## 22. Risks

- Misjudged small app skips review; mitigated by floor + human plan gate.
- Downstream consumers of a stub with zero findings (updated-plan, final-audit input, approval hashing): verified by AC-9 tests that run each on the stub. The stub's overall_assessment is always non-empty. If the updated-plan path rejects zero findings, the stub carries one informational finding (non-empty overall_assessment retained) and the updated-plan stage itself is not modified. If any other consumer fails, fix in scope by making the stub acceptable to it, otherwise stop and ask.
- Existing tests that assert the review always runs may conflict; implementer checks them first and reports any needing a change as requiring renewed authority.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Stub text and console line were ambiguous; one exact validated/rendered string removes the conflict. | Section 19 and R-4 now fix stub overall_assessment as `skipped: class <class>, no risk hits` and console line as that text prefixed with `Adversarial review `. |
| AR-002 | Accepted | build() has no plan to compare, so the sha check belongs with the plan-aware entry points; skip-review must re-verify it itself. | Sections 1 and 8 and R-1 and the AC-1/AC-2 traceability row now put the sha check in skip-review and the shell helper only; build() does not evaluate it. |
| AR-003 | Accepted | The doc/test path rule left empty, mixed and small-class owned-file sets undefined; fail-closed is the safe rule. | R-1 mechanism and traceability row s17.1.r1 now state: empty owned set, or any non-doc/non-test file in docs/test-only class, means full; small has no path rule beyond the floor. |
| AR-004 | Accepted | The plan never said what happens when the plan sha changes after the stub exists; discarding the stub and recomputing is the fail-closed choice. | Rewrote D-4 in Decisions and extended traceability row s17.1.r1 with the re-entry behavior. |
| AR-005 | Accepted | Decline outcome on a skipped review was undefined; rerunning as a forced full review with the marker removed is the safe, human-respecting choice. | Edit D-3 to state decline reruns ADVERSARIAL_REVIEW as full review and removes the marker; add D-5; update traceability row s17.1.r4. |
| AR-006 | Accepted | AC-7 and the first scope cut conflict; the json fields and marker are the essential records, the ledger row is optional. | Edit s19.1 so the ledger row stays the first cut and is not needed for AC-7, and edit s17.1.r4 so AC-7 is satisfied by json plus marker. |
| AR-007 | Accepted | The plan defined no behavior for declining a skipped review or re-entering ADVERSARIAL_REVIEW; recomputing on every entry and clearing the marker on full review closes that gap. | Edit D-3 and D-4 in Decisions to state per-entry recomputation, decline-as-full-review and marker deletion; update traceability row s17.1.r4. |
| AR-008 | Accepted | The plan already places the sha check in the shell helper, but AC-2/SB-9 attribute it to build(); stating one home removes the conflict. | Edit s1.1, s6.1.i2, s6.1.i3, R-1 and s17.1.r1: sha is checked only in change_class_review_skipped and skip-review; build() does not evaluate it. |
| AR-009 | Accepted | Other consumers of ADVERSARIAL_REVIEW.json (final audit input, approval hashing) may assume non-empty findings; only updated-plan was covered. | Section 5 no longer claims final audit/approval are untouched-and-safe; traceability AC-5/AC-9 row and risk item now require tests of final-audit input and approval hashing on the stub, with a non-empty overall_assessment. |
| AR-010 | Accepted | Existing suites could use docs/small classifier stubs that would now emit skip, so the plan must pin default stubs to never emit review: skip. | Edited AC-10 traceability row: default test classifier stubs never emit review:skip; broken existing suites change only with renewed approval. |
| AR-011 | Accepted | Optional classifier review field validation was unspecified; honoring only exact lowercase skip is fail-closed and consistent with R-2. | Edit s8.1 and R-2 mechanism and traceability row s17.1.r2 to state only exact string skip is honored; other values mean full without invalidating the answer. |
| AR-012 | Accepted | The plan's s8 contradicts itself on stub failure; one rule (immediate stop, no retry, no fallback to full review) matches AC-8. | Add a failing-stub test to the s10 test strategy, and a stop-without-retry assertion to the s17.1.r3 test and behavior rows. |
| AR-013 | Accepted | The floor sees only plan text, so owned-file paths must also gate skip; failing closed on empty or sensitive paths closes the gap. | Edit R-1, D-1 (s15.1.i1) and traceability s17.1.r1 to require declared owned files, doc/test-only globs, and sensitive-path veto for small. |
| AR-014 | Accepted | The model's review value is the sole positive skip signal, so it must be strictly validated and plan text treated as untrusted. | Edited s8 interface (classifier answer item), D-2, R-2 and traceability row s17.1.r2 to require exact lowercase "skip" only, else full, with plan text untrusted. |
| AR-015 | Accepted | Trusting stored review=skip plus a matching sha lets a hand-edited change-class.json or a race bypass the floor; recomputing in the writing invocation closes that. | s6.1.i1 and s8.1 now require skip-review to recompute the floor against the current plan and never trust stored review=skip alone. |
| AR-016 | Accepted | Treating only `0` as disabling skip fails open for empty, false or no values, contradicting the fail-closed invariant. | Section 12 (s8.1) and traceability row s17.1.r2 now state skip is enabled only when WORKFLOW_SKIP_REVIEW is unset or exactly 1; any other value means full review. |
| AR-017 | Accepted | Rerun/resume handling of an existing ADVERSARIAL_REVIEW.json and the review-skipped marker was unspecified; stale files could mislead. | Edit D-4 to define stub-write and stale-removal rules, and add them to restriction R-4. |
| AR-018 | Accepted | The open-ended risk wording conflicts with the zero-findings expectation; a deterministic fallback removes the ambiguity without touching the plan stage. | Risk s20.1.i2 and trace row s17.1.r3 now say the stub carries one informational finding if zero findings are rejected; the plan stage is unmodified. |
| AR-019 | Accepted | The plan never defined how owned files are classified or how an empty owned-file set is treated; reusing existing floor path rules and failing closed on empty is safe. | Edit s1.1, R-1, s17.1.r1 and step-1 to state that classification reuses change_class.py floor path rules and a plan with no owned files is never skipped. |
| AR-020 | Accepted | The marker and ledger row are written by the shell drivers, so AC-7 cannot be proven wholly by the Python suite, and the ledger row is a scope cut. | Split AC-7 coverage in the Automated-test strategy (s10 is another writer's; here s16.1 rows r1, r6, r7 and s17.1.r4) so json is tested in .py and marker/ledger in .sh; ledger optional. |
| AR-021 | Accepted | Corrupted-stub handling was stated two ways; a stub failure is a bug, not model output, so retry is meaningless. | Edit s12.1 to state stub validation failure stops immediately, no retry, nonzero exit, no model call; align s10.1 and s17.1.r3 tests. |
| AR-022 | Accepted | The sha check has one home to avoid a split between build(), the helper and recheck; missing sha must fail closed. | Edit s8.1, s15.1.i4, R-1 and s17.1.r1 to place the sha check only in change_class_review_skipped and skip-review, treat a missing plan_sha as a mismatch, and keep recheck clearing skip independently. |
| AR-023 | Accepted | Unspecified handling of other classifier review values is a real gap; failing closed is consistent with the plan's fail-closed rule. | Edit s8 interface list item for the classifier answer to state that only exact lowercase string skip is honored and anything else is full without error. |
