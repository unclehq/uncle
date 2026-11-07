# Change plan

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (none new); Feature flag (existing WORKFLOW_CLOSE_ISSUE=0 opt-out is the containment); Observability (reuses existing reason messages).

## 1. Selected technical approach

Add two predicates to `scripts/lib/change-pr.sh`. `change_pr_in_worktree`: true only when `git rev-parse --absolute-git-dir` differs from `git rev-parse --path-format=absolute --git-common-dir` (a linked worktree); false if either git command fails; the `worktree-owned` marker alone never makes it true, so a stale marker in a plain repo changes nothing. `change_pr_worktree_owned`: true only when the marker `worktree-owned` exists under STATE_DIR (default `.uncle/workflow`), resolved to an absolute path against the project root before testing. In `change_pr_complete`: (a) widen the unattended auto-publish condition at line 66 to `CLOSE_ISSUE==1 && UNATTENDED==1 && (-s ORIGIN_FILE || (change_pr_worktree_owned && change_pr_in_worktree))`, so origin-less auto-publish needs the worktree-owned marker and a real linked worktree, and operator-made worktrees without the marker never auto-publish; (b) the new non-zero return applies only when `CLOSE_ISSUE==1 && UNATTENDED==1` in a run where `change_pr_in_worktree` is true: after the publish path, return 0 only when `CHANGE_PR_EXTRAS_REASON` is EXACTLY `published` or `published-draft-unreviewed` (exact string match, no glob/prefix); any other value, including empty or unset, returns 1 (this includes the pending case). With `CLOSE_ISSUE==0` (operator opt-out, 'handoff disabled'), `change_pr_complete` does not publish and returns 0; attended runs always return 0, so an attended decline or skip is not a failure; (c) in `scripts/change-workflow.sh` completion (~4988-5004) exit with `pr_rc` when it is non-zero (which by (b) happens only for unattended CLOSE_ISSUE==1 worktree runs), instead of unconditional `exit 0`; otherwise the driver exits 0. Attended dialogs unchanged. The engine already pushes without force, reuses existing PRs and supports origin-less runs, so it is not modified.

Detection contract for `change_pr_in_worktree` (AR-019): true if the marker `${STATE_DIR:-.uncle/workflow}/worktree-owned` exists; otherwise true if `git rev-parse --git-dir` differs from `--git-common-dir`; false when either git call fails (e.g. outside a repository). Marker presence alone suffices even in a non-worktree directory, subject to any stricter qualification decided by the owners of AR-007/AR-012.

## 2. Alternatives considered
- Write PR logic into worktrees.sh: rejected; duplicates the audited engine and bypasses tree/verdict gates.
- Always publish regardless of CLOSE_ISSUE: rejected; removes the documented operator opt-out and is not requested.
- Make all failures non-zero including non-worktree: rejected by constraint (no alteration beyond need).

## 3. Why preferred
Smallest surface; reuses the journaled, tree-attested engine; issue path untouched.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
`worktrees.sh`, `parallel_steps.py`, `from-issue.sh`, engine python in change-pr.sh, `stagegate.sh`, `workflow.sh`, review/approval gates, existing test expectations.

## 6. Data-flow changes

Unattended worktree completion now reaches `change_pr_publish` without an origin file; `change_pr_publish` already skips issue-eligibility when origin is empty. Remote and base rule: an origin-less worktree publish pushes only to the repository's configured default remote (`origin`, or the single configured remote if exactly one exists) and targets the repository default branch as PR base. If no remote is configured, or several remotes exist with none being `origin`, publish does not push, sets a failure reason naming the missing/ambiguous remote, and `change_pr_complete` returns 1. Failure rule: a push failure (or any publish failure) in an unattended worktree run with CLOSE_ISSUE=1 sets `CHANGE_PR_EXTRAS_REASON` to a failure reason (never `published*`), makes `change_pr_complete` return 1, and prints the stopped-extras message exactly once. Issue-reference rule: a no-origin worktree publish never emits issue-closing references (e.g. Closes/Fixes/Resolves #N) in the PR title or body and never closes any issue; the PR body is built without an issue link when ORIGIN_FILE is absent.

## 7. State-transition changes

None in state files or journal; process exit status differs for failed worktree publication. A non-zero exit runs the normal exit trap and does not mutate or clear the journal, so a re-run resumes from it.

## 8. Interface changes

New internal function `change_pr_in_worktree`; `change_pr_complete` may now return 1 (worktree runs only). Callers use `|| pr_rc=$?`, so set -e safe. Verdict rule for unattended worktree runs without an origin file: an unreviewed verdict publishes as a draft (reason `published-draft-unreviewed`) and returns 0; a failing (non-READY, reviewed) verdict does not publish, keeps the engine's existing no-publish reason, and returns 1.

## 10. Compatibility

Non-worktree and issue paths byte-identical in routing. Decision D-1: worktree detection uses the single definition in section 1 (change_pr_in_worktree: absolute-resolved worktree-owned marker under STATE_DIR OR git-dir != git-common-dir; false when git fails), so issue worktrees and operator-made linked worktrees count; no other section may define worktree detection differently. Issue worktrees already auto-publish via ORIGIN_FILE, so no double PR (journal + lookup guarantee one PR). This is asserted, not assumed: an unattended issue-linked run inside a worktree (worktree fixture that also has an ORIGIN_FILE) must call change_pr_publish exactly once.

## 12. Error and recovery

Reasons from `change_pr_no_pr` retained; stopped-extras printed via existing `change_pr_extras_print`; rerun resumes via journal. Decision D-2: on worktree publish failure the failure reason and the stopped-extras message are printed exactly once. `change_pr_complete` prints them, and the driver exits with `pr_rc` through the normal exit trap (on_exit), which must not print them again; the implementer adds a printed-once guard if the trap would repeat the print. A re-run resumes from the journal without duplicating a push or PR. A test counts occurrences of the reason/extras message in stderr and asserts exactly one.

## 14. Rollback plan
`git revert` the change commit; no state, schema or remote artifacts to unwind (created PRs remain, which is intended).

## 16. Automated-test strategy

Extend `scripts/tests/pr-auto-publish-test.sh` (stubs publish/engine; fixture worktree via `git -c commit.gpgsign=false`, `--no-gpg-sign`, local gpgsign=false): AC-1, AC-3, AC-4, AC-6, plus call-count for AC-2. Fixture must override STATE_DIR so the marker is tested. Cases:
(a) AC-3 exact-match allowlist (worktree, WORKFLOW_CLOSE_ISSUE=1): reason `published` -> rc 0; `published-draft-unreviewed` -> rc 0; empty, unset, `pending`, handoff-disabled, and an arbitrary other string (e.g. `published-other`) -> rc 1 (proves exact match, not glob).
(b) AC-6: in a worktree with WORKFLOW_CLOSE_ISSUE=0, assert publish is not called AND `change_pr_complete` returns 0 (and driver exit 0); non-zero return applies only when CLOSE_ISSUE=1.
(c) Driver exit status (AC-3) is verified behaviorally, not by grep: a shell test runs the completion path of `scripts/change-workflow.sh` with `change_pr_complete` stubbed to return 1 in a worktree fixture (CLOSE_ISSUE=1) and asserts exit status 1, and asserts exit status 0 for the same stub in a non-worktree fixture. It may live in `scripts/tests/pr-auto-publish-test.sh` or a new sibling shell test registered with `scripts/run-shell-tests.sh`.
(d) Detection (in_worktree is git-dir != git-common-dir only): git-dir-only linked worktree (true); marker-only in a plain repo with STATE_DIR overridden so the marker exists (false, no publish, behavior unchanged); neither (false); git failing outside a repo (false).
(e) Verdict cases (AR-011): with the engine stubbed to an unreviewed verdict, an origin-less unattended worktree run publishes as a draft (reason `published-draft-unreviewed`) and returns 0; with a failing verdict it does not call publish and returns 1.
(f) Failure-path single-print: worktree, publish stub failing, run through the completion/exit path with stderr captured; assert the stopped-extras message occurs exactly once (occurrence count == 1) so any on_exit duplicate print is caught.

Secret-hygiene check (AR-015): export a sentinel value (e.g. `GH_TOKEN=SENTINEL-SECRET-123`) in the test environment, run the publish-success and publish-failure worktree cases, and assert the sentinel appears in neither the published PR body (captured from the stub) nor stdout/stderr of `change_pr_complete`.

## 17. Regression-test strategy

Existing four routing checks, pr-verdict-binding, pr-reconcile, worktree-run tests, full suites via the baseline commands. Test would fail before change: AC-1 and AC-3 (no publish / rc 0), and the driver-exit test (worktree fixture with change_pr_complete stubbed to rc 1 exits 0 before the change, 1 after).

## 18. Manual verification
Run a headless non-issue build in a worktree against a scratch GitHub repo: PR opened; rerun reuses it; break remote auth to see non-zero exit with reason. LIVE_VERIFICATION phase only; not a coding prerequisite.

## 20. Implementation sequence

## Implementation sequence

1. Add `change_pr_in_worktree` and routing/return-code changes in `change_pr_complete` (R-1, R-2; AC-1,3,4,6).
   Owns: `scripts/lib/change-pr.sh`
2. Driver exit-status handling after `change_pr_complete` for worktree runs (AC-3); CLOSE_ISSUE=0 worktree runs still exit 0, and non-zero applies only when CLOSE_ISSUE=1. Not cuttable under time pressure: only README wording may be cut. Verified by the behavioral driver-exit test (worktree stub rc 1 -> exit 1; non-worktree stub rc 1 -> exit 0), not by grep.
   Owns: `scripts/change-workflow.sh`
   Depends on: 1
3. Tests for the cases in section 16, including: (a) the driver completion-path exit-status test (change-workflow.sh completion with change_pr_complete stubbed to rc 1; worktree: exit 1; non-worktree: exit 0); (b) detection cases (AR-019): marker-only (STATE_DIR overridden, plain repo), git-dir-only (linked worktree, no marker), neither (plain repo, no marker), and git failing outside a repo (false); (c) a worktree fixture that also has an ORIGIN_FILE: an unattended issue-linked run inside it must call change_pr_publish exactly once (AC-2 call-count).
   independent of 1-2 (written against the specified function contract), may run concurrently
   Owns: `scripts/tests/pr-auto-publish-test.sh`
4. **Driver exit-status test** — Add a shell test that runs the change-workflow.sh completion path with change_pr_complete stubbed to return 1: exit 1 in a worktree fixture (unattended), exit 0 in a non-worktree fixture and for attended runs. Register it in scripts/run-shell-tests.sh if that runner enumerates tests explicitly, and add it to the plan's Verification commands and protected verification paths.
   Owns: `scripts/tests/change-workflow-exit-status-test.sh`, `scripts/run-shell-tests.sh`
   Depends on: 2
5. Document behavior (AC-9).
   Owns: `scripts/README.md`

## 21. Scope cuts under time pressure

Cut first: README wording only (step 4). The routing fix, the driver exit-code change (step 2), the driver exit-status test and the routing tests are never cut, because INV-4/OB-3/AC-3 require a non-zero exit for failed unattended worktree publication.

## 22. Risks and unresolved questions

- Risk: marker detection also matches operator worktrees; accepted per 'all worktrees'.
- Risk: an extra non-zero exit surprises wrappers (TUI); only after real PR failure in worktrees.
- No blocking decisions.
- Ownership: step 2 (scripts/change-workflow.sh) owns the on_exit/extras single-print handling; if suppressing a duplicate print requires editing any other file, that file must be added to the step's Owns before implementation.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Constraints | AC-7 | No force push | Reuse engine plain push; no push edits | Engine already compliant (change-pr.sh ~1636) | CAP-none | CODING |
| R-2 | USER | CHANGE_REQUEST Constraints | AC-2, 4, 5 | Non-worktree and issue behavior unchanged | Gate all new routing on `change_pr_in_worktree` | Minimal surface | CAP-none | CODING |
| R-3 | USER | Success criteria | AC-3 | Failure surfaced, not claimed complete | rc 1 + driver exit (driver exits with pr_rc), only when WORKFLOW_CLOSE_ISSUE=1; CLOSE_ISSUE=0 returns 0. When CLOSE_ISSUE=1 in a worktree run, change_pr_complete returns 0 only if CHANGE_PR_EXTRAS_REASON is exactly `published` or `published-draft-unreviewed`; any other value (including empty/unset) returns 1 | Existing reason strings reused | CAP-none | CODING |
| R-6 | DESIGN | Review AR-014 | AC-1 | No-origin worktree publish never emits issue-closing references and never closes any issue | Build PR title/body without an issue link when ORIGIN_FILE is absent; automated test captures the body and asserts no Closes/Fixes/Resolves keyword or issue reference | Without an origin file issue-eligibility is skipped, so closing keywords must be explicitly suppressed (AR-014) | CAP-none | CODING |
| R-4 | DESIGN | Plan | AC-1 | PR creation via gh against default branch | Existing engine `gh pr create`; push only to the default remote (`origin` or the single configured remote); missing or ambiguous remote fails non-zero with a reason | Already implemented; feasibility seen at change-pr.sh ~1668; remote/base selection per s6.1 (AR-013) | CAP-gh | LIVE_VERIFICATION |
| R-5 | DESIGN | Review AR-015 | AC-1, AC-3 | No credentials or environment values in PR text or logs | Reuse existing engine body/reason strings, which carry no env values; add no new output interpolating environment variables, tokens or remote URLs with embedded credentials; test asserts a sentinel secret in env never appears in output | Unattended publish has no human reviewing output before it is posted | CAP-none | CODING |

Runner/config binding: bash/shell test runner `scripts/run-shell-tests.sh`. Live check: manual scratch-repo run (section 18); needs authenticated gh, non-secret evidence only.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/change-pr.sh` | Add `change_pr_in_worktree`; widen auto-publish condition; return non-zero for unpublished worktree runs | Core defect B-3/B-4 | Medium: shared with issue flow | pr-auto-publish-test.sh, pr-verdict-binding-test.sh |
| `scripts/change-workflow.sh` | Exit with `pr_rc` for worktree runs after completion | Do not claim completion on failure | Low-medium | grep/behavior test, suites |
| `scripts/tests/pr-auto-publish-test.sh` | Add worktree/no-origin, failure, non-worktree, opt-out cases | Success criterion: test for no-issue case | Low | itself |
| `scripts/README.md` | Document behavior | AC-9 | None | manual |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| Publish PR for non-issue worktree | OB-1 | INV-5 | change-pr.sh | AC-1 case | Scratch-repo run |
| Issue PR still once | OB-2 | INV-3, INV-5 | change-pr.sh | AC-2, No-origin worktree publish: assert PR body/title contain no closing keyword or issue reference | n/a |
| Failure surfaced: with WORKFLOW_CLOSE_ISSUE=1 a worktree run returns 0 only for reason exactly published or published-draft-unreviewed; any other value (including empty/unset) returns non-zero. With CLOSE_ISSUE=0 a worktree run returns 0. Attended worktree runs are exempt from INV-4: a declined or skipped dialog returns 0. | OB-3 | INV-4 | change-pr.sh, change-workflow.sh | AC-3 case (CLOSE_ISSUE=1: published, published-draft-unreviewed => 0; empty, unset, pending, other => 1; unattended: non-zero), AC-3 case (CLOSE_ISSUE=0 => 0), Attended worktree decline case (rc 0), Driver completion-path test: change_pr_complete stubbed rc 1 -> exit 1 in worktree fixture with CLOSE_ISSUE=1, exit 0 in non-worktree fixture and with CLOSE_ISSUE=0 | Break auth run |
| Reuse existing PR | OB-4 | INV-5 | engine (unchanged) | pr-reconcile-test.py | Rerun |
| Non-worktree unchanged; CLOSE_ISSUE=0 worktree run does not publish and returns rc 0 | OB-5, OB-6 | INV-2 | change-pr.sh | AC-4, AC-6 (asserts no publish and rc 0) | n/a |
| No force push | n/a | INV-1 | engine (unchanged) | AC-7 diff check | n/a |

Scope-cut override (supersedes the earlier scope-cut order): the driver exit-code change in `scripts/change-workflow.sh` (step 2) is NOT cuttable, because INV-4/OB-3/AC-3 require a non-zero exit when an unattended worktree publish fails. Only README wording (step 4) may be cut. The routing fix, the driver exit-code change and their tests are never cut.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The success-reason set was ambiguous; an exact two-value allowlist (empty/unset fails) is testable and matches AC-3. | s1.1 and R-3 state exact allowlist; s12.1 adds empty/unset/other-reason test cases. |
| AR-002 | Accepted | The 'handoff disabled' failure return contradicts the CLOSE_ISSUE=0 opt-out (OB-6/AC-6), so the non-zero rule must apply only when CLOSE_ISSUE=1. | Edit s1.1 (b)/(c) so CLOSE_ISSUE=0 worktree runs return 0 and the driver exits 0; update s12.1 and traceability rows s21.1.r3 and s21.1.r5 to assert rc 0. |
| AR-003 | Accepted | Attended worktree runs keep their dialogs unchanged (OB-7), so INV-4 must not apply to them; a declined dialog returns 0. | Traceability row s21.1.r3 now states attended worktree runs are exempt from INV-4 and a declined dialog returns 0; non-zero applies only to unattended runs. |
| AR-004 | Accepted | The worktree definition was ambiguous about marker path resolution, git-dir layouts and git failure; a single precise definition removes that. | Sections 1 (s1.1) and 10 (s9.1) now define change_pr_in_worktree precisely: absolute-resolved marker OR git-dir != git-common-dir, false on git failure. |
| AR-005 | Accepted | Push-failure behavior and extras-print count must be specified in the plan so they are testable, not left to the implementer. | Edited s6.1 and s10.1 to state push failure sets a failure reason, returns 1, and prints extras exactly once. |
| AR-006 | Accepted | The driver exit-code change implements the required non-zero exit (INV-4/OB-3, AC-3), so cutting it would contradict the requirements. | Step 2 marked non-cuttable and a scope-cut override block added (s21); only README wording may be cut. |
| AR-007 | Accepted | A marker-or-git-dir test lets a stale marker in a plain repo trigger auto-publish, which breaks 'non-worktree unchanged'. | s1.1, s9.1 and s12.1 now define in_worktree by git-dir != git-common-dir only, with marker-alone and plain-repo tests. |
| AR-008 | Accepted | Non-zero exit must not apply to attended runs, since attended dialogs are unchanged and a declined dialog is a legitimate outcome. | Section 1 (s1.1) now conditions the non-zero return and driver exit on UNATTENDED==1; attended runs always return 0. |
| AR-009 | Accepted | s1(b) treated 'handoff disabled' as failure, contradicting AC-6/OB-6; CLOSE_ISSUE=0 must return 0 and the non-zero rule applies only when CLOSE_ISSUE=1. | Edit s1.1 (b) and (c), R-3, s21.1.r3/r5 and s12.1 so CLOSE_ISSUE=0 worktree runs return 0 and non-zero applies only when CLOSE_ISSUE=1. |
| AR-010 | Accepted | Duplicate extras printing and exit-trap/re-run behavior should be specified, not left to the implementer. | Rewrote D-2 in s10.1 to fix exit via pr_rc, single reason print, and journal resume; clarified s7.1 on exit-trap and re-run. |
| AR-011 | Accepted | Verdict handling for origin-less unattended worktree publish was unstated; settling it avoids ambiguity between draft publish and refusal. | Added verdict rule to s8.1 (interface) and a verdict test case to s12.1 (automated tests). |
| AR-012 | Accepted | Auto-publishing from operator-made worktrees with no human dialog is unrequested and risky; only driver-owned worktrees (marker) should qualify. | Edited s1.1 and s9.1: origin-less unattended auto-publish requires the worktree-owned marker; git-dir comparison alone never triggers it. |
| AR-013 | Accepted | Remote and base were unspecified for origin-less worktree publish; a missing or ambiguous remote must fail visibly rather than guess. | Edit s6.1 to state remote/base rule and non-zero failure; update R-4 to match. |
| AR-014 | Accepted | With no origin file the issue-eligibility check is skipped, so the plan must state explicitly that non-issue worktree publish emits no closing references. | Section 6 data-flow text states no-origin worktree publish never emits issue-closing references or closes an issue; traceability row r2 adds a test for it. |
| AR-015 | Accepted | Unattended publish writes PR text and logs without a stated no-secrets rule; adding one is cheap and low risk. | Add restriction row R-5 and a test assertion in s12.1 that PR bodies and failure output contain no credentials or env values. |
| AR-016 | Accepted | A grep cannot prove the driver exits non-zero; a behavioral test of the completion path is required. | Sections 16, 17, step-2/step-3 and traceability s21.1.r3 now require a shell test running change-workflow.sh completion with change_pr_complete stubbed to rc 1 (worktree: exit 1; non-worktree: exit 0). |
| AR-017 | Accepted | Plan left failure reasons unenumerated; an exact allow-list with empty/unset treated as failure is unambiguous and testable. | s1.1(b) now states the exact-match success reasons; R-3, s21.1.r3 and the s12.1 test cases cover empty/unset and other reasons. |
| AR-018 | Accepted | Section 1(b) treating 'handoff disabled' as failure contradicts OB-6/AC-6; the opt-out must return 0 and the non-zero rule must apply only when CLOSE_ISSUE=1. | Edit s1.1 to scope the non-zero return to CLOSE_ISSUE==1 and return 0 without publishing when CLOSE_ISSUE=0; s12.1 and s21.1.r5 now assert rc 0 for AC-6. |
| AR-019 | Accepted | Detection edge cases were unspecified and untested. | Section 1 adds a detection contract; step-3 now requires marker-only, git-dir-only, neither and git-failure tests. |
| AR-020 | Accepted | Leaving duplicate extras printing to the implementer makes it untestable; a fixed single-print rule can be asserted. | Section 12 (s10.1) fixes single-print behavior; section 16 (s12.1) adds a test counting extras occurrences in stderr. |
| AR-021 | Accepted | D-1's no-double-PR claim was untested; a worktree fixture with an ORIGIN_FILE is cheap and closes the gap. | Edit s10.1 (D-1), step-3 and s16 test list to require a worktree+ORIGIN_FILE case asserting change_pr_publish is called exactly once. |
