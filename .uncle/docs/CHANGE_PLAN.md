# Change Plan: Issue 243 `uncle --revalidate`

Seeded from [unclehq/uncle#243](https://github.com/unclehq/uncle/issues/243)

Omitted sections: Schema/persistence beyond state dir (covered in 9); Concurrency (single driver lock already exists); Migration (none); Feature flag (flag is opt-in); Observability (plan output is the observability)

Issue 243

## 1-3. Approach
Selected: build on the existing uncommitted draft (`scripts/lib/revalidate.py`, `uncle` flag, driver record hooks). Pure-Python fingerprint/plan functions with an injectable runner; driver resumed at the first invalidated stage via `UNCLE_REVALIDATE_RESUME`. Alternatives: extend `green-check.fingerprint` (rejected: single global hash, cannot be per-stage); hash everything including README (rejected: violates acceptance case). Preferred because plan logic stays testable without models.

## 4. Components

Modify: `scripts/lib/revalidate.py`, `uncle`, `scripts/change-workflow.sh` (record hook for every stage, resume entry honoring the per-stage action plan, pre-write approval/attestation guard, gate stop), `scripts/stagegate.sh` (record hooks), tests, `README.md`, `scripts/tests/critical-suites.txt`. Not modify: `uncle-verify.py`, approval/attestation writer code, `tree_fingerprint.py`, `project_paths.py`, existing tests.

## 9. Persistence

`.uncle/workflow/stage-fingerprints/<STAGE>.json`: stage, hash, inputs{kind:hash}, status(pass|invalidated), time, readme hash. Decision D-1: only the project-root README.md is excluded from stage inputs, so README edits invalidate nothing (AC-3); every other declared input (application and test files, protected verification paths, approved documents, and any other Markdown file a stage consumes) is hashed by content regardless of extension. Decision D-2: every passing stage in scope records its fingerprint (record hooks for all stages are required scope, not cuttable). A stage with no fingerprint record is classified using existing workflow history (stage completion/approval records, stage output documents): if history shows it never ran, it is reported skip (not run); if history shows it previously ran but it has no fingerprint (legacy), it is classified changed and reruns, subject to the no-recorded-passes exit rule (when no recorded pass exists at all, exit 2 and execute nothing, AC-7). A previously-recorded stage without inputs is also changed. Decision D-3: Uncle version = hash of driver scripts (`prompt` kind) so any driver change reruns prompt-reading stages.

Decision D-4 (required scope): record input fingerprints on every stage's successful completion. Record hooks beyond PLAN, ADVERSARIAL_REVIEW and IMPLEMENT are required scope, not optional, and are not on the cut list; a completed stage with no hook would otherwise fall outside revalidation.

## 12. Error and recovery
Runner failure: stage left `invalidated`, run stops, exit 1; next run reruns it. No state: exit 2. Reopened gate: exit 75, reported as blocked.

## 14. Rollback
Revert listed files; delete `.uncle/workflow/stage-fingerprints`.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Invariants | RI-1 | reuse only on byte-identical inputs | sha256 per input kind in `input_hash`; every declared input is hashed regardless of extension, only the project-root README.md is exempt; exceptions mean changed | CAP-PY | revalidate.py l.97 | CODING |
| R-2 | USER | CHANGE_REQUEST | RI-2 | protected change flagged | `needs-review` action in `plan` | CAP-PY | plan l.205 | CODING |
| R-3 | USER | CHANGE_REQUEST | RI-3 | pass-only reuse | status check in `plan` | CAP-PY | plan l.190 | CODING |
| R-4 | USER | CHANGE_REQUEST | RI-4 | downstream rerun | `bad` propagation via PRODUCES | CAP-PY | plan l.183 | CODING |
| R-5 | USER | CHANGE_REQUEST | RI-5 | no approval/attestation writes | Primary (pre-write): before invoking any resumed stage the revalidation entry sets a revalidate-mode guard so approval and attestation writers refuse to write and exit 75 (no writer code is modified; the driver gates on the mode before calling them); gate stop exit 75 at any reopened gate. Secondary (post-hoc): snapshot compare of approval/attestation files before and after, failing the run on any difference. | CAP-PY, CAP-SH | default_runner l.227 | CODING |

## 16-17. Test strategy
Unit and integration suites with stub runner counting calls; README acceptance test; protected-file injection; dry-run no-write check; two-pass resume test. Regression: full shell and python runners. Fixtures disable git signing.

## 18. Manual verification
On a built sample project run `uncle --revalidate --dry-run`, edit README.md, rerun; confirm line and all reused; edit a source file, confirm dependents listed.

## 21. Scope cuts first

`--attended` nuances; attestation line polish. Record hooks for every stage are required scope and are not cuttable.

## 22. Risks
False reuse (mitigated by RI-1 tests); driver resume ordering; draft is unreviewed so step 1 audits it against spec.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/revalidate.py` | audit and complete vs AC-1..10 (readme field, unrecorded-stage handling, resume) | core logic | Low | revalidate-test |
| `uncle` | flag parsing/help/exclusivity | entry point | Medium | revalidate-integration, existing startup suites |
| `scripts/change-workflow.sh` | record hook for every stage, per-stage action-plan resume filter (run only stages marked run), pre-write approval/attestation guard, gate stop | record passes | Medium | integration, shell runner |
| `scripts/stagegate.sh` | IMPLEMENT record hook | record passes | Low | shell runner |
| `scripts/tests/revalidate-test.py`, `revalidate-integration-test.py` | cover every AC | verification | Low | self |
| `scripts/tests/critical-suites.txt` | register suites | run in default tier | Low | runner |
| `README.md` | document flag | docs | None | n/a |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: every passing stage records its input fingerprints on successful completion (all stages, no hook cut). | RB-1 | RI-1 | revalidate.py | revalidate-test, integration: every driver stage writes a fingerprint record on pass, revalidate-test: non-README Markdown input change (fixture/protected/document) is detected as changed; root README.md change is not | M-1 |
| AC-2 | RB-2, 3, 4 | RI-5 | revalidate.py, uncle | revalidate-test, integration | M-1 |
| AC-3 | RB-5 | RI-1 | revalidate.py | integration README test (root README.md edit reuses all), revalidate-test: non-root Markdown and protected Markdown input change is detected as changed | M-2 |
| AC-4: exactly the changed stages and their dependents rerun; all others are reused. Execution contract: the complete per-stage action plan is passed to the resumed driver (alongside UNCLE_REVALIDATE_RESUME); the driver executes only stages marked `run`, skips `reuse` and unrecorded (`skip`) stages without running any command, and stops before any `needs-review` stage or reopened gate. | RB-6 | RI-4 | revalidate.py | revalidate-test, revalidate-integration: resume the real driver with model and test commands stubbed; assert only stages marked run execute commands and stages marked reuse or skip execute none | M-3 |
| AC-5 | RB-7 | RI-2 | revalidate.py | defect-injection test | M-3 |
| AC-6: a stage that previously ran but has no recorded hash/pass (legacy) is counted as changed and rerun; only a stage with no execution history is skipped. | RB-9 | RI-3 | revalidate.py | revalidate-test, revalidate-test: legacy stage (history shows it ran, no fingerprint) with at least one recorded pass is changed; never-run stage (no history) is skip | none |
| AC-7: with no recorded passes at all, exit 2 and execute nothing; legacy stages are not rerun in that case. | RB-8 | RI-3 | revalidate.py, uncle | revalidate-test, revalidate-test: no recorded passes anywhere exits 2 and executes nothing, even if history shows stages previously ran | M-1 |
| AC-8 | RB-10 | RI-3 | revalidate.py | revalidate-test | none |
| AC-9: revalidation never writes approvals or attestations. The driver in revalidate mode refuses (stops before invoking) any approval or attestation writer, including from resumed stages that write without reopening a gate; the before/after snapshot compare is only a secondary check. | RB-11 | RI-5 | change-workflow.sh | integration: resumed stage attempting an approval/attestation write is blocked before the write occurs under revalidate mode, and snapshot compare confirms no change | none |
| AC-10: `--revalidate` combines only with `--noui`, `--attended` and `--dry-run`; other startup modes are rejected, and `--dry-run` without `--revalidate` is rejected. | RB-12 | all | uncle | full runners | M-1 |

AC-4 verification boundary: helper-only stub-runner call counts are insufficient. The integration suite must resume the real driver (UNCLE_REVALIDATE_RESUME) with model and test commands stubbed, and assert that only stages marked run in the computed plan execute, while reused and skip stages execute no commands.

## Implementation sequence

1. Audit draft vs spec; fix `revalidate.py` gaps (README-only exemption, workflow-history classification of never-run vs legacy stages, resume) and add missing unit tests. Deliverable: a documented action-plan hand-off contract (plan file path exported via env var alongside `UNCLE_REVALIDATE_RESUME`) that step 2 consumes.
   Owns: `scripts/lib/revalidate.py`, `scripts/tests/revalidate-test.py`
2. Driver and CLI wiring: flag handling (`--revalidate` is legal with `--noui`, `--attended` and `--dry-run`; reject any other startup mode combined with it, and reject `--dry-run` without `--revalidate`); record hooks; in `scripts/change-workflow.sh`, accept the computed per-stage action plan under `UNCLE_REVALIDATE_RESUME` and execute only stages marked run, skipping reused and unrecorded stages; in revalidate mode block approval/attestation writers before any resumed stage is invoked and stop at needs-review stages or reopened gates (exit 75). Add an integration test resuming the real driver with model/test commands stubbed, asserting only run-marked stages execute.
   Owns: `uncle`, `scripts/change-workflow.sh`, `scripts/stagegate.sh`, `scripts/tests/revalidate-integration-test.py`
   Depends on: 1
3. Docs and suite registration
   
   Verification commands are the baseline report list (shell runner, python runner, and explicit `bash scripts/run-python-tests.sh -- revalidate` and `-- revalidate-integration`).
   Owns: `README.md`, `scripts/tests/critical-suites.txt`
   Depends on: 1, 2

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Optional record hooks plus skipping unrecorded stages would silently drop completed stages from revalidation, contradicting AC-1/RB-1. | Persistence section states every passing stage records a fingerprint and all record hooks are required scope; AC-1 traceability row updated to match. |
| AR-002 | Accepted | D-2 conflated never-run stages with legacy stages that ran without fingerprints; RB-9 requires the latter to count as changed. | Rewrote D-2 in s3.1 and aligned AC-6/AC-7 traceability rows to the never-run vs previously-run distinction. |
| AR-003 | Accepted | Excluding all Markdown could reuse stages after real Markdown app/test/protected/document inputs change; only the root README.md is exempt per AC-3. | Rewrote D-1 in section 9 to exclude only root README.md and hash other Markdown inputs; added test coverage to AC-1. |
| AR-004 | Accepted | The plan named only a resume entry point and gave no contract keeping later reusable stages from executing, which AC-4 requires. | AC-4 requirement and tests now require the full per-stage plan to be passed to the driver, which runs only 'run' stages and stops at needs-review or reopened gates. |
| AR-005 | Accepted | Exclusivity wording could be read as rejecting the modifiers the spec supports; the legal flag set must be explicit. | Step 2 and AC-10 now allow --revalidate with --noui, --attended, --dry-run; reject other startup modes and --dry-run without --revalidate. |
| AR-006 | Accepted | Categorical Markdown exclusion could reuse stale results when a stage consumes non-README Markdown; AC-3 exempts only the README. | Section 9 D-1 rewritten: exclude only project-root README.md; hash all other consumed Markdown, including protected files. |
| AR-007 | Accepted | Resuming at the first invalidated stage gave no per-stage filter, so reusable stages could run and writers could fire; the driver needs an explicit execution contract. | Edit AC-4 and AC-9 requirements, step-2 text and owns (change-workflow.sh resume/filter/gate stop), and add a driver-level integration test. |
| AR-008 | Accepted | Optional hooks plus skipping unrecorded stages could leave completed stages permanently outside revalidation; distinguishing never-run from ran-without-fingerprint closes that gap. | Edit s3.1 (D-2) to separate never-run (skip) from ran-without-fingerprint (changed); AC-1 requires records for every passing stage. |
| AR-009 | Accepted | A post-hoc snapshot compare detects approval/attestation writes only after they happen; a pre-write guard is needed for resumed stages. | R-5 mechanism now requires a pre-invocation write block with snapshot compare as secondary check; AC-9 traceability updated to match. |
| AR-010 | Accepted | Excluding all Markdown contradicts RI-1 and AC-1; only the project-root README.md is exempt under AC-3. | Rewrote D-1 in s3.1 to exempt only root README.md and hash all other declared inputs by content; aligned AC-3 test and R-1 mechanism. |
| AR-011 | Accepted | D-2 did not define the evidence separating never-run stages from legacy stages that ran without a fingerprint, so fixtures could expect conflicting results. | Rewrote D-2 in s3.1 to use workflow history as evidence; updated AC-6 and AC-7 tests to cover both cases. |
| AR-012 | Accepted | Stub call counts on helpers cannot show that the resumed driver skips reused stages; a real-driver integration test is needed. | Traceability AC-4 now requires an integration test resuming the real driver with stubbed model/test commands, asserting only run stages execute; s12 note added. |
