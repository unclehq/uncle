# Change Spec (Issue 149)

Omitted sections: Performance (none); Security (no new surface); Migration (none); Prototype isolation (n/a)

## 1. Change type
Bug fix / Refactor of bookkeeping.

## 2. Problem
Uncle rewrites tracked `.gitignore` outside reviewed diffs, including after the final audit, leaving ` M .gitignore`, blocking worktree removal, or shipping an unreviewed change.

## 3. Current behavior
Baseline B-1..B-6.

## 4. Desired behavior
TUI/driver startup and config reloads never write tracked files. Ignore coverage for non-worktree roots comes from untracked `.git/info/exclude`. Worktree creation (pre-audit) may normalize the worktree `.gitignore` so the edit is in the audited diff. Publish verifies exact `.gitignore` bytes and a clean tracked tree.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| G-1 | MODIFY | Change finishes and PR published | tracked `.gitignore` may be modified | `git status --porcelain --untracked-files=no` empty; else run reports files, not COMPLETE | test AC-1, AC-6 |
| G-2 | MODIFY | PR created | managed edit after audit can enter PR | PR `.gitignore` bytes equal audited; mismatch stops publish with message | AC-2 |
| G-3 | PRESERVE | Post-PR removal | refuses dirty tracked | passes when clean; other dirty file still refused | AC-3 |
| G-4 | MODIFY | Project `.gitignore` lacks block | added at end/anytime | block provided via info/exclude (root) or via worktree edit before audit; never later | AC-4 |
| G-5 | MODIFY | Run with no PR completes | may leave edit | checkout clean | AC-1 |
| G-6 | MODIFY | TUI start/reload/project switch | edits tracked `.gitignore` | no tracked write; writes info/exclude; prints deferral message if legacy tracked rule needs worktree normalization | AC-5 |
| P-1 | PRESERVE | Ignore coverage | `.uncle/*` ignored, `.uncle/docs/` visible | unchanged semantics under exclude | AC-7 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | NEW | No tracked file modified between final audit and publish | run | publish pre/post check in change-pr.sh | AC-2, AC-6 |
| I-2 | STRENGTHENED | PR commit tree equals audited tree incl. `.gitignore` bytes | publish | validate | AC-2 |
| I-3 | NEW | Uncle bookkeeping writes no tracked file outside worktree creation | TUI/drivers | uncle_gitignore API | AC-5 |
| I-4 | NEW | Finished-PR worktree has no tracked modifications | removal | completion check | AC-1, AC-3 |
| EI-4 | EXISTING | Guards tolerate only Uncle-managed lines | guards | only_adds_managed | existing test |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Canonical block unchanged. `ensure()` and `strip_managed` signatures retained so existing callers/tests work; in-flight runs keep snapshot tolerance (decision: keep).

## 8. Failure behavior
Dirty tracked file or `.gitignore` mismatch at publish: print file names and reason, exit non-COMPLETE. Unwritable info/exclude: warn, continue.

## 12. Rollback
Revert commits; no data/schema change. Exclude block is harmless to leave.

## 14. Non-goals
Change canonical block; change `.uncle/workflow/` treatment; clean `parallel/step-*`.

## 15. Assumptions
- Existing in-flight runs: tolerance kept (open question resolved: keep).
- `.git/info/exclude` is shared across linked worktrees and supports `!` negation with same precedence; a legacy bare `.uncle` in tracked `.gitignore` outranks it, so worktree creation still normalizes pre-audit.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | After a change run completes in a fixture repo (with and without PR), `git status --porcelain --untracked-files=no` is empty and `.gitignore` is byte-identical to the audited tree. | New fixture test scripts/tests/gitignore-clean-end-test.py plus shell publish test; run via run-python-tests.sh/run-shell-tests.sh. |
| AC-2 | Publish fails with a message naming the file if `.gitignore` bytes (or any tracked file) differ from the audited tree after audit/attest; the PR commit tree equals the audited tree. | Fixture test mutating `.gitignore` between attest and publish; asserts nonzero status and file named. |
| AC-3 | `auto_removal_content_refusal` passes for a clean finished worktree and still refuses when another tracked file is dirty. | Shell test extending pr-auto-publish-test.sh. |
| AC-4 | With a base `.gitignore` lacking the managed block and with one already canonical, ignore coverage is provided without a post-audit tracked edit; any tracked edit occurs only at worktree creation and appears in the audited diff. | Two fixture cases in new test. |
| AC-5 | TUI `load_config`, config-stamp reload and project switch never modify a tracked file; they write only `.git/info/exclude` and print a deferral notice when a legacy tracked rule remains. | Test calls `_ensure_uncle_gitignored` repeatedly on fixture repo and asserts `.gitignore` bytes unchanged and exclude contains canonical block once. |
| AC-6 | Defect injection: reintroducing a tracked-file `ensure()` call after the audit makes the new tests fail. | Documented injection run in test report/IMPLEMENTATION_NOTES. |
| AC-7 | Ignore semantics preserved: `.uncle/workflow/` ignored, `.uncle/docs/` and attestation files visible to `git status`/`git check-ignore` using exclude-only rules, including from a linked worktree. | Fixture test with git check-ignore in main and linked worktree. |

