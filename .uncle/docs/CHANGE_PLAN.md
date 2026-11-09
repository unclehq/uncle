# Change plan: branch and worktree policy

Omitted sections: Schema/persistence (one marker file only); Concurrency (no new shared state); Migration (none); Feature flag (none beyond existing WORKFLOW_WORKTREE); Observability (stdout notices only).

Source seed: none in metadata (no `Seeded from` link, no issue number).

## 1. Selected technical approach

New sourced bash library `scripts/lib/run-policy.sh` is the single decision point:

- `run_policy_kind <driver-basename|action>` -> `app|change|issue|unknown`, matching exact strings only (no prefix, case-folding or path guessing): stagegate.sh, create_app, run_app -> app; change-workflow.sh, change_request, create_change, run_change -> change; from-issue.sh, github_issue -> issue; anything else, including empty, absent or an unset UNCLE_STARTUP_ACTION -> unknown. `unknown` behaves exactly as today: it never skips worktree creation as `app` does, and no preflight or branch guard runs for it.
- `run_policy_worktree_wanted <kind>` -> false for `app`.
- `run_policy_app_preflight` -> refusal rules (BH-5, BH-6). On a repo with commits, a detached HEAD is refused as not on main: exit 1 with a message saying HEAD is detached (naming the detached commit short SHA, since there is no branch name), before any write. Skips on non-git or unborn-HEAD projects. The BH-7 notice prints whenever WORKFLOW_WORKTREE=1 is set on an app build, regardless of repo state. The BH-6 refusal message lists dirty paths in `git status` order, at most the first 10, one per line; when more than 10 exist it appends a final line `and N more` where N is the total count minus 10 (10 or fewer paths print no suffix).
- `run_policy_change_branch` -> for an in-place change run on any branch not recorded in run-branch (including a feature branch, and including when a remote exists) creates and switches to a new branch from HEAD (BH-1, BH-3). Handles detached HEAD (branches from the detached commit, including when a remote exists), exits 1 before any stage if no free name in `-2..-64` or the name fails `git check-ref-format --branch`, and exits 1 leaving the checkout unchanged if `git switch -c` fails (it carries uncommitted work, so a dirty tree alone is not a failure). Ordering with the PR engine (BH-2/BH-3 interplay): the guard runs before `change_pr_engine start`. When a remote exists, `start_build` sees the guard's non-default current branch and adopts it as `head_branch` (change-pr.sh:1376), journaling it with no second branch created. With no remote or a detached HEAD, `start_build` returns early and the guard's branch alone is used.

`worktree_auto` takes an optional 2nd arg (kind or driver/action name); for app it returns 0 printing nothing. All four launchers pass their run kind through. Drivers call the policy after `uncle_ensure_project_git` (launcher-side setup) and before any driver write: `run_policy_app_preflight` runs before `change_pr_engine start`, before the state directory or any stage output is created, and before the first stage. 'Nothing written' for a refused app start means no new files and no edits beyond what the launcher created before the driver started (including any repo init by `uncle_ensure_project_git`); the refusal path itself writes nothing.

## Decisions

| ID | Decision | Reason |
|---|---|---|
| D-1 | Change runs keep default worktree via `worktree_auto`; guard covers in-place runs | Minimal surface; worktree already means new branch; spec A2 |
| D-2 | Branch name from `change_pr_engine run-branch-name`, numbered `-2..-64` if taken (as worktree_auto does). If the derived name is empty, fails `git check-ref-format --branch`, or no free name exists in the base and `-2..-64`, `run_policy_change_branch` exits 1 before any stage and names the cause (invalid name, empty name, or names exhausted); no branch is created. A detached HEAD is branched from by the guard, with or without a remote (the engine returns early there, so no second branch arises). | Reuse existing naming; no collision with existing branches (INV-5); fails closed rather than writing to a detached or default checkout, and a failed name never leaves a half-started run (AR-022) |
| D-3 | Created branch recorded in `.uncle/workflow/run-branch`. An in-place change run on ANY branch not recorded in run-branch (main, master, or a feature branch not created for this run, with or without a remote) first creates and switches to a new branch from HEAD, which the engine adopts and records. The guard skips only when `run-branch` names an existing local branch (verified with `git show-ref --verify refs/heads/<name>`) that equals the current branch and is not the default branch (D-5); otherwise the file is ignored. A `worktree-owned` marker or change-pr journal is honored only when the current branch is not the default branch; on the default branch no run-branch file, marker or journal ever suppresses the guard. A marker naming a missing branch or a branch other than the current one is ignored. | Implements 'unless already on a branch created for it'; resume-safe; a pre-existing feature branch is never adopted as the run branch, and stale, planted or reused-name markers cannot keep a run on main (INV-3/AC-1/BH-1) |
| D-4 | `run_policy_change_branch` runs `git check-ref-format --branch <name>`, rejects a name with a leading '-' or an empty name, then calls `git switch -c -- <name>` (carries uncommitted work). A rejected name or failed switch exits 1 naming the cause, before any stage. Skip with message on unborn HEAD or non-git. App preflight (BH-5/BH-6) is likewise skipped on non-git or unborn-HEAD projects, with or without WORKFLOW_WORKTREE=1; the BH-7 notice is independent of repo state and still prints whenever WORKFLOW_WORKTREE=1 on an app build. | Branch names derive from untrusted brief/issue text via run-branch-name, so they are validated and option parsing is ended with `--`; `uncle_ensure_project_git` owns repo creation, so nothing to branch from otherwise |
| D-5 | `main` = local branch `main`; `master` counts as main only when no local `main` exists. An app build on a repo with commits and a detached HEAD is refused as not on main (exit 1, before any write); the message says HEAD is detached and names the detached commit (short SHA). A linked worktree whose HEAD is on main is treated like any checkout (same refusal and dirty rules). | Stock `git init` repos; A1. A detached HEAD is not on any branch, so it cannot be on main; BH-5 'names current branch' has no branch to name, so the commit is named instead. No special-casing of linked worktrees keeps one rule. |
| D-6 | Dirty check = `git status --porcelain -z --untracked-files=all`, parsed NUL-delimited (so spaces, newlines and renames are handled exactly; a renamed or staged entry counts by its destination path). Staged, unstaged and untracked entries all count as uncommitted; ignored files do not (porcelain omits them). Exclusions match exact paths only and apply to untracked (`??`) entries only: anything beneath `.uncle/`, top-level `REQUIREMENTS.md`, top-level `CHANGE_REQUEST.md`. A modified, staged, deleted or renamed tracked file at those paths (e.g. a committed `.uncle/docs/CHANGE_REQUEST.md`) counts as uncommitted. Any other change, including `.gitignore`, is reported. The same rule applies to a checkout left by a completed or archived earlier run (state file archived): untracked or uncommitted earlier-build source is dirty; committed files are clean. The BH-6 message lists the first 10 paths in `git status` order, then `and N more` when more than 10 remain; paths are printed with control characters stripped. | Uncle writes only those paths as new untracked files before start; a tracked edit there is the user's work (AR-004, AR-015). `-z` and exact matching remove quoting ambiguity so tests can assert the exact message, and stripping control characters prevents terminal-control injection from hostile filenames. |
| D-10 | A directory with a `worktree-owned` marker (legacy owned app worktree) is not preflighted and is not refused; app preflight on any other checkout, including a finished run's checkout whose state file was archived, is evaluated by the D-6 dirty rule and the D-5 main rule | Closes AR-008: legacy in-flight runs unaffected (BH-11) while leftovers from finished runs get one consistent rule |
| D-7 | App preflight runs only when `$STATE_FILE` is absent (an unparseable `$STATE_FILE` is ignored and treated as absent) and no valid `worktree-owned` marker exists, and only on a git project with a born HEAD (non-git and unborn-HEAD projects skip it, since there is nothing to compare against). A marker is valid only if it sits in a linked worktree (git-dir differs from git-common-dir) whose current branch is an existing local non-default branch; an invalid or planted marker is ignored and preflight runs. | Resume and legacy in-flight runs unaffected (BH-10, BH-11) without letting a stale or planted file bypass the refusal; edge states (non-git, unborn HEAD) follow one combined rule |
| D-8 | The 'worktree not used' notice is printed by the stagegate driver only, once, and only when `WORKFLOW_WORKTREE` is exactly `1` in the driver's environment on a fresh app start (no $STATE_FILE, no worktree-owned marker). Unset, `0`, and resume print nothing. Launchers (shell, TUI, headless, `--worktree`, `UNCLE_PROJECT_ROOT_LOCKED`) never print it; they only skip worktree creation, and the driver reads the same environment variable regardless of which launcher ran. | Every launcher path reaches the driver exactly once, so one print site avoids duplicates; keying on the variable alone makes the condition identical across launchers, and the notice answers an explicit request so it stays silent for defaults and resumed runs (BH-7, BH-11). |
| D-9 | `from-issue.sh` and `home_actions.py` are not edited | Existing refusal for `--new --worktree` already plain; prompt-only change for home agent |

## 2-3. Alternatives and preference
A) Policy inside each launcher: rejected (4 copies, violates one-place). B) Remove worktrees from change runs too: rejected (breaks concurrent runs, conflicts with preserve). C) Make engine `start_build` create branches without remote: rejected (touches PR engine, widens blast radius). Selected approach reuses existing branch machinery and touches no PR logic.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Constraints | AC-9 | Never delete/force-modify branches/worktrees | New code only `git switch -c`, no delete/-f | Safety | CAP-GIT | CODING |
| R-2 | USER | CHANGE_REQUEST Constraints | AC-6 | Gates not weakened | No edits to gate code | Scope | CAP-GIT | CODING |
| R-3 | USER | CHANGE_REQUEST Constraints | AC-7 | Policy in one place | run-policy.sh | INV-1 | CAP-GIT | CODING |
| R-4 | USER | CHANGE_REQUEST Constraints | AC-4 | Refuse off-main/dirty/detached-HEAD with reason | run_policy_app_preflight, called before any driver write (state dir, markers, stage output); refuses off-main, dirty, or detached HEAD with exit 1 and a message stating the reason (for detached HEAD, that HEAD is detached) | BH-5/6 | CAP-GIT | CODING |
| R-5 | PLATFORM | CLAUDE.md signing rules | AC-1..5 | Test fixtures never sign or use user's git config | `-c commit.gpgsign=false`, `--no-gpg-sign`, isolated HOME/GIT_CONFIG | Signing policy | CAP-GIT | CODING |
| R-6 | DESIGN | Decision D-7 | AC-6 | Resume unaffected; stale or planted markers never bypass refusal or guard; regression runs deterministic | skip only when a valid state file or validated marker exists (D-3, D-7); UNCLE_RUN_POLICY=off skips app preflight and change guard (legacy suites get it from shared runners) | Compat | CAP-GIT | CODING |

Runner/config binding: bash + python3 + git on PATH (observed: scripts/run-shell-tests.sh, run-python-tests.sh exist). Feasibility evidence: inspected symbols `worktree_auto` (worktrees.sh:292), `uncle_ensure_project_git` (project-git.sh:3), `start_build` (change-pr.sh:1342). No LIVE_VERIFICATION needing credentials; all checks are local fixtures.

## 4. Components to modify / 5. Not to modify
See change-impact table. Not modified: `scripts/from-issue.sh`, `scripts/lib/worktree-merge.sh`, `scripts/lib/change-pr.sh`, `scripts/lib/worktree_runs.py`, `scripts/lib/home_actions.py`, stage and gate code, existing tests.

## 6-8. Data flow, state, interfaces

Launchers -> `worktree_auto <root> <kind>` -> `run_policy_*`. State: new file `.uncle/workflow/run-branch` (branch name). Interface: `worktree_auto` gains an optional kind argument. Kind semantics: only the exact string `app` (or driver/action names that `run_policy_kind` maps to app) suppresses worktree creation. An absent, empty or `unknown` kind keeps today's behavior and is never treated as app, so existing callers and `worktree-auto-seed-test.sh` stay valid. `run_duties.prepare_worktree(..., kind=None)` likewise keeps today's behavior for None or unrecognized kinds and returns None without creating anything only for kind `app`. To keep INV-2 true for every real app start, each launcher resolves the kind explicitly: TUI passes `create_app` for workflow_idx 0 and `change_request` for 2; `uncle_headless.py` passes `UNCLE_STARTUP_ACTION`, and when that variable is unset derives the kind from the driver basename in `args` (stagegate.sh -> app). The shell launcher passes the driver basename. A test asserts that an app start via each launcher creates no worktree, and that absent/unknown kind still creates one.

## 12. Error and recovery
Refusals exit 1 before writes; a failed `git switch -c` exits 1 and leaves the checkout as found. Re-running after fixing the cause is safe.

## 14. Rollback plan
Revert the commit. Branches created by runs and `.uncle/workflow/run-branch` are inert; nothing is deleted.

## 16-17. Automated and regression test strategy

New `scripts/tests/run-policy-test.sh` (fixtures in temp repos, signing disabled per R-5): AC-1,2,3,4,5,8,9, including a stale-marker case: run-branch, `worktree-owned` marker and change-pr journal present while on main must still produce a new branch (INV-3), and a run-branch naming a nonexistent or non-current branch is ignored. New `scripts/tests/run-policy-test.py`: `prepare_worktree` with app kind returns None and creates nothing, change kind unchanged; launchers delegate (AC-7). Regression: existing `worktree-auto-seed-test.sh`, `worktree-run-test.sh`, `worktree-branch-test.py`, `early-branch-test.py`, `project-git-test.py` must pass untouched; full runners via baseline commands. Defect injection: the tests fail if app kind still creates a worktree or the guard is removed, or if a marker on main suppresses the guard.

- App preflight: detached HEAD with commits (including detached at main's tip) exits 1, message says HEAD is detached and includes the abbreviated commit, nothing written beyond the pre-driver snapshot (full file inventory, hashes, HEAD, branches, index identical).
- Master-only repo passes; repo with both main and master while on master refuses; linked worktree on main treated like any checkout; non-git and unborn-HEAD skip preflight, including with WORKFLOW_WORKTREE=1 (notice still prints).
- Dirty check: modified tracked, staged, untracked, ignored (clean), staged rename, path with spaces, path with newline/ESC (no raw control characters in message), tracked REQUIREMENTS.md and tracked .uncle/docs file modified (refuse) versus the same untracked (pass). 12 dirty paths: stdout is the first 10 in git status order then 'and 2 more', exit 1.
- Completed-run checkout: committed .uncle/docs plus archived state passes; untracked prior-build source refuses; worktree-owned legacy marker skips preflight; stale/planted markers (nonexistent or non-current run-branch, worktree-owned on main, unparseable state file) never bypass refusal or guard.
- Change guard: feature branch not in run-branch with remote and WORKFLOW_WORKTREE=0 ends on a new branch differing from the starting branch; detached HEAD with and without remote creates a branch, preserves uncommitted work, original commit is its parent; stubbed run-branch-name returning leading-dash, invalid ref and empty name exits 1 before any stage with no branch created; names base and -2..-64 all taken exits 1 naming the cause; guard then change_pr_engine start with a remote: exactly one new branch, journal head_branch equals guard branch, original main ref unchanged.
- Kind handling: run_policy_kind near-miss strings (case variants, trailing whitespace, path prefixes) return unknown; worktree_auto and prepare_worktree with None, empty and unknown kind keep today's behavior (create a worktree); headless with UNCLE_STARTUP_ACTION unset maps to a defined kind from the driver basename.
- BH-7 notice matrix on fresh app start: =1 prints once; =0 and unset print nothing; =1 on resume prints nothing; =1 with UNCLE_PROJECT_ROOT_LOCKED=1 prints once.

## 18. Manual verification

In a scratch repo: `uncle` with REQUIREMENTS.md on clean main, check `git worktree list`/`git branch` before and after; repeat on a feature branch (refusal) and with an edited tracked file (refusal); run a change request with `WORKFLOW_WORKTREE=0` and check `git branch --show-current`.

M-5: in a scratch repo, complete or archive an app build (state file archived), leave uncommitted source from it, and run `uncle` again: expect a dirty refusal listing those paths. Commit them on main and rerun: expect it to proceed. Then in a legacy `worktree-owned` directory, expect no preflight refusal.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/run-policy.sh` (new) | Policy functions | INV-1 | Low | run-policy-test.sh |
| `scripts/lib/worktrees.sh` | `worktree_auto` kind arg, app returns early | BH-4 | Medium | worktree-auto-seed-test.sh, run-policy tests |
| `scripts/stagegate.sh` | Source policy; preflight + notice after `uncle_ensure_project_git` | BH-5..7 | Medium (driver fixtures) | run-policy-test.sh, driver suites |
| `scripts/change-workflow.sh` | Branch guard before `change_pr_engine start` | BH-1 | Medium | run-policy-test.sh (incl. detached HEAD with and without remote, name exhaustion, switch failure), driver suites |
| `uncle` | Pass `${1##*/}` to worktree_auto | AC-7 | Low | run-policy-test.sh |
| `uncle_tui.py` | Pass kind in `_enter_run_worktree` | AC-7 | Low | run-policy-test.py |
| `scripts/lib/run_duties.py` | `prepare_worktree` kind param | AC-7 | Low | run-policy-test.py |
| `scripts/lib/uncle_headless.py` | Pass startup action as kind | AC-7 | Low | run-policy-test.py |
| `docs/worktrees.md`, `scripts/README.md`, `prompts/home-agent.md` | Policy text | BH-12 | None | run-policy-test.sh grep |
| `scripts/tests/run-policy-test.sh`, `run-policy-test.py` (new) | New tests | AC-1..9 | None | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1,2 (in-place change run on main or a non-run feature branch gets a new branch, remote or not) | BH-1, 3 | INV-3 | change-workflow.sh, run-policy.sh | run-policy-test.sh | M-4 |
| AC-3 | BH-4 | INV-2 | worktrees.sh, launchers | run-policy-test.sh/.py | M-1 |
| AC-4 | BH-5, 6, 10 | INV-4 | stagegate.sh | run-policy-test.sh: snapshot file hashes and path inventory (including untracked, excluding .git internals) just before invoking the driver; run app build on a detached HEAD and assert exit 1, a message saying HEAD is detached, and that the post-refusal inventory and hashes are identical to the pre-driver snapshot (no `.uncle/workflow` or other new/edited paths) | M-2, M-3 |
| AC-5: With `WORKFLOW_WORKTREE=1` on a fresh app start, no worktree is created and the stagegate driver prints the 'worktree not used' notice once; with `WORKFLOW_WORKTREE` unset or `0`, or on resume, the notice is not printed. | BH-7 | INV-2 | stagegate.sh | run-policy-test.sh: notice printed once for fresh app start with WORKFLOW_WORKTREE=1; absent for =0, unset, and resume | M-1 |
| AC-6 | BH-2, 8, 9, 11 | INV-5, 6 | untouched | existing suites (with UNCLE_RUN_POLICY=off exported by the shared runners), run-policy-test.sh opt-out case | - |
| AC-7 | all | INV-1 | launchers | run-policy-test.py | - |
| AC-8 | BH-12 | - | docs | run-policy-test.sh | - |
| AC-9 | - | INV-5 | run-policy.sh | run-policy-test.sh | - |

Not a bug fix; BH-4/BH-1 tests are the 'fail before, pass after' tests. BH-2/BH-3 interplay expected outcome (risk s15.1.r2): the guard's new branch is the current non-default branch when `start_build` runs, so the engine adopts it as head_branch and creates no second branch; for an in-place run on a pre-existing feature branch the guard still branches first, so the engine adopts the new branch, not the feature branch. Interplay cases (feature branch with remote, main with remote) live in run-policy-test.sh. Additional BH-1 cases in run-policy-test.sh: detached HEAD with a remote creates a branch; all names `-2..-64` taken exits 1 before any stage and leaves the checkout unchanged; failing `git switch -c` exits 1 and leaves the checkout unchanged.

## Implementation sequence

1. Policy library (CAP-GIT, R-1,3,4,6; decisions D-2..D-10). run-policy.sh solely
   all skip conditions (state file, validated worktree-owned marker, archived state, run-branch/journal validation per D-3/D-7/D-10), the dirty-check evaluation and BH-6 message formatting, branch-name validation (, leading-dash rejection, ), name exhaustion handling, writing , and the UNCLE_RUN_POLICY=off check.  adopts the guard's branch unchanged; change-pr.sh stays unowned. Steps 5 only calls the policy functions and propagates exit 1; it duplicates no condition
   Owns: `scripts/lib/run-policy.sh`
2. `worktree_auto` kind argument; app returns early
   Owns: `scripts/lib/worktrees.sh`
   Depends on: 1
3. Shell launcher `uncle` passes driver basename
   Owns: `uncle`
   Depends on: 2
4. Python launchers pass kind (independent files, same contract): TUI passes the action; `prepare_worktree` takes `kind=None` (None/unknown = today's behavior, `app` = return None); `uncle_headless.py` passes `UNCLE_STARTUP_ACTION`, falling back to the driver basename when unset, so an app start never creates a worktree
   Owns: `uncle_tui.py`, `scripts/lib/run_duties.py`, `scripts/lib/uncle_headless.py`
   Depends on: 2
5. Drivers call policy: stagegate preflight/notice, change-workflow branch guard. Both calls are skipped, with one notice line, when UNCLE_RUN_POLICY=off (exact match only); the shared test runners export it for legacy suites.
   Owns: `scripts/stagegate.sh`, `scripts/change-workflow.sh`
   Depends on: 1
6. Tests (written to the step 1 function contract); the shared runners scripts/run-shell-tests.sh and scripts/run-python-tests.sh export UNCLE_RUN_POLICY=off for legacy suites. Test matrix is in section 16-17.
   Owns: `scripts/tests/run-policy-test.sh`, `scripts/tests/run-policy-test.py`, `scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh`
   Depends on: 1
7. Docs and prompt
   Owns: `docs/worktrees.md`, `scripts/README.md`, `prompts/home-agent.md`
8. Run both baseline commands; record deviations
   
   Step IDs map to decisions: S1 D-2..D-7; S2 D-1; S5 D-7, D-8.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 2, 3, 4, 5, 6, 7

## 21. Scope cuts under time pressure
Cut first: python launcher test (keep shell test), README detail, TUI wording. Never cut: app preflight, change branch guard, INV-2 test.

## 22. Risks and unresolved questions

| Risk | Mitigation |
|---|---|
| `main` vs `master` ambiguity | D-5 |

Guard/engine interplay (BH-2/BH-3): when the guard has created and switched to branch B on a repo with a remote, the engine adopts B as head_branch and creates no second branch; the journal's head_branch and original_branch both equal B, and B equals the contents of .uncle/workflow/run-branch. run-policy-test.sh asserts this with a remote fixture: exactly one new branch exists after start, and head_branch equals the guard's branch. A no-remote fixture asserts the guard's branch is used and no journal is written.

Existing driver suites (about 50) run stagegate.sh and change-workflow.sh in git fixtures that may be off main, dirty, or have commits, so the new app preflight and change-run branch guard could change their results. Decision: both are skipped when the environment variable UNCLE_RUN_POLICY=off (exact string; any other value, or unset, leaves the policy active). The skip prints one line 'Run policy disabled by UNCLE_RUN_POLICY=off' and changes nothing else; the worktree decision for app kind (INV-2) is not affected by the opt-out. Fixture rule: legacy suites get the variable exported once by the shared runners scripts/run-shell-tests.sh and scripts/run-python-tests.sh, so no individual test, fixture or expected result is edited. The new run-policy tests explicitly unset it and include a case proving the opt-out skips only preflight and guard. If a runner is a protected verification path and cannot be changed without renewed authority, record this in IMPLEMENTATION_NOTES.md and stop rather than weaken the policy or edit a test. Step 8 runs both baseline suites and any remaining policy-caused failure must be listed there with its cause.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan left app builds on a detached HEAD undefined; refusing as not on main is consistent with BH-5. | D-5 states detached HEAD on an app build is refused naming the detached commit; run_policy_app_preflight item (s1.2.i3) updated to match. |
| AR-002 | Accepted | BH-1 and the engine's adopt-non-default-branch rule conflict for an in-place run on a feature branch; one rule is needed. | D-3, s1.2.i4, s12.1.r1 and s12.2 now say an in-place change run on any branch not recorded in run-branch gets a new branch from HEAD, remote or not, and the engine adopts it. |
| AR-003 | Accepted | BH-7 and D-8 left WORKFLOW_WORKTREE=0, unset and resume undefined; a single explicit rule makes the notice testable. | D-8 now states the notice prints only for explicit WORKFLOW_WORKTREE=1 on a fresh app start; AC-5 test expectations updated to match. |
| AR-004 | Accepted | D-6 left untracked, ignored, staged entries and over-10 output undefined, so tests could not assert the BH-6 message. | D-6 now defines counting rules (untracked count, ignored do not, staged count) and the first-10-then-'and N more' output. |
| AR-005 | Accepted | Combined edge states for app preflight (non-git, unborn HEAD, master-only, linked worktree) were not settled in one rule. | Edit D-5 and D-7 in the Decisions table to state the combined edge-state rule. |
| AR-006 | Accepted | Preflight must precede driver writes so INV-4 and AC-4 are testable; 'nothing written' needs a precise definition. | Edit s1.3 ordering, R-4 mechanism and AC-4 requirement/tests to run preflight before driver writes and define 'nothing written' against a pre-driver snapshot. |
| AR-007 | Partially accepted | Real ordering gap: start_build adopts any non-default current branch (change-pr.sh:1376), so the interplay outcome must be stated. (1 edit(s) could not be placed in the plan and were left out.) (1 edit(s) could not be placed in the plan and were left out.) | s1.2.i4 states the engine adopts the guard-created branch as head_branch with no second branch; vague risk row s15.1.r2 replaced by an explicit interplay block in section 22. |
| AR-008 | Accepted | The dirty rule must say how completed-run leftovers and legacy owned worktrees are judged; D-6 and D-7 left that open. | D-6 and D-7 now apply one dirty rule to archived or completed-run checkouts; D-7 covers worktree-owned and manual check M-5. |
| AR-009 | Partially accepted | A 'stop' instruction leaves regression results non-deterministic; an explicit opt-out and fixture rule is needed so AC-6 can be judged. (1 edit(s) could not be placed in the plan and were left out.) (1 edit(s) could not be placed in the plan and were left out.) | Replace risk row s15.1.r1 with a decided UNCLE_RUN_POLICY=off opt-out and fixture rule; update R-6, AC-6 and step-5 to match. |
| AR-010 | Accepted | An absent or unknown kind creating an app worktree would contradict INV-2; the plan must define it, and an unrecognized kind must not be mistaken for app. | s6.1 now defines absent/unknown kind: worktree_auto and prepare_worktree keep today's behavior only for a kind that is not app, and the launchers resolve the kind from the action. |
| AR-011 | Accepted | Detached HEAD (even with a remote, where the engine returns early), name exhaustion and switch failure were unspecified; the guard must own them. | D-2 and run_policy_change_branch item state detached-HEAD handling, -2..-64 exhaustion failure and switch failure; test row s12.2 and s11.1.r4 coverage added. |
| AR-012 | Accepted | The notice condition was unstated; fixing it as an explicit =1 on an app start (never unset or =0) is cheap and makes the check testable. | D-8 now states the notice condition and the launcher-independent, driver-only printing; AC-5 row requires the notice only for WORKFLOW_WORKTREE=1. |
| AR-013 | Accepted | Branch names derive from untrusted brief/issue text, so validating them and ending option parsing before `git switch -c` is a real safety gap. | Edit D-4 so run_policy_change_branch validates with check-ref-format, rejects a leading '-', and uses `git switch -c -- <name>`; failure exits 1 before any stage. |
| AR-014 | Accepted | Plain porcelain output is ambiguous for odd filenames and BH-6 prints paths, so NUL-delimited parsing and control-character stripping are needed. | Edited D-6 to parse `git status --porcelain -z` and print paths with control characters stripped. |
| AR-015 | Accepted | Path-only exclusion would let a modified tracked file under .uncle/, REQUIREMENTS.md or CHANGE_REQUEST.md pass as clean, since a merged run can commit them. | D-6 now applies the exclusions to untracked entries only; tracked modifications at those paths count as uncommitted. |
| AR-016 | Accepted | Markers in the working tree can be stale or planted, so existence alone must not bypass the guard or preflight. | D-3 and D-7 now validate markers (run-branch must name an existing local non-default branch equal to the current branch); R-6 updated to match. |
| AR-017 | Accepted | Behavior of kind `unknown` was unspecified; INV-2 must not be bypassed or over-applied by env-derived names. | Section 1: run_policy_kind matches exact strings only; unknown behaves as today and never skips worktree creation as app. |
| AR-018 | Accepted | Real gap: app builds on non-git/unborn-HEAD repos with WORKFLOW_WORKTREE=1 were unspecified; the rule is simple and consistent with D-4. | Edited D-4, D-7 and s1.2.i3 to state preflight skips on non-git/unborn HEAD and the BH-7 notice prints whenever WORKFLOW_WORKTREE=1 on an app build. |
| AR-019 | Accepted | D-6 left untracked, ignored, renamed, space-containing and tracked-excluded entries ambiguous, so tests could not assert one result. | D-6 now defines how each entry class counts, using NUL-delimited porcelain, exact top-level exclusion matching and no exclusion for tracked files. |
| AR-020 | Accepted | BH-5 assumes a current branch name; a detached HEAD on an app build has none and was undefined. | Edit s1.2.i3 and R-4 so app preflight refuses a detached HEAD with exit 1 and a message saying HEAD is detached; AC-4 test row covers it. |
| AR-021 | Accepted | A stale or planted marker on the default branch could otherwise let a change run stay on main, violating INV-3/AC-1. | D-3 now skips the guard only when the current branch equals run-branch, is an existing local branch, and is not the default branch; s9.1 adds a test. |
| AR-022 | Accepted | Exhausted names and empty or invalid derived names were unspecified; failing before any stage with a named cause is safe and cheap. | Decision D-2 now fails with exit 1 before any stage, naming the cause, when no free name exists in -2..-64 or the name is empty or fails check-ref-format. |
| AR-023 | Accepted | BH-6 left path order and overflow output unspecified, so tests could not assert the refusal message. | Section 1 run_policy_app_preflight item now fixes path order (git status order), a 10-path cap, and an 'and N more' suffix. |
