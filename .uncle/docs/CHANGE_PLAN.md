# Change plan: issue 276

Omitted sections: schema/persistence (none), migration (none), concurrency (none), feature flag (gated by existing UNCLE_PUBLISH_MODE=handoff)

Seeded from [unclehq/uncle#276](https://github.com/unclehq/uncle/issues/276).

Issue 276

## 1. Selected technical approach

D-1 (revised, AR-001/AR-008): no project commit is created, no branch is created, HEAD is not created or advanced, and the user's real index and working tree are never read-modified or written. Build, verification, approval and completion neither create nor require a project commit or a clean tree, in every mode. Add `run_policy_snapshot_base` in `scripts/lib/run-policy.sh`, called from the existing no-history branch of `run_policy_change_branch` (line ~164) only when `UNCLE_PUBLISH_MODE=handoff` and HEAD is unborn; all other modes behave exactly as today. It captures the starting tree as a file-hash and path inventory that includes untracked files and excludes all `.uncle/` paths, built in an isolated temporary index (`GIT_INDEX_FILE` pointing at a temp file, removed on exit, starting empty so pre-staged `.uncle/` entries in the user's index cannot leak in): `git add -A -- . ':(exclude).uncle'` against the temp index, then `git write-tree`. The tree is verified to contain no `.uncle/` path (`git ls-tree -r --name-only`); if any appears the snapshot is abandoned. The resulting tree id and inventory are exported/recorded as hand-off base evidence (`UNCLE_HANDOFF_BASE_TREE`). Where the hand-off exporter requires a commit-shaped base id, an unsigned internal evidence object may be derived from that tree with `git -c commit.gpgsign=false -c user.name=Uncle -c user.email=uncle@localhost commit-tree --no-gpg-sign`, held only under the private ref `refs/uncle/handoff-base`; it is not on any branch, is not a project commit, and is never pushed. On any failure (including after the temp-index add) it removes the temp index, warns, leaves the real index and working tree byte-identical to their pre-run state and HEAD unborn, and returns 0 as today. If consuming this base requires edits to `change-pr.sh` beyond reading the exported value, stop and amend the plan.
D-2: `scripts/lib/audit-verdict.sh:216` completion text names only artifacts confirmed written for this run (e.g. the PR URL only if a PR was published, `handoff.json` only if the hand-off record exists on disk, the attestation only if `.uncle/attestation.json` exists); HEAD existence is not a condition. When no such artifact was confirmed, the text points to `.uncle/docs/FINAL_AUDIT.md`.
D-3: `scripts/change-workflow.sh:5280-5283` no-HEAD message: when `UNCLE_PUBLISH_MODE=handoff` and no base evidence was captured, say no hand-off record was written because there is no base. Non-hand-off text unchanged.

## 2. Alternatives
(a) Write hand-off with empty base when no HEAD: needs engine changes (`head()`, journal, attest) throughout change-pr.sh; high risk. (b) Fix only the host: outside repo.

## 3. Why preferred
Smallest surface; reuses the fully tested hand-off path; no engine or schema edits.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
`change-pr.sh`, `handoff_export.py`, host script, `uncle verify`.

## 6. Data flow / 7. state

The seed runs only under UNCLE_PUBLISH_MODE=handoff. In hand-off mode the base is built from an isolated index (inventory includes untracked files); its commit/tree sha becomes `original_head` in the audit-created journal and `handoff.json.base_commit`, with the inventory stored alongside. Outside hand-off mode no commit is created and the starting tree is represented by the file inventory and hashes only. HEAD remains unborn in both cases. No state-machine change.

## 10. Compatibility
Only the hand-off-mode + unborn-HEAD case changes. Hosts must treat the seed commit as local; release owner to clone the real base per the issue (out of scope).

## 12. Error and recovery

Seed failure -> warning, continue; the real index and work tree are left exactly as they were before the run (the seed uses only a temporary index, which is deleted), so a failed startup never changes the user's staged selections. D-3 message makes the missing record explicit. A rerun on an existing seed sees HEAD and skips seeding.

## 14. Rollback
Revert the change; no persisted format changes.

## 16-17. Automated and regression tests

T-1 `scripts/tests/run-policy-test.sh`: cases for seed (hand-off, unborn), no seed without hand-off, no seed with existing HEAD (HEAD unchanged). INV-3 cases: (a) unborn repo with `.uncle/` files (e.g. `.uncle/docs/PLAN.md`, `.uncle/state`) already staged in the user's index plus a normal source file -> `git ls-tree -r --name-only HEAD` contains no `.uncle/` path, contains the source file, and the user's real index is unchanged (same `git ls-files -s` output and index file hash before and after, pre-staged `.uncle/` entries still staged); (b) untracked `.uncle/` -> absent from the seed; (c) failure injected after the temporary index has been populated (e.g. failing `commit-tree`/`update-ref` via PATH shim or env hook) -> warning emitted, function returns 0, HEAD still unborn, real index listing and work-tree file hashes identical to the pre-run snapshot, no temp index file left behind. T-2 new `scripts/tests/handoff-no-base-test.sh` has separate scenarios, each in its own temp repo with no commits, git signing disabled in the fixture, gh/remote absent. T-2a (successful seed): the fixture explicitly arranges a NOT_READY final audit (AC-3 applies only to NOT_READY) and drives the unattended hand-off completion path; assert handoff.json (attestation present, audit_verdict NOT_READY, draft true, base_commit = seed sha) and that `.uncle/attestation.json` exists; D-2 assertions are artifact-based: completion text mentions the hand-off record and attestation only when those files exist and never claims a PR in hand-off mode. T-2c (non-NOT_READY): with a READY audit, assert audit_verdict and draft keep their existing mapping (draft not forced true). T-2b (injected seed failure, e.g. commit forced to fail): HEAD stays absent; assert the D-3 no-hand-off-record message, that no handoff.json is written, that completion text names no unwritten artifact and points to `.uncle/docs/FINAL_AUDIT.md`, and that the exit status equals the pre-change exit status for the same no-HEAD run. Reuse harness style of unattended-test.sh and fixtures of handoff-export-test.py. T-2 is added to `critical-suites.txt` as `handoff-no-base`. Regression: the driver's two default runners; also run explicitly `bash scripts/run-shell-tests.sh -- handoff-no-base` (confirm flag form with `--help`). Tests that must fail before the fix: T-2a handoff.json assertion; T-1 case (a) must also fail against a naive `git add -A -- . ':(exclude).uncle'` plus `git commit` implementation.

T-3 (AR-012, inside T-1/T-2 fixtures): under a hostile inherited environment (global/system config with `commit.gpgsign=true`, `tag.gpgsign=true` and `gpg.program` set to a fake signer that records each invocation to a file and exits non-zero), create the fixture repository and run the seed and hand-off paths. Assert the recorder file shows zero invocations and every fixture Git subprocess received both repo-local signing settings and the explicit `-c ...=false` / `--no-gpg-sign` / `--no-sign` flags.

## 18. Manual verification
None required; optionally run a hand-off build in a commit-less sandbox.

## 19. Observability
Seed emits one stderr line naming the seed commit sha.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/run-policy.sh` | add seed function (isolated temporary index via GIT_INDEX_FILE, write-tree, commit-tree, update-ref; `.uncle/` excluded from the seed tree even if pre-staged; real index and work tree untouched on success and failure) and call | give hand-off a base commit | Medium: runs before branch logic | T-1 (incl. unborn repo with pre-staged `.uncle/` files asserting no `.uncle` paths in the seed tree, index-preservation, and failure-after-staging cases) |
| `scripts/lib/audit-verdict.sh` | conditional completion message | wording truthful | Low | T-2a, T-2b |
| `scripts/change-workflow.sh` | hand-off no-HEAD message | truthful output | Low | T-2b |
| `scripts/tests/run-policy-test.sh` | seed cases | cover AC-1, AC-2 | Low | itself |
| `scripts/tests/handoff-no-base-test.sh` | new suite | cover AC-3..5 | Low | itself |
| `scripts/tests/critical-suites.txt` | add suite name | run in default tier | Low | runner |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| With UNCLE_PUBLISH_MODE=handoff and unborn HEAD, a base snapshot (tree id plus file-hash/path inventory including untracked files, excluding .uncle/) is captured without creating a project commit, creating HEAD or a branch, changing the index, or invoking a signer. | BH-1 | INV-2, INV-3 | run-policy.sh | T-1 (incl. unborn repo with pre-staged .uncle/ files: seed built in an isolated temporary index, seed tree has no .uncle/ paths, user's index unchanged, failure-after-staging case) | none |
| AC-2 | BH-5, BH-6 | INV-4 | run-policy.sh | T-1 (incl. failure-after-staging leaves index and working tree unchanged) | none |
| AC-3 applies to a NOT_READY audit: for an unattended hand-off build that starts commit-less and ends with a NOT_READY audit, handoff.json is written with attestation present, audit_verdict NOT_READY and draft true. Other audit outcomes retain their existing verdict and draft mapping. | BH-2 | INV-1 | run-policy.sh | T-2a | optional |
| AC-4: Completion text names only artifacts confirmed written for this run (PR, hand-off record, attestation); otherwise it points to .uncle/docs/FINAL_AUDIT.md. HEAD existence alone is not the condition. | BH-3 | - | audit-verdict.sh | T-2a, T-2b | none |
| AC-5 | BH-4 | - | change-workflow.sh | T-2b | none |
| AC-6 | all PRESERVE | all EXISTING | all | driver commands | none |

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST.md fix 1 | AC-1, AC-3 | hand-off carries a commit-free base record; build, verification and completion never create or require a project commit | commit-free snapshot (D-1): isolated temporary index excluding .uncle plus file-hash and path inventory including untracked files; runs only under UNCLE_PUBLISH_MODE=handoff, never modifies the user's index, HEAD stays unborn, no project commit in any mode | user's binding commit-free rule; revisable DESIGN choice within it, seed limited to the user-chosen hand-off publish flow | CAP-git | CODING |
| R-2 | REPOSITORY | CLAUDE.md signing rules | AC-1 | no signer is invoked by the product path; fixture commits disable signing | D-1 never invokes git commit or any signer and makes no real-project commit, branch, or index change; any evidence object uses `--no-gpg-sign` under a private ref; test fixtures set `commit.gpgsign=false`, `tag.gpgsign=false` repo-locally plus explicit `-c commit.gpgsign=false -c tag.gpgsign=false` and `--no-gpg-sign`/`--no-sign` on every fixture Git subprocess; a negative test runs under inherited `commit.gpgsign=true` with a failing recording fake signer (`gpg.program`) and asserts zero invocations | mandated | CAP-git | CODING |
| R-3 | USER | issue fix 2 | AC-4 | completion message names only artifacts confirmed written this run | D-2 | direct | CAP-bash | CODING |

Constraint (AR-008): the implementation must not create a project commit, checkpoint or tag to satisfy any stage; only disposable test fixtures may commit, and then with signing disabled.

Feasibility: run-policy.sh:158-166 and change-pr.sh:2064 inspected; local git and bash only. No live-auth prerequisites.

## 20. Implementation sequence

Steps 1-3 are independent files and may run in parallel.

1. Commit-free base snapshot function in run-policy (D-1 revised; R-1, R-2): runs only under UNCLE_PUBLISH_MODE=handoff; builds the seed tree in an isolated temporary index (write-tree) from a file-hash and path inventory that includes untracked files and excludes `.uncle/` even if pre-staged; the user's real index, worktree and HEAD are left unchanged on success and failure; non-hand-off modes make no commit, add or index change; `.uncle` exclusion is verified on the written tree.
   Owns: `scripts/lib/run-policy.sh`
2. Message fixes (D-2 artifact-based completion wording, D-3)
   Owns: `scripts/lib/audit-verdict.sh`, `scripts/change-workflow.sh`
3. Tests: seed cases, new suite (two scenarios T-2a/T-2b), critical-suites entry, written from the spec contract. The recording fake-signer helper for the AR-012 negative signing test is inlined in handoff-no-base-test.sh (no separate file) and that script is a protected verification path. Also assert the fixture's HEAD and refs are unchanged by any non-hand-off run.
   Owns: `scripts/tests/run-policy-test.sh`, `scripts/tests/handoff-no-base-test.sh`, `scripts/tests/critical-suites.txt`
4. Verification only: run the two default runners plus the explicit suite command and report results. Edits only files already owned by steps 1-3; creates no new files and makes no project commit.
   Owns: `scripts/lib/run-policy.sh`, `scripts/lib/audit-verdict.sh`, `scripts/change-workflow.sh`, `scripts/tests/run-policy-test.sh`, `scripts/tests/handoff-no-base-test.sh`, `scripts/tests/critical-suites.txt`
   Depends on: 1, 2, 3

## 21. Scope cuts under time pressure

D-3 and AC-5 verification remain required unless the user explicitly approves a revised scope. If time expires, cut only optional items first: the optional manual hand-off run in a commit-less sandbox, then extra edge-case variants in T-1 (but keep the T-1 pre-staged regression). Never cut the commit-free snapshot seed behavior (D-1), including its isolated-index and `.uncle` exclusion guarantees, D-2, D-3, or the T-2 assertions that cover AC-3, AC-4 and AC-5 (including the handoff.json assertion).

## 22. Risks and unresolved questions
- Synthetic base sha differs from the host's real base; host must clone the real base (issue item 3, release owner).
- A2 (journal creation without remote) is verified by T-2; if it fails, stop and amend the plan.
- Runner flag form for one suite is unconfirmed (A1); fall back to running the new script with `bash` directly.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Partially accepted | Project commits during build are prohibited, so D-1 must not commit on HEAD/branch or touch the index; but the hand-off engine needs a base id, so a non-branch snapshot object plus a hash/path inventory is used instead. | Rewrote D-1 (s1.1), s6.1, R-1, R-2, AC-1 and step-1 to a commit-free snapshot: isolated index, inventory including untracked files, HEAD stays unborn. |
| AR-002 | Accepted | HEAD existence does not prove a PR or attestation was written, so completion wording must follow confirmed artifact outcomes. | D-2 in s1.1 and T-2 in s10.1 now key completion text on artifacts confirmed written this run, else point to FINAL_AUDIT.md. |
| AR-003 | Accepted | AC-3 lacked an audit-result precondition while BH-2 limits NOT_READY/draft:true to a NOT_READY audit; T-2 must arrange that audit explicitly. | AC-3 now applies only to a NOT_READY audit; T-2 arranges a NOT_READY audit and checks that other verdicts keep their existing mapping. |
| AR-004 | Accepted | AC-5 is a mandatory acceptance criterion, so the plan must not allow cutting D-3 or its test unilaterally. | Section 21 (s17.1) now keeps D-3 and AC-5 verification required unless the user approves a revised scope; only non-acceptance items may be cut. |
| AR-005 | Partially accepted | Build, verification and completion must stay commit-free, but the issue's hand-off needs a base commit, so the seed is confined to the user-selected hand-off publish mode. | Rewrite D-1, section 6, R-1 and step 1 so the seed runs only under UNCLE_PUBLISH_MODE=handoff, uses an isolated index, and keeps non-hand-off builds commit-free. |
| AR-006 | Accepted | A pathspec exclude on git add does not remove already-staged .uncle entries, so committing the index could violate INV-3 and alter the user's index. | D-1 now builds the seed tree in an isolated temporary index excluding .uncle, leaves the user's index untouched; T-1 adds pre-staged and failure-after-staging cases. |
| AR-007 | Accepted | Real gap: `git add -A` can leave the index changed if commit fails, silently altering the user's staged selections. | D-1 builds the seed with an isolated temporary index (GIT_INDEX_FILE); §12 and T-1 add index/work-tree preservation on failure with a failure-after-staging test. |
| AR-008 | Accepted | A real project commit during build startup contradicts the binding no-project-commit rule; commits are a user-approved publishing action and signing rules govern only disposable fixtures. | Replace D-1 in s1.1 with a commit-free file-snapshot base; update R-1, R-2, step-1 and the s17 scope cut; add a no-commit constraint to s15. |
| AR-009 | Accepted | A pathspec exclude on git add does not remove already-staged .uncle entries, so committing the live index could violate INV-3; an isolated index fixes this and leaves the user's index untouched. | Rewrote D-1 (s1.1) to build the seed tree from a temporary GIT_INDEX_FILE excluding .uncle, and T-1 (s10.1) to add a pre-staged .uncle case and an index-unchanged assertion. |
| AR-010 | Accepted | A pathspec exclude on git add does not remove already-staged .uncle entries, so INV-3 needs an explicit pre-staged-state test and an isolated-index mechanism. | D-1 builds the seed from an isolated index excluding .uncle; T-1 adds an unborn repo case with staged .uncle files asserting the seed tree has no .uncle paths. |
| AR-011 | Accepted | A successful seed means HEAD exists, so the no-HEAD messages (D-3, BH-4) can only be exercised in a separate injected-seed-failure case. | s10.1 splits T-2 into T-2a (successful seed) and T-2b (injected seed failure); traceability and change-impact rows updated to match. |
| AR-012 | Accepted | Disabling signing alone does not prove an inherited signing=true config cannot reach a signer; a recording fake signer test is a cheap, direct proof. | R-2 mechanism extended and s10.1 gains a negative test with inherited signing=true and a failing recording fake signer asserting zero invocations. |
