# Change plan — Issue 272

Omitted sections: Schema/persistence (none); Concurrency (none); Migration (none); Feature flag (none, pure function fix); Observability beyond one log line

Issue 272

Seeded from [unclehq/uncle#272](https://github.com/unclehq/uncle/issues/272).

## 1. Selected technical approach
In `scripts/lib/change_class.py`, rewrite `interpretation_counts` to: (a) count distinct `R-n` / `D-n` ids as now; (b) if the id count is 0, count structure: bullet/numbered list lines in `required_functionality`, and pipe-table data rows in `definition_of_done` (excluding the header row, which precedes a `|---|` separator row, and the separator itself). Add a diagnostic: when `interpretation()` is non-empty and either count is 0, print one line to stderr (`change-class: interpretation counts unknown (requirements=N, criteria=M); not classing small`). Zero already prevents small via the existing `0 <` guards.

Decision D-1: ids win over structure when present (backward compatible). D-2: nested/indented bullets count only at top level (no leading indent beyond 1 space) to avoid inflating counts. D-3: items-per-bullet continuation lines are ignored.

## 2. Alternatives
- Make the investigation emit ids (stagegate/prompt change): wider surface, depends on model compliance. Rejected.
- Exclude test/scaffold files from `large` thresholds (request item 3): changes class for every app and change; no evidence from this issue needed it once small applies. Deferred.

## 3. Why preferred
Smallest surface, deterministic, fixes root cause (counts), restores PLAN_TARGET/PLAN_WORD_SCALE budgeting for small apps.

## 4. Components to modify
`scripts/lib/change_class.py`; `scripts/tests/review-skip-test.py`.

## 5. Not to modify
`scripts/stagegate.sh`, `prompts/requirements-investigate.md`, `requirements-context.py`, APP_SMALL / large thresholds, `file_kinds` counting.

## 6. Data flow
Unchanged except `features.requirements`/`criteria` now non-zero for id-less interpretations.

## 8. Interfaces
`interpretation_counts(project)` signature and return shape unchanged; stderr gains one line.

## 10. Compatibility

Counts are identical for any section that contains R-n/D-n ids. ID precedence applies per section, so in a mixed interpretation (ids in only one section) the id-less section now uses the structural fallback and its count may change from 0; this is intended. Existing change-class.json readers unaffected.

## 12. Error and recovery
Unparseable or absent interpretation -> `{}` -> (0,0), and no log (nothing exists to be unknown about).

## 14. Rollback plan
Revert the two files. No state migration; previously written change-class.json files are inert.

## 16. Automated-test strategy

Add to `scripts/tests/review-skip-test.py` (hyphenated, explicit command because not in critical tier): tests for AC-1..AC-4, building temp project dirs with a REQUIREMENTS_INTERPRETATION.json and a small plan file via existing helpers (`plan_text`).
Id precedence is applied independently per section: a section containing ids keeps its id count; an id-less section uses the structural fallback. Mixed-case tests: (a) R-ids in required_functionality with an id-less definition_of_done table -> requirements = id count, criteria = table data rows; (b) id-less required_functionality bullets with D-ids in definition_of_done -> requirements = top-level bullet count, criteria = id count.
Regression test: AC-1 test fails before fix (counts 0, class standard/large) and passes after.

## 17. Regression strategy
Run full shell and python commands from the baseline plus explicit review-skip; id-bearing test retained.

## 18. Manual verification
None required; optionally call `python3 scripts/lib/change_class.py` helpers on a sample id-less JSON.

## Verification commands
```
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- review-skip
```
Protected verification paths: `scripts/tests/review-skip-test.py` is edited by step 2 only (authorized, added tests only); no other tests change.

## Restrictions
| R-ID | source_kind | Source | Req | Required property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Requested fix 1 | OB-1 | counts independent of ids | structural fallback | minimal | CAP-1 | CODING |
| R-2 | REPOSITORY | change_class.py:263-269 | INV-2 | keep small limits | untouched APP_SMALL | compat | CAP-1 | CODING |
Feasibility: inspected change_class.py:226-230 and :263-269; pure Python, no external capability needed. No live-auth prerequisites.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| scripts/lib/change_class.py | structural counting fallback + unknown-count log | Root cause of issue 272 | Low-medium: over/under-counting | review-skip-test.py new tests |
| scripts/tests/review-skip-test.py | add AC-1..AC-4 tests | Regression coverage | Low | itself |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | OB-1 | INV-2 | change_class.py | new small-app test, mixed-section tests (R-ids with id-less criteria, id-less requirements with D-ids) | none |
| AC-2 | OB-1, OB-2 | INV-3 | change_class.py | counts tests | none |
| AC-3 | OB-6 | INV-2 | change_class.py | over-limit test | none |
| When an interpretation has non-empty sections and either count is 0, exactly one stderr line is emitted per features() evaluation (counts computed once via a single interpretation_counts call and reused); an empty sections object is treated as absent and emits nothing. | OB-3, OB-4 | INV-1 | change_class.py | stderr test through features() (mandatory, not cuttable, a helper-only call is not sufficient): exactly one diagnostic line per evaluation for non-empty sections when either count is zero, no diagnostic when both counts are non-zero, or when the interpretation is absent, invalid, or has an empty sections object, mixed-case tests: id requirements with id-less criteria, and id-less requirements with id criteria | none |
| AC-5 | OB-5 | INV-1, INV-4 | all | full suites | none |

## Implementation sequence

1. Counting fallback and diagnostic in `scripts/lib/change_class.py`. `interpretation_counts` stays pure (no logging) and returns (requirements, criteria). ID precedence applies independently per section: a section containing R-n/D-n ids keeps its id count unchanged; a section with no ids uses the structural fallback. In `features()` for non-change families, call `interpretation_counts` once per evaluation, reuse both counts for `requirements` and `criteria`, and emit the unknown-count diagnostic (one stderr line) from `features()` at most once per evaluation, only when the interpretation sections object is non-empty and either count is 0. An empty sections object is treated as absent (same as missing or invalid input) and emits no diagnostic. The diagnostic is not emitted from inside the helper, so it cannot print twice. The diagnostic and its stderr test (asserting exactly one line, tested through `features()`) are mandatory and cannot be cut.
   Owns: `scripts/lib/change_class.py`
2. Tests for AC-1..AC-4 (id-less small, id-bearing preserved, over-limit, zero-count log) plus the two mixed-section cases (ids only in requirements; ids only in criteria) asserting per-section precedence
   Owns: `scripts/tests/review-skip-test.py`
   Depends on: 1

## Scope cuts under time pressure

The AC-4 diagnostic and its stderr assertion are mandatory and cannot be cut under time pressure. Cut first: the extra mixed-shape and nested-bullet edge-case tests beyond the issue's 4/4 shape and beyond AC-1..AC-4 (including the mixed-section cases). No required item is cut. Never cut: structural counting, per-section id precedence, the AC-1 test, or the AC-4 diagnostic and its test.

## Risks and unresolved questions
- Investigation bullet/table shape may vary (e.g. bold sub-labels); mitigated by top-level-only counting and tests with the issue's 4/4 shape. None blocking.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | features() calls interpretation_counts twice, so a diagnostic inside it would print twice; one-line cardinality must be specified. | step-1 and AC-4 now require features() to call interpretation_counts once, reuse both counts, and emit at most one diagnostic, tested through features(). |
| AR-002 | Accepted | interpretation() returns {} for empty sections and for missing/invalid input alike, so the two cannot be told apart; the plan must state the rule explicitly. | step-1 and AC-4 now treat an empty sections object as absent (no diagnostic); non-empty sections with either count zero emit it. |
| AR-003 | Accepted | The plan both requires the AC-4 diagnostic and lists it as the first cut, which is contradictory. | Scope cuts section now says the AC-4 diagnostic and its stderr test are mandatory and cannot be cut; the cut-first item becomes a different item. |
| AR-004 | Accepted | features() calls interpretation_counts twice, so logging inside the helper would print two lines. | Step 1 and AC-4 now require one interpretation_counts call per features() evaluation, counts reused, and a single diagnostic tested through features(). |
| AR-005 | Accepted | Per-section fallback can change the tuple for mixed interpretations, so precedence scope and the compatibility promise must be explicit and tested. | Step 1 and s8.1 state per-section ID precedence and narrow compatibility to sections with IDs; AC-4 tests add both mixed cases. |
| AR-006 | Accepted | features() calls the counts helper twice, so a diagnostic inside the helper would print twice; emission scope must be fixed. | Step 1 makes features() compute counts once and emit at most one diagnostic; AC-4 test asserts exactly one stderr line through features(). |
| AR-007 | Accepted | The plan both required the AC-4 diagnostic and listed it as cuttable, which is contradictory. | Rewrote s19.1 so the AC-4 diagnostic and its stderr assertion are mandatory; cut order now names only non-required items. |
| AR-008 | Accepted | Section scope of id precedence was unspecified, so mixed interpretations had no oracle. | Added a per-section precedence rule and mixed-case tests to s11.1, step-2, AC-1 coverage. |
