# FINAL_AUDIT.md — Early build branch creation (Issue 60)

Inputs: `CHANGE_SPEC.md` (Issue 51 content), `CHANGE_PLAN.md` (Issue 60), `.uncle/workflow/change.diff` (4 files: FE-1..FE-4), `IMPLEMENTATION_NOTES.md`, `CHANGE_TEST_REPORT.md`, `MANUAL_CHECKLIST.md`, `VERIFICATION_REPORT.md`, `DEFECTS.md`, `implementation-completion.txt`, waivers `AC-6`, `AC-7`, `delivery-summary.tsv`, check-run logs under `.uncle/workflow/check-runs/{293d27a1…,5aaf2384…}`. `plan-executability/assessment.md`, `plan-recovery.json`, `TEST_REVIEW.md` absent.

Re-executed at audit (working tree, 2026-09-16): `python3 scripts/tests/early-branch-test.py` → `Ran 12 tests OK`; `python3 scripts/tests/pr-originless-test.py` → `Ran 26 tests OK`; `python3 scripts/tests/project-git-test.py` → `Ran 5 tests OK`. `git status --porcelain` → FE-1..FE-4 plus ` M scripts/lib/gates.sh`, `?? scripts/lib/document-layout.sh`, ` D FINAL_AUDIT.md`. Driver `results.tsv`: green-check commands 0/0/0/1/0, shell runner PREEXISTING (7 suites; `7aa3c66e….log` shows `triage-guard` and `close-flow` fail with identical counts on a HEAD export).

Waived rows: AC-6 and AC-7 (`.uncle/workflow/waivers/AC-6`, `AC-7`, reason `Waived by an unattended run; no person assessed this check.`). Both are Issue 51 spec rows; the waiver permits workflow advancement only. Nothing implements them.

## Findings

| ID | Severity | Evidence | Affected behavior | Affected invariant | Required correction | Blocks completion |
|---|---|---|---|---|---|---|
| FA-1 | High | `CHANGE_SPEC.md:1` is `Configurable markdown viewer (Issue 51)` with AC-1..AC-7 about `_viewer_command`; `CHANGE_PLAN.md:1` is Issue 60 with different AC-1..AC-5. `delivery-summary.tsv` rows AC-1..AC-5 read INCOMPLETE because the driver matches spec IDs, not plan IDs. The hash-approved spec (`approvals/CHANGE_SPEC.sha256`) does not describe the delivered change. | Spec-to-delivery traceability; the approved analysis artifact describes a different feature | Approval-chain integrity (spec supersedes request per stage rules) | Regenerate `CHANGE_SPEC.md` (and `BASELINE_REPORT.md`) for Issue 60 and re-open the analysis gate, or record an operator decision that `CHANGE_PLAN.md` is the accepted spec for this run | YES |
| FA-2 | High | `git status --porcelain` at audit: ` M scripts/lib/gates.sh` (+4 lines: `. "$GATES_LIB_DIR/document-layout.sh"`, `document_layout_prompt "$log_name"`), `?? scripts/lib/document-layout.sh` (96 lines). Neither is in `change.diff`, plan FE-1..FE-4, or FN-1..FN-3. MC-008 FAIL (`9217050….log`, exit 1; DEF-1). | Runtime behaviour of every gate that sources `gates.sh`; not covered by the approved diff review | FS-1 frozen scope; VC-3 "only FE-1..FE-4 differ" | Remove both paths from this change's tree, or amend scope and re-open the implementation diff gate with them included | YES |
| FA-3 | Medium | AC-6/AC-7 waivers: `reason: Waived by an unattended run; no person assessed this check.` The stage rule is that a waiver is a typed operator reason; here none exists. `implementation-completion.txt` still records both as BLOCKED. | Delivery of the two Issue 51 rows (none intended) | Waiver provenance (operator-recorded) | Operator confirms the waiver (they are Issue 51 rows outside this change) or resolves via FA-1; do not treat as delivered | YES |
| FA-4 | Medium | `change-pr.sh:503` `early_ref_oid` runs `for-each-ref refs/heads/<name>`, which also matches `refs/heads/<name>/*`. MC-024 FAIL (`5506c749….log`): sibling ref at another OID yields `StartError(COLLISION)`, no journal. DEF-3. Pre-existing pattern from `handoff` (`change.diff:167`), now reached at build start. | AC-4: collision reported for a ref that does not exist; build stops before the first stage | D-4 "accept existing candidate ref only at starting OID" decides on the wrong ref | Use `git rev-parse --verify -q refs/heads/<name>` (or `show-ref --verify`) in `early_ref_oid`; add a T-4 sibling case | NO |
| FA-5 | Low | `IMPLEMENTATION_NOTES.md` DV-3 says `start` skips below the worktree root; `change-pr.sh:912` raises `PR binding requires the Git worktree root.` before `start_build` (`:550`) runs. MC-022 FAIL (`920f5a9f….log`, exit 1). Driver does `cd "$PROJECT_ROOT"` (`change-workflow.sh:21`), so the build path is unaffected. DEF-2. | Direct `change_pr_engine start` from a subdirectory (CLI only) | None on the driver path | Either dispatch `start` before the `:912` guard or delete the dead `:550` guard and amend DV-3 | NO |
| FA-6 | Low | `VERIFICATION_REPORT.md:34` records MC-018 PASS while the executed wrapper (`5aaf2384…/52e1a995….log`) ends `RESULT MC-018 FAIL 1`; the failing assertion is the wrapper's "nothing beyond journal" against driver preamble bookkeeping (`approvals/`, `performance/`, `TRIAGE.md`). The three substantive `ok:` lines (abort message, no stage, no git mutation) are present. | Checklist MC-018 expected-result wording; no product behaviour | None | Reviewer amends MC-018's expected result to exclude driver bookkeeping, or the wrapper is corrected and rerun; the PASS is a judgment over a red wrapper and should be labelled as such | NO |
| FA-7 | Low | `MANUAL_CHECKLIST.md` MC-014 expects both "head_branch is `feature`" and "final branch is `uncle/<slug>-<owner>` based on `feature`"; plan D-3/T-3 and `change-pr.sh:577` retain `feature`. Observed behaviour (`90546555….log`) matches the plan. DEFECTS OQ-1. | None; checklist text contradicts the approved plan | None | Reviewer corrects the MC-014 wording | NO |
| FA-8 | Low | `BASELINE_REPORT.md:7` is Issue 51 and §9 lists 6 failing suites; HEAD `8f4a2347` fails 7 (`triage-guard` added). Green-check reads PREEXISTING from its own pre-change run, so no regression is claimed; the baseline document itself is stale. | Baseline provenance for the shell suite | None | Rerun the baseline stage at HEAD when FA-1 is resolved | NO |
| FA-9 | Info | MC-013 / LV-1 BLOCKED-HUMAN: a real remote with `refs/remotes/<remote>/HEAD` and authenticated `gh` are unavailable (`DEFECTS.md` ENV-1; plan R-6 declares this LIVE_VERIFICATION). Local fixtures T-1, T-3, T-8 cover the same assertions with a bare remote and fake `gh`. | AC-1/AC-3 on a live GitHub remote | None | Operator runs one eligible build through its first stage on a disposable remote and records `git rev-parse refs/heads/<head_branch>` | NO |

Unsupported PASS claims (category 1): every PASS row in `VERIFICATION_REPORT.md` maps to a `check-runs` log with exit 0 and `ok:` lines except MC-018 (FA-6). `CHANGE_TEST_REPORT.md` counts were reproduced at audit for the three Python suites; shell-runner and defect-injection claims match `results.tsv` and the report's own restored-`cmp` statements and were not re-executed.

Delivered against the approved `CHANGE_PLAN.md`: AC-1..AC-5 implemented and re-verified here; D-1..D-8 present in `change.diff`; DV-1..DV-5 recorded; no test was weakened or deleted (`pr-originless-test.py` change is append-only, `change.diff:586-663`); FN-1..FN-3 hashes match (MC-008 first assertion). Signing rules hold in both fixtures (MC-016; `early-branch-test.py:303-310`, `pr-originless-test.py:231-237`). Rollback: revert FE-1/FE-2/FE-4, delete FE-3; a `started` v2 journal left by a rolled-back tree is rejected by the old `load()` as corrupt, which is the pre-change failure mode.

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| AC-1 | YES | PASS | `early-branch-test.py` T-1/T-3 OK at audit; MC-001, MC-014 logs |
| AC-2 | YES | PASS | T-2/T-6/T-7 OK at audit; MC-002, MC-011, MC-016, MC-017 |
| AC-3 | YES | PASS | `pr-originless-test.py` 26 OK at audit; MC-005, MC-010, MC-021, MC-023 |
| AC-4 | YES | FAIL | Exact-ref cases pass (MC-003, MC-012, MC-018); sibling-ref false collision MC-024 (FA-4) |
| AC-5 | YES | PASS | T-5 and `project-git-test.py` OK at audit; MC-004. Subdirectory CLI path (FA-5) is not a build path |
| AC-6 | NO | NOT RUN | Issue 51 row; waived unattended (FA-3); not implemented |
| AC-7 | NO | NOT RUN | Issue 51 row; waived unattended (FA-3); not implemented |
| G-1 | YES | FAIL | Working tree contains `scripts/lib/gates.sh` and `scripts/lib/document-layout.sh` outside the approved diff (FA-2) |
| G-2 | YES | FAIL | `CHANGE_SPEC.md` describes Issue 51, not the delivered Issue 60 change (FA-1) |
| G-3 | YES | PASS | Driver green check: no regression; 7 pre-existing shell-suite failures identical on a HEAD export (`7aa3c66e….log`) |
| G-4 | NO | BLOCKED-HUMAN | LV-1 live remote run; Brian with authenticated `gh` and a disposable remote (FA-9) |

NOT READY
