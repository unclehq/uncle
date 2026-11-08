# Change plan: `uncle --audit [BRANCH]`

Omitted sections: Schema/persistence (none); Migration (none); Concurrency beyond lock (see 11); Observability (stdout summary only); Feature flag (additive flag is the containment)

## 1. Selected technical approach

New bash helper `scripts/audit-command.sh` that validates preconditions, sets the target checkout's state to `FINAL_AUDIT`, runs the existing driver there, then prints verdict class and `FINAL_AUDIT.md` path. The helper always runs `$ROOT/scripts/change-workflow.sh` from the install dir (with only the working directory set to the target checkout) and never a `change-workflow.sh` found in the target checkout, whose content is branch-controlled; there is no env override for the driver path. The target directory is derived only from `git worktree list --porcelain` of the caller's repository, realpath-resolved, and must exist and contain a `.uncle` directory owned by the current user; otherwise the helper refuses. `uncle` parses `--audit [BRANCH]` in its flag loop (records `UNCLE_AUDIT=1`, `UNCLE_AUDIT_BRANCH`) and dispatches to the helper after mode resolution (`UNCLE_UNATTENDED` exported, `uncle:~381`) and before the TUI/noui branches (`uncle:~420`). The `--audit` path skips upgrade checks and any other pre-dispatch startup steps, never reads stdin, and never starts the TUI. If `.uncle/workflow/audit-verdict` is absent or older than the run, the summary prints `verdict: unknown` and the driver's status is still returned.

## 2. Alternatives considered
| Alt | Verdict |
|---|---|
| A. Add `--audit` option inside `change-workflow.sh` | Rejected: edits the driver the request forbids touching |
| B. Launcher early-exit exec at flag parse like `--runs` | Rejected: runs before mode resolution so `--attended` is lost |
| C. Helper script + post-mode dispatch (selected) | Smallest surface, reuses driver unchanged |

## 3. Why preferred
Auditor behavior (I-3) is untouched; mode flags work; matches existing launcher conventions (helper in `scripts/`, tests via `UNCLE_RUNTIME_ROOT`).

## 4. Exact components to modify
See change-impact table.

## 5. Not to modify
`scripts/change-workflow.sh`, `scripts/stagegate.sh`, `scripts/from-issue.sh`, `scripts/lib/audit-verdict.sh`, `prompts/**`, `uncle_tui.py`, existing tests.

## 6. Data-flow changes
args -> launcher vars -> helper -> (git checks, `worktree_branch_dir`) -> state file -> driver -> `FINAL_AUDIT.md` + `audit-verdict` -> helper prints summary.

## 7. State-transition changes

Helper writes `FINAL_AUDIT` (preserving the issue prefix convention of `state_write`, `scripts/lib/state.sh:54`) only after all preconditions pass (I-6). Stage precondition: the target's current state must be a post-implementation stage or `FINAL_AUDIT` itself (re-run accepted); any other state (planning, plan/review approval gates, implementation in progress, pending gates) is refused with `Error:` naming the state, and the state file is left untouched, so approval gates cannot be skipped. The write happens while the helper holds the checkout's driver lock via a non-blocking flock acquisition; if the lock cannot be acquired the helper refuses without writing, and if the driver then cannot take the lock the helper restores the previous state value. This closes the probe-then-write race so a live driver's state is never altered. Previous state is printed. Any branch name, path or state value the launcher or helper prints (summary and Error: messages alike) has control characters (including ESC and other C0/C1 bytes) stripped first.

## 8. Interface changes

New launcher flag `--audit [BRANCH]`. BRANCH token rule: the token after `--audit` is BRANCH only if present, non-empty and not starting with `-`. A literal empty-string token is refused with `Error:` and `$UNCLE_REFUSE_CODE`. A token starting with `-` (`--attended`, `-x`) is never BRANCH: it parses as no BRANCH (current branch) and falls to the existing handler for that token (a single-dash token hits the existing `Unknown argument` refusal); the option-like BRANCH refusal applies to the `--audit=--x` form. The word `verify` directly after `--audit` is taken as BRANCH (not the early-exit verifier); a second positional after BRANCH hits the existing `Unknown argument` error path (`$UNCLE_REFUSE_CODE`). Exclusivity: `--audit` is added to the existing pre-scan exclusivity count (`uncle:~217-227`, alongside `--application`, `--issue`, `--change-request`), so any combination with them (including `--issue --audit`) is refused with `Error:` and `$UNCLE_REFUSE_CODE` (2 under --noui, otherwise 1) before any stdin read; the existing literal `exit 1` paths for the three pre-existing options are unchanged. Early-exit flags (`-h/--help`, `verify`, `--runs`, `--performance`, which exec inside the parse loop) act in argument order as today: `--audit` appearing after one is never parsed; `--audit` appearing before one is refused as a combination (`Error:`, `$UNCLE_REFUSE_CODE`) before any exec. Branch resolution: BRANCH is resolved via `worktree_branch_dir` (target dir only from `git worktree list --porcelain`); zero or multiple matching worktrees are refused with an `Error:` naming the cause; BRANCH equal to the current branch audits the current checkout. Git never receives BRANCH as a bare argument or via `check-ref-format --branch` (which expands `@{-N}`): all git calls use the fully qualified `refs/heads/<name>` after a `--` separator. A target whose state is already FINAL_AUDIT is accepted and re-run. Exit: refusals `$UNCLE_REFUSE_CODE`. After the driver runs: if `.uncle/workflow/audit-verdict` is missing, print `verdict: UNKNOWN` and exit `$UNCLE_REFUSE_CODE`; otherwise exit with the driver's status. Mode: the helper passes mode only via the exported `UNCLE_UNATTENDED` environment variable; it adds no driver CLI flags (`--attended`/`--unattended` are not forwarded to `change-workflow.sh`), and an unset value means the driver default.

## 10. Compatibility

Purely additive; usage and hint list gain one entry. Decision D-1: the token after `--audit` is BRANCH iff present, non-empty and not starting with `-`. A token starting with `--` after `--audit` is never a BRANCH and is handled by the existing flag handlers, so `uncle --audit --attended` parses as no BRANCH; `uncle --audit -x` leaves `-x` to the existing unknown-argument handler; `uncle --audit ''` is refused; `uncle --audit verify` is refused as an extra positional; only `--audit=--x` is refused as an option-like BRANCH. Tests assert each of these forms.

## 11. Concurrency

Decision D-2: before any state write the helper refuses via a non-blocking flock probe on the target checkout's driver.lock, exiting $UNCLE_REFUSE_CODE with a message naming the lock; the probe is not left to the driver (reusing the probe in `scripts/lib/worktrees.sh` `worktree_run_locked` or `plan-executability.py` where it exposes a non-blocking test). The probe runs on the validated, realpath-resolved target directory only (see section 1). The driver's own lock remains the final guard. The AC-4 lock test holds the lock in a background process and asserts the helper's refusal code and message and that state is untouched.

## 12. Error and recovery
All refusals precede any write. If the driver stops (override gate, failure) the state is left to the driver's normal resume path; `./scripts/change-workflow.sh` resumes.

## 14. Rollback
Revert the commit. No data migration; leftover FINAL_AUDIT state is harmless.

## 16. Automated-test strategy

New `scripts/tests/audit-command-test.sh` (named `*-test.sh`, collected by `run-shell-tests.sh`). Fixtures: temp git repo with `commit.gpgsign=false`, `tag.gpgsign=false`, `--no-gpg-sign` on every commit; a copy of `uncle` plus `scripts/lib` and a stub `scripts/change-workflow.sh` in a temp install dir with an empty `uncle_tui.py`, selected via `UNCLE_RUNTIME_ROOT`; `UNCLE_SKIP_UPGRADE=1` set as a safety net (the audit path itself skips upgrade checks; a case asserts no upgrade step runs, stdin is not read, and the TUI is not started). Stub records cwd, args, `UNCLE_UNATTENDED`, and the state it found, and may write a verdict file. Cases map to AC-1..AC-4, plus: a verdict file absent or older than the run prints `verdict: unknown` and the exit status equals the driver status. A sanitization case uses a branch name or state value containing an ESC byte and asserts no control characters appear in stdout/stderr (AR-017). Defect injection (AC-6): one mutant per AC-4 refusal, each applied to a temp copy and removing only that single check; the owning file is the one holding the check (argument-shape, exclusivity and home-agent refusals in `uncle`; git, state and lock refusals in `scripts/audit-command.sh`). Each mutant must make its matching refusal test fail, and the mutant run is recorded per refusal; an unmatched pass or a failure in an unrelated test does not count. A mutant that strips the output sanitizer must fail the sanitization case.

- State-stage cases (AR-002): for each mid-flight state (planning, plan/review approval gates, implementation in progress, pending gates) assert refusal with `Error:`, byte-identical state file and the stub not run; post-implementation stage and existing FINAL_AUDIT are accepted. Each has its own mutant.
- Hostile BRANCH cases (AR-013): `-x`, `--x`, `@{-1}` and empty string are refused before any git or state action; a mutant removing the leading-dash check must fail.
- Checkout-path cases (AR-014): a worktree missing `.uncle` and a branch with no worktree are refused with no state write; zero and multiple worktree matches are refused; BRANCH equal to the current branch audits the current checkout; a mutant removing the path validation must fail.
- Driver-origin case (AR-015): a decoy `change-workflow.sh` in the target worktree that fails or records; assert only the install-dir stub ran and cwd was the target.
- Lock-race case (AR-016): the stub driver exits with a lock-acquisition failure; assert the prior state file is restored byte-identically.
- Verdict cases (AR-020): stub writes verdict absent, unparsable, and non-READY with driver exit 0 and nonzero; assert `verdict: unknown` where applicable and that the exit status equals the driver's.
- Lock probe (AR-021): the probe is a self-contained non-blocking flock inside `scripts/audit-command.sh`; `worktrees.sh` and `plan-executability.py` are not edited. The test holds `driver.lock` from a background process and asserts refusal, no state write and the stub not invoked.

## 17. Regression strategy
Driver runs both baseline commands post-change (`bash scripts/run-shell-tests.sh`, `bash scripts/run-python-tests.sh`); launcher-* tests must stay green.

## 18. Manual verification
M-1: in a real finished change worktree run `uncle --audit` and confirm a fresh `.uncle/docs/FINAL_AUDIT.md` (needs live reviewer credentials: LIVE_VERIFICATION phase only, not a coding prerequisite). M-2: from another checkout run `uncle --audit <branch>`.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `uncle` | add `--audit` parsing, exclusivity check, home-agent refusal (owns argument-shape, exclusivity and home-agent refusals), post-mode dispatch, usage line, hint-list entry | entry point | Medium: flag loop and usage | launcher-* tests + new test |
| `scripts/audit-command.sh` (new) | git, state and lock refusals, branch->checkout, state write, run driver, summary (`verdict: unknown` when verdict missing; exit equals driver status) | core behavior | Low: new file | audit-command-test.sh |
| `scripts/tests/audit-command-test.sh` (new) | cases AC-1..AC-4; stub may omit the verdict file; defect injection with one mutant per AC-4 refusal in `uncle` and in `audit-command.sh` | verification | None | self |
| `scripts/README.md` | document `--audit` | docs | None | n/a |

## Restrictions
| R-ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Constraints | AC-7 | do not change auditor or existing commands | no edits to driver files; helper only | request | CAP-SHELL | CODING |
| R-2 | USER | CHANGE_REQUEST Constraints | AC-1,AC-5 | follow CLI conventions | flag in `uncle` loop, helper under `scripts/` | consistent with `--runs` | CAP-SHELL | CODING |
| R-3 | PLATFORM | CLAUDE.md signing rules | AC-6 | tests never sign | gpgsign=false + `--no-gpg-sign` in fixtures | project rule | CAP-GIT | CODING |
| R-4 | DESIGN | state-write ordering | I-6 | no write before preconditions | validate first; revisable | safety | CAP-SHELL | CODING |
Feasibility evidence: `UNCLE_RUNTIME_ROOT` override inspected at `uncle:21-23`; `worktree_branch_dir` at `scripts/lib/worktrees.sh:48`; `state_write` at `scripts/lib/state.sh:54`; runner `scripts/run-shell-tests.sh` exists. Live audit needs reviewer credentials (LIVE_VERIFICATION only; non-secret evidence: `.uncle/docs/FINAL_AUDIT.md` produced by M-1).

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | B-2, B-5 | I-4 | uncle | audit-command-test.sh help/hint cases | none |
| AC-2: `uncle --audit` audits the current checkout and prints the verdict class and FINAL_AUDIT.md path. Exit status equals the driver's, except that a missing or unparsable `.uncle/workflow/audit-verdict` prints `verdict: UNKNOWN` and exits `$UNCLE_REFUSE_CODE`; otherwise the driver status is used. | B-1 | I-6 | uncle, audit-command.sh | default-branch case, missing-verdict case: stub writes no verdict, expect `verdict: UNKNOWN` and exit $UNCLE_REFUSE_CODE, not-READY verdict with driver exit 0: exit 0, BRANCH parsing cases: empty string, `verify`, single-dash token, `--attended` as no BRANCH | M-1 |
| AC-3 | B-8 | I-7 | audit-command.sh | other-worktree case | M-2 |
| AC-4 | B-9 | I-1, I-6 | audit-command.sh | one case per refusal; argument-shape, exclusivity and home-agent cases exercise `uncle`, git, state and lock cases exercise `audit-command.sh`, empty-string BRANCH refused, --audit with verify/--runs/--performance refused, --audit combined with --application/--issue/--change-request (incl. bare `--issue --audit` with piped stdin left unread) is refused with $UNCLE_REFUSE_CODE (1 normally, 2 under --noui), existing FINAL_AUDIT state accepted and re-run, lock held by background process: helper refuses with $UNCLE_REFUSE_CODE, defect injection: one mutant per refusal in the owning file, each must fail its matching test | none |
| AC-5 | B-3, B-4, B-6, B-7 | I-3, I-4 | none | baseline commands | none |
| AC-6 | all | all | test file | defect injection: one mutant per AC-4 refusal across uncle and audit-command.sh, each failing its matching test, sanitization mutant fails the control-character case | none |
| AC-7 | B-6 | I-3 | none | git diff --stat | none |

## 20. Implementation sequence

| Step | Description | Deps | Decisions |
|---|---|---|---|

1. Helper `scripts/audit-command.sh` owns the git, state and lock refusals; every refusal leaves state untouched. Validate: git repo; BRANCH not starting with `-`; branch existence via `git show-ref --verify -- refs/heads/<name>` and `git check-ref-format refs/heads/<name>` (never `--branch`); target checkout is the current one or the match from `git worktree list --porcelain` of the caller repo (the only source of the target dir), realpath-resolved, must exist and contain `.uncle` owned by the current user; `family`==change and state present; current state is a post-implementation stage or FINAL_AUDIT, else refuse; non-blocking driver-lock probe (refuse if held). Then write `FINAL_AUDIT` state while holding the lock (restore the previous state if the driver cannot acquire the lock) and record the run start time. Run `$ROOT/scripts/change-workflow.sh` from the install dir (never the target checkout's copy) with cwd set to the target, conveying mode only through exported `UNCLE_UNATTENDED` (no driver CLI flags added; unset means driver default). Summary: print the verdict class from `.uncle/workflow/audit-verdict` and the `.uncle/docs/FINAL_AUDIT.md` path; if the verdict file is absent, unparsable, or older than the run start print `verdict: unknown`. Exit status always equals the driver's status, never altered by the verdict (including a not-READY verdict or missing file).
   Owns: `scripts/audit-command.sh`
2. Launcher wiring in `uncle` owns the argument-shape, exclusivity and home-agent refusals (git, state and lock refusals are not duplicated here; they live in `scripts/audit-command.sh`). `--audit` case in flag loop with optional BRANCH: the next token is BRANCH iff it is non-empty and does not start with `-`; an empty string is refused; `verify` is taken as BRANCH and any second positional hits the Error path. Add `--audit` to the exclusivity pre-scan loop (`uncle:~219-223`) so combinations with `--application`/`--issue`/`--change-request` are refused before any stdin read, and the in-loop startup-action mutual-exclusion check also covers `--audit`; both exit `$UNCLE_REFUSE_CODE` (2 under --noui). Early-exit flags (`--help`, `verify`, `--runs`, `--performance`) act in argument order: before `--audit` they act as today and `--audit` is never parsed; after `--audit` (as flags) the combination is refused with `$UNCLE_REFUSE_CODE`. `UNCLE_HOME_AGENT` marker check, post-mode dispatch (the audit path skips the upgrade check, never reads stdin, never starts the TUI), usage text, hint list.
   Owns: `uncle`
   Depends on: 1
3. Tests `scripts/tests/audit-command-test.sh` per section 16, including the case list that follows it. Run it and the launcher-* tests. Defect injection applies mutants only to copies under a temp directory, one per AC-4 refusal in the owning file (`uncle` or `scripts/audit-command.sh`), each required to fail its matching test with results recorded; this step never edits files owned by steps 1 and 2. The lock test holds driver.lock from a background process.
   Owns: `scripts/tests/audit-command-test.sh`
   Depends on: 1, 2
4. Docs line in `scripts/README.md`.
   Owns: `scripts/README.md`
   Depends on: 2

## 21. Scope cuts under time pressure

Cut first: README line, then BRANCH argument for other worktrees (keep current-branch default), then lock probe (driver lock still guards). Never cut precondition-before-write ordering, tests for refusals, or the per-refusal mutants in either `uncle` or `audit-command.sh`.

## 22. Risks and unresolved questions
- Existing tests may match exact usage text: grep `scripts/tests` for usage assertions before editing; if one conflicts, stop and record in IMPLEMENTATION_NOTES.md rather than editing the test.
- Non-blocking lock probe helper: confirm during step 1; fallback is relying on the driver's lock refusal (message surfaces to the user).
- Stub-driver test does not exercise the real auditor; covered by M-1.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan forwards a mode flag to a driver it does not modify; mode must travel only via the environment. | Edit s8.1 and step-1 so mode passes only through exported UNCLE_UNATTENDED, with no driver CLI flags. |
| AR-002 | Accepted | Overwriting a mid-flight state with FINAL_AUDIT could skip approval gates, so a stage precondition is needed. | Edit s7.1 and step-1 to refuse unless state is post-implementation or FINAL_AUDIT, leaving state untouched. |
| AR-003 | Accepted | Exit contract needed a rule for missing verdict; refusal code on UNKNOWN is a clear, testable choice. | Section 8 and AC-2 now state: missing audit-verdict prints UNKNOWN and exits $UNCLE_REFUSE_CODE, otherwise driver status. |
| AR-004 | Accepted | BRANCH parsing edge cases must be fixed so tests are deterministic. | Section 8, section 10 D-1 and step 2 now define BRANCH as next token iff non-empty and not starting with '-'; empty refused; 'verify' refused as extra positional. |
| AR-005 | Accepted | Zero, multiple, and current-branch cases were undefined and need a deterministic rule. | Step 1 and s8.1 define resolution via worktree_branch_dir: zero/multiple matches refused, current branch audits current checkout. |
| AR-006 | Accepted | The pre-scan counts only three options, so --audit could reach a stdin read before refusal. | Step 2 and s8.1 add --audit to the pre-scan exclusivity loop, refusing combinations before any stdin read. |
| AR-007 | Accepted | The pre-scan at uncle:217-227 counts only three flags, and a bare `--issue --audit` would otherwise read stdin first. | s8.1 and step-2 state --audit joins the pre-scan exclusivity count so combinations are refused before any stdin read. |
| AR-008 | Accepted | Existing exclusivity exits use literal 1; the new --audit combination must use one stated code. | s8.1, AC-4 and step-2 state that combining --audit with another startup action exits $UNCLE_REFUSE_CODE (2 under --noui). |
| AR-009 | Accepted | Edge-value BRANCH parsing was unspecified; a precise token rule removes ambiguity. | s8.1 now defines BRANCH as next token only if non-empty and not starting with '-'; empty refused; 'verify' taken as BRANCH; second positional hits Error path. |
| AR-010 | Accepted | Early-exit flags exec inside the parse loop, so ordering relative to --audit must be stated. | s8.1 and step-2 state early-exit flags act in argument order; --audit after them is never parsed; --audit before them is refused as a combination. |
| AR-011 | Accepted | The plan left unstated whether upgrade checks and stdin/TUI run on the audit path. | Section 1 and steps 2 state the --audit path skips upgrade checks, never reads stdin, never starts the TUI; section 16 test sets UNCLE_SKIP_UPGRADE only as a safety net. |
| AR-012 | Accepted | Summary behavior for a missing or stale audit-verdict was undefined. | Step 1 and section 16 define: absent or older-than-run verdict prints 'verdict: unknown' and the driver status is still returned. |
| AR-013 | Accepted | Real gap: BRANCH starting with a single dash or revision syntax like @{-1} could be interpreted as a git option or expanded. | s8.1 refuses BRANCH starting with '-' and s19 step-1 requires git calls to use refs/heads/<name> after '--', never check-ref-format --branch. |
| AR-014 | Accepted | Checkout path from worktree_branch_dir was unvalidated and branch-controlled content could redirect the audit. | s1.1, s10.1 and step-1 require the target dir to come only from git worktree list --porcelain, realpath-resolved, existing, with a user-owned .uncle. |
| AR-015 | Accepted | Running a script from a branch-controlled target checkout would execute untrusted content; the install-dir driver is the only safe and consistent choice. | Section 1 prose now states the helper always runs $ROOT/scripts/change-workflow.sh from the install dir, with only the cwd set to the target. |
| AR-016 | Accepted | A probe followed by a separate state write is a check-then-act race; the write must happen under the driver lock or be restored. | Section 7 prose now requires the FINAL_AUDIT write under a held driver lock (non-blocking flock), restoring the prior state if the lock is not acquired. |
| AR-017 | Accepted | Echoed state, branch names and paths could carry terminal escapes; sanitizing is cheap and safe. | s7.1 now requires control characters stripped from every printed branch, path or state value; test added in s13.1. |
| AR-018 | Accepted | A single whole-block stub cannot prove each refusal test catches its own check. | s13.1 now requires one mutant per AC-4 refusal in both uncle and audit-command.sh, each failing its matching test; AC-6 updated. |
| AR-019 | Accepted | Refusal ownership was unstated and injection covered only the helper, so a launcher-side defect would go undetected. | Steps 1-2, AC-4 and s16 rows state refusal ownership (uncle vs audit-command.sh); s16 and s20 require one mutant per refusal in both files. |
| AR-020 | Accepted | Output and exit were undefined when the verdict file is missing or not READY; one rule settles it. | Step 1 and AC-2 specify 'verdict: unknown' for a missing or unparsable verdict and exit always equal to the driver status; s16 stub covers absent verdict. |
| AR-021 | Accepted | A deterministic lock probe is needed so the AC-4 lock refusal is testable and distinct from the driver's own refusal. | Section 11 (s10.1) now fixes a non-blocking flock probe on driver.lock with $UNCLE_REFUSE_CODE; AC-4 and step 2 text updated; test holds the lock in a background process. |
| AR-022 | Accepted | Empty BRANCH, early-exec flag combinations and existing FINAL_AUDIT state were unspecified and need explicit rules. | Section 8 (s8.1) states empty BRANCH refused, --audit with verify/--runs/--performance refused, existing FINAL_AUDIT accepted; AC-4 and step 2 updated. |
| AR-023 | Accepted | D-1 and the spec's option-like BRANCH refusal conflicted; one rule removes the ambiguity for tests. | Sections 8 and 10 now state a -- token after --audit is never a BRANCH and falls to existing handlers; the refusal applies only to --audit=--x. |
