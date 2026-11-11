# Change plan: issue 260

Seeded from [unclehq/uncle#260](https://github.com/unclehq/uncle/issues/260).
Issue 260

Omitted sections: Schema/persistence (only an untracked marker file), Concurrency (single marker write), Migration (none), Feature flag (none), Observability (none)

## 1. Selected technical approach

Decision D-1: add a per-project freeze marker `<root>/.uncle/workflow/gitignore-frozen`. `uncle_gitignore.ensure()` returns False without touching `.gitignore` when the marker exists. New `uncle_gitignore.freeze(root)` writes the marker and returns a bool. Refusal rule: freeze() refuses symlinks at every component of the marker path (`<root>/.uncle`, `<root>/.uncle/workflow`, and the `gitignore-frozen` leaf), checked with lstat without following links. It creates the marker without following links or truncating an existing target (open with O_CREAT|O_EXCL|O_NOFOLLOW; an already-existing regular-file marker counts as frozen, an existing symlink is refused) and never writes outside the project root. Fail-closed rule: if freeze persistence fails (permission error, refused symlink, read-only filesystem), the failure must NOT restore normalization. `freeze()` records the freeze in-process (module-level frozen-roots set) so later `ensure()` calls in the same process stay read-only, and call sites emit a visible warning and set a non-writing guard (env `UNCLE_GITIGNORE_FROZEN=1`, inherited by child processes and resumed steps in that run). `ensure()` honors the marker, the in-process record, and the env guard, so inability to persist the marker never resumes tracked-file writes. Freeze is invoked (a) after `git push` succeeds in `change-pr.sh`, (b) before the commit in `from-issue.sh` finalize, (c) before the merge commit in `stagegate.sh`. Pre-freeze normalization (worktree creation, bind, completion) is unchanged, so it stays in the committed diff.
Decision D-2: no existing test is edited; freeze calls use `python3 -c 'import ...'` / in-Python `uncle_gitignore.freeze(` so the `CallerEnumeration` regex (only matches `.ensure(` and `python3 ... uncle_gitignore.py`) is not tripped.

Decision D-3: scope of the guarantee. The enforced guarantee is that no uncle code path writes `.gitignore` after the freeze boundary (guarded in `ensure()`). During implementation, inventory every uncle writer of tracked files reachable after finalize/publish (grep scripts and lib for writes outside `.uncle/`), and record the inventory in `IMPLEMENTATION_NOTES.md`. Any writer found that targets a tracked file other than `.gitignore` is either made to check the freeze marker (read-only when frozen) or listed there as a stated limit (U-1). No broader write-blocking layer is added.

## 2-3. Alternatives and rationale

| Alt | Why not |
|---|---|
| Stop all tracked `.gitignore` writes; use `info/exclude` only | Legacy tracked bare `.uncle` beats `info/exclude`, re-hiding `.uncle/docs` and re-opening the 2379-file leak (see `uncle_gitignore.py:20-30`) |
| Restore `.gitignore` to HEAD after push | Is itself a post-push write |

Selected: freeze marker, fail-closed. Minimal, testable, keeps pre-commit behavior. A marker-write failure keeps ensure() read-only via the in-process record and inherited env guard rather than restoring normalization. Stated limit (U-1): writers outside uncle's code, and a separate later process with neither marker nor inherited guard, are not covered.

## 4. Components to modify
See change-impact table.

## 5. Not modified
`ensure_exclude`, `uncle_tui.py`, plan prompts, `change_plan_duties.py`, existing tests.

## 6-7. Data flow / state

New state: marker file present => ignore handling frozen for this project root. Set once and never cleared by uncle on success; creating fresh run state on the same project root preserves it (AR-004). The only removal is rollback of a marker created by a failed finalize/merge commit attempt (a pre-existing marker is always preserved).

## 8. Interfaces
New `uncle_gitignore.freeze(project_root)->bool`; `ensure()` unchanged signature. CLI unchanged.

## 10. Compatibility
No marker => identical behavior.

## 12. Error and recovery

Marker write failure fails closed: freeze() still sets the in-process flag and the call site sets the inherited env guard, so ensure() stays read-only; a warning is emitted and freeze() returns False. It never degrades to current write behavior. A failed finalize/merge commit removes only the marker that attempt created.

## 14. Rollback plan
Revert the commit. Stale markers are inert.

## 16. Automated-test strategy

New `scripts/tests/gitignore-post-push-test.py` (name uses hyphen): fixtures use `git -c commit.gpgsign=false -c tag.gpgsign=false`, `--no-gpg-sign`, repo-local signing off. Cases: frozen ensure with initially absent `.gitignore` asserts it still does not exist after API and CLI calls (existence check, no hashing); frozen ensure with canonical, legacy and bare `.uncle` files asserts bytes equal the pre-invocation snapshot; CLI frozen no-op; unfrozen still normalizes; freeze refusal with symlinked `.uncle`, symlinked `workflow`, and symlinked `gitignore-frozen` leaf (link targets untouched); unwritable marker location: freeze returns False and later/resumed ensure calls (in-process and via inherited env guard) leave `.gitignore` byte-identical; marker survives fresh run state creation on a frozen root; failed-commit retry (marker created by the failed attempt removed and retry normalizes; pre-existing marker preserved); non-git root; execution tests running each freeze call site (change-pr.sh post-push, from-issue.sh finalize, stagegate.sh merge) in disposable fixtures with mocked publishing and signing, asserting the target root is frozen and a failed push creates no marker; source-order checks only as a secondary supplement. Regression test that fails before the fix: frozen-ensure case (before: file rewritten).

## 17. Regression strategy
Existing gitignore suites unchanged.

## 18. Manual verification
M-1: in a throwaway repo with tracked legacy `.gitignore`, call freeze then the CLI; `git status` clean.

## Verification commands
- `bash scripts/run-shell-tests.sh`
- `bash scripts/run-python-tests.sh`
- `bash scripts/run-python-tests.sh -- gitignore-post-push` (runs the new suite explicitly; not in the default tier)

Protected verification paths: `scripts/tests/` (existing files unchanged; only the new file is added), `scripts/tests/critical-suites.txt` edited by step 3.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Expected | AC-1, AC-3 | No uncle edit of `.gitignore` after commit/push; other tracked-file writers after that boundary are inventoried and guarded or recorded as limits (D-3) | Freeze marker + ensure guard (DESIGN, revisable) + post-freeze writer inventory (D-3) | Smallest change preserving pre-commit normalization | CAP-PY3 | Inspected `uncle_gitignore.py:80-128`, `change-pr.sh:1963`; AC-3 is verified by executing each call site in disposable fixtures, not by source order alone | CODING |
| R-2 | USER | CHANGE_REQUEST AC-3 | AC-5 | Any change is planned, pre-commit | Doc note; edits remain pre-freeze | Keeps diff honest | CAP-PY3 | `plan-duties.md:7` | CODING |
| R-3 | REPOSITORY | CLAUDE.md signing rules | AC-1 | Tests disable signing | Fixture flags | Never touch user signer | CAP-GIT | Pattern in `gitignore-clean-end-test.py:15-30` | CODING |

No live-verification-only prerequisites; no credentials needed.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/uncle_gitignore.py` | Add `freeze()`, guard in `ensure()`. `freeze()` sets a process-level frozen flag BEFORE attempting to persist the marker (refusing symlinks at `.uncle`, `workflow`, and the marker leaf); `ensure()` returns False without writing if the flag is set or the marker exists. If persisting the marker fails (permissions, refused symlink), the flag still keeps this process read-only, a warning is logged, and `freeze()` returns False; call sites must not fall back to normalization. Inability to persist never restores tracked-file writes. | Enforce V-1 | Low | `gitignore-post-push` (incl. unwritable `.uncle/workflow` and symlinked marker path: `ensure()` after failed `freeze()` leaves `.gitignore` bytes/absence unchanged in-process), `uncle-gitignore-test.sh` |
| `scripts/lib/change-pr.sh` | Call `uncle_gitignore.freeze` after push at ~1963 | Post-push freeze | Medium (embedded Python in publish path) | `gitignore-post-push` order check, `gitignore-clean-end` |
| `scripts/from-issue.sh` | Freeze before `git add -A`/commit (~391); if the commit attempt fails, remove the marker created by that attempt (preserve a pre-existing one) | Finalize commit | Low | `close-flow-test.sh`, new order check |
| `scripts/stagegate.sh` | Freeze before `worktree_merge_finish_all` (~7152); if the merge commit attempt fails, remove the marker created by that attempt (preserve a pre-existing one) | Merge commit | Low | shell suites, new order check |
| `scripts/tests/gitignore-post-push-test.py` | New | AC-1..4 | None | itself |
| `scripts/tests/critical-suites.txt` | Add `gitignore-post-push` | Run in default tier | None | runner |
| `docs/plan-duties.md` | Note: no post-commit ignore edits | AC-5 | None | review |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: with the freeze marker present, `ensure()` and the CLI never modify `.gitignore`. For an initially absent `.gitignore`, assert it remains absent (existence check, no hashing) after each frozen API and CLI invocation. For an existing `.gitignore` (canonical, legacy, bare `.uncle`), compare its bytes against the unchanged pre-invocation snapshot. | S-2, S-6 | V-1 | uncle_gitignore.py | gitignore-post-push: missing-file case asserts `.gitignore` still does not exist after frozen ensure() and CLI, gitignore-post-push: existing-file cases (canonical, legacy, bare `.uncle`) assert bytes equal the pre-invocation snapshot after frozen ensure() and CLI, gitignore-post-push: marker survives creation of fresh run state on the same project root | M-1 |
| AC-2 | S-4 | EXISTING | uncle_gitignore.py | uncle-gitignore-test.sh | - |
| AC-3 | S-1, S-3 | V-1 | change-pr.sh, from-issue.sh, stagegate.sh | gitignore-post-push execution tests: disposable-fixture integration tests run each freeze call site (change-pr.sh post-push, from-issue.sh finalize, stagegate.sh merge) with mocked publishing and signing, assert the target root's marker exists afterward, and assert a failed push creates no marker, gitignore-post-push source-order checks (secondary, supplementary only) | - |
| AC-4 | S-1 | V-2 | uncle_gitignore.py | gitignore-post-push (incl. symlinked `.uncle`, symlinked `workflow`, and symlinked `gitignore-frozen` leaf cases: freeze returns False, symlink target outside the root is unchanged and not created/truncated) | - |
| AC-5 | - | - | docs/plan-duties.md | - | diff review |
| AC-6; also: if a finalize (from-issue.sh) or merge (stagegate.sh) commit attempt fails, the freeze marker created by that attempt is removed so retries still normalize; a marker that existed before the attempt is preserved. | S-4, S-5 | V-3, V-4 | all | shell+python runners, gitignore-post-push failed-commit retry regression: failed commit removes the attempt's marker and retry normalizes; pre-existing marker preserved | - |

## Implementation sequence
1. Core freeze: add `freeze()` and the `ensure()` guard; keep CLI. Decisions D-1. Owns: `scripts/lib/uncle_gitignore.py`
2. Call sites: add freeze after push in `change-pr.sh`, before commit in `from-issue.sh` and `stagegate.sh` (each file edited once; builds on step 1's `freeze` API). Owns: `scripts/lib/change-pr.sh`, `scripts/from-issue.sh`, `scripts/stagegate.sh` — Depends on: 1
3. Tests: new suite plus critical-suites entry (independent of step 2 files; written against the step 1 API contract `freeze(root)`). Owns: `scripts/tests/gitignore-post-push-test.py`, `scripts/tests/critical-suites.txt` — Depends on: 1
4. Docs note. Owns: `docs/plan-duties.md`

## Scope cuts under time pressure

The finalize (`from-issue.sh`) and merge (`stagegate.sh`) freeze calls and the `docs/plan-duties.md` note are required deliverables (AC-3, AC-5) and cannot be cut without first revising the approved acceptance criteria. If time expires, cut first: extra edge-case fixtures beyond the AC-1..4 minimum, then the manual M-1 walkthrough write-up; the `ensure()` guard and the push-site freeze are never cut.

## Risks and unresolved questions

| ID | Risk | Mitigation |
|---|---|---|
| U-1 | The literal post-push writer was not located; may be external | Guard uncle's own writers; state limit in `IMPLEMENTATION_NOTES.md` |
| U-2 | `CallerEnumeration` may already fail at baseline for `stagegate.sh:483` | Baseline run is authority; do not edit that test |

U-3 decision (AR-004): a new run on the same project root preserves the freeze marker; creating fresh run state must not remove it. Uncle never clears the marker, so a reused worktree after push stays frozen (S-6). Any wording elsewhere that a fresh run state resets the marker is superseded by this rule.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Restoring normalization on marker-write failure reopens the original defect after a successful commit or push, contradicting the guarantee. | D-1 now makes ensure() fail closed when the marker is present or its persistence failed, and s2 records the limit. |
| AR-002 | Partially accepted | The tracked-file guarantee exceeded the .gitignore-only guard; an inventory of uncle writers after the freeze boundary is needed, but a general write-blocking layer is out of scope. | Narrowed R-1 to .gitignore and added an implementation inventory of post-freeze tracked-file writers in s1 (D-3). |
| AR-003 | Accepted | AC-3 and AC-5 are approved acceptance criteria, so the scope-cut list must not remove their deliverables. | Section 18 now lists only non-required work as cuttable and states the finalize/merge freeze calls and docs note are required. |
| AR-004 | Accepted | The reset boundary was ambiguous; a reused root must stay frozen (S-6), so fresh run state must not clear the marker. | Risk U-3 now states a new run on the same project root preserves the marker; AC-1 traceability adds a preservation test. |
| AR-005 | Accepted | A failed finalize/merge commit must not leave normalization disabled; removing the marker that attempt created restores retry behavior while preserving pre-existing markers. | Add AC-6 failed-commit rollback criterion and a failed-commit retry regression test to the traceability rows. |
| AR-006 | Accepted | Symlink refusal must cover the whole marker path so the write cannot be redirected outside the project. | s1.1 D-1 now defines refusal at .uncle, workflow and gitignore-frozen with a no-follow, no-truncate create; AC-4 gains a test. |
| AR-007 | Accepted | A failed marker write must not restore tracked-file writes after publish; the guard has to fail closed in-process and for later processes. | Edit s15.1 uncle_gitignore.py row: ensure() read-only after freeze(), including in-process flag and failed persistence; add test coverage. |
| AR-008 | Accepted | Source-order checks cannot prove a call site is reachable, targets the right root, or is skipped on push failure; execution tests can. | AC-3 and R-1 now require disposable-fixture execution tests of each freeze call site (mocked publish/signing, root frozen, failed push leaves no marker); source-order checks become secondary. |
| AR-009 | Accepted | SHA-256 of an absent path is undefined and empty-bytes treatment would miss erroneous empty-file creation, so existence and content assertions must be separate. | AC-1 traceability row now requires: absent .gitignore stays absent after frozen API and CLI calls; existing files compared byte-for-byte to a pre-invocation snapshot. |
