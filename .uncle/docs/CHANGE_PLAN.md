# Change Plan (Issue 228)

Seeded from [unclehq/uncle#228](https://github.com/unclehq/uncle/issues/228).

Issue 228

Omitted sections: Schema/persistence, Migration, Concurrency, Feature flags (none apply)

## 1. Selected technical approach

Triage-then-fix per suite. Step 1 reproduces every failure on a clean checkout of main HEAD (a throwaway `git worktree`, no signing, no commit to the project) to separate host-state artifacts from real defects. Failures are judged against clean main: a failure seen only in the dirty tree is recorded in IMPLEMENTATION_NOTES.md as host-state and needs no code change. Fixes: (D-1) in both drivers parse `--help/-h/--version` before the run-policy preflight, using this argv rule: scan argv left to right; the first of `--help`, `-h`, `--version` found wins, is handled before preflight (prints and exits 0, writing no state), and all later arguments are ignored (so `--version --unattended` prints the version and `--help build` prints help). If none of those appears, including an unknown argument alone, the full run-policy preflight runs before any state write exactly as today; real-run args (e.g. `--unattended`, a build request) with no help/version flag still run preflight. (D-2) fixture isolation: attestation, early-branch, home-actions fixtures must create their own git repo and `.gitignore` rather than inherit host state; the attestation fixture writes its own `.gitignore` in two variants, one without `.uncle` and one containing `.uncle` (simulating the dirty host case), and at least one shard asserts the ignore-containing case so AC-5 is exercised; (D-3) add explicit `-c commit.gpgsign=false -c tag.gpgsign=false` and `--no-gpg-sign` to flagged fixture git calls; (D-4) for exit 127 and gates-verification-integrity, locate the missing command/ordering in the failing check, then fix product or add a prerequisite check with a clear message. Prerequisite checks fail closed: a missing tool produces a nonzero exit that names the tool, and is never reported as a pass or a skip; a suite failing on a missing prerequisite counts as FAILED for AC-8.

Argument rule for D-1 (AR-013): `--help`, `-h` or `--version` is honored before preflight only when it is the first argument (`$1`); it prints and exits 0 and writes no state. Every other form, including `--unattended --version`, `build --help`, or an unknown argument, goes through the full run-policy preflight before any state write, and is then parsed normally. Arguments after a leading help/version flag are ignored.

Host-isolation rule (AR-016): every fixture (attestation, early-branch, home-actions, worktree-run, gates-verification-integrity and the exit-127 fix) runs only in a disposable temp repo with sanitized HOME and GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM (pointed at an empty or temp file) and GPG agent env neutralized. No fix or fixture may read, write, or depend on the project checkout's real .gitignore, git config, or refs; the fixture writes its own .gitignore inside the temp repo.

## 2-3. Alternatives and rationale

Alternative: edit assertions to match behavior (rejected: forbidden). Alternative: relax run-policy (rejected: weakens SI-1). Selected approach fixes root causes minimally.

Side-effect freedom (AR-014): the help/version path prints and exits 0 before sourcing any state, creating directories, writing journals or state, creating worktrees or branches, or invoking git or agent/reviewer CLIs. A test snapshots the tree (file-hash inventory including untracked files, plus `git for-each-ref`) before and after `--help`, `-h` and `--version` for both drivers and fails on any difference.

## 4. Components to modify / 5. Not to modify
Modify per table below. Not: run-policy semantics, test assertions, `all_suites.py`.

## 8. Interface changes
None beyond `--version`/`--help` working in any tree state.

## 12. Error behavior

Worktree listing failure: keep `WorktreeListError`. The resume path (`uncle_tui.py` / `scripts/lib/worktree_runs.py`) catches it and shows a refusal message; the TUI does not raise and no state is changed. The `home-actions-test.py` fixture is repaired (made a valid repo) only if triage shows the non-repo fixture was unintended, i.e. the test itself asserts a valid-repo outcome; fixture edits change setup only, never assertions. Otherwise the product handling is fixed and the fixture is left as is. Step 1 triage records which case applies.

## 14. Rollback
Revert the change commit; no persisted state altered.

## 16-17. Test strategy

Regression tests already exist (the failing suites). Each suite that fails on clean main fails before and passes after; a suite that fails only in the dirty tree is recorded as host-state, needs no code change, and must still pass after. Command: `bash scripts/run-all-tests.sh` (from baseline). Protected paths: `scripts/tests/**`; any edit there requires a requirement-based note in IMPLEMENTATION_NOTES.md and limits to fixture setup, never assertions. A suite failing on a missing prerequisite counts as FAILED for AC-8; the change is complete only when all suites pass, otherwise the suite is listed as unresolved. The `missing prerequisite: <tool>` stderr wording and non-127 nonzero exit are checked by the message-wording check named under AC-7.

AC-5 dirty-host verification: run `python3 -B scripts/tests/attestation-statement-test.py` twice in the same session, once with the host checkout's .gitignore containing a `.uncle` entry and once with it clean. Create each condition deliberately, restoring the original .gitignore byte-for-byte afterward (hash before and after); the incidental dirty state of this worktree is not evidence. Both runs must pass, and the results are recorded in IMPLEMENTATION_NOTES.md.

## 18. Manual verification

Run `scripts/stagegate.sh --version` and `--help` in a dirty tree; confirm a real run is still refused. With a required tool removed from PATH, confirm stderr shows `missing prerequisite: <tool>` and the exit code is nonzero and not 127.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/stagegate.sh` | scan argv for --help/-h/--version before preflight: the first of these flags found anywhere in argv wins (so --help/-h wins over --version when it comes first), later args are ignored, it prints and exits 0; no flag (including unknown args alone) means full preflight unchanged; the early path performs no state write, directory creation, journal, worktree/branch creation, or git/agent CLI invocation | SB-1, SB-2 | Preflight bypass via mixed args; mitigated because only these three flags short-circuit and nothing is written | unattended-test.sh, run-policy tests, plus new before/after tree-unchanged assertion |
| `scripts/change-workflow.sh` | same argv rule as stagegate.sh: first of --help/-h/--version wins before preflight, later args ignored, otherwise full preflight; early help/version path has no side effects | SB-1, SB-2 | same | unattended-test.sh, plus new before/after tree-unchanged assertion |
| `scripts/tests/attestation-statement-test.py` | isolate fixture `.gitignore` (setup only): fixture creates its own temp repo and writes its own `.gitignore`; one shard writes a `.gitignore` containing `.uncle`, another omits it, and at least one shard asserts the ignore-containing case | SB-6 | isolation could mask a real ignore bug; mitigated by the host-isolation rule (temp repo, sanitized HOME/GIT_CONFIG_GLOBAL, never touching the project's real .gitignore or git config), by the `.uncle`-ignored shard, and by the triage decision recording any product defect it exposes | itself (both `.gitignore` variants asserted); step 1 triage records whether the product must handle a repo `.gitignore` listing `.uncle`, otherwise marks it out of scope in IMPLEMENTATION_NOTES.md |
| `scripts/tests/early-branch-test.py` and the early-branch product files named by step 1 triage (added to step 4 Owns before any edit) | fix unexpected ref creation (product or fixture per triage); each skip context snapshots `git for-each-ref` and a file-hash inventory (including untracked files) before and after, and any difference fails | SB-4 | branch semantics | early-branch-test.py (ref + file-hash before/after comparison per skip context) |
| `scripts/tests/home-actions-test.py`, `scripts/lib/worktree_runs.py`, `uncle_tui.py` | catch `WorktreeListError` in the resume path and show a refusal message without raising or changing state; repair the fixture (setup only) only if the test is meant to assert a valid repo and non-repo was unintended | SB-5 | resume behavior; a fixture change could mask a real listing failure or handling gap | itself |
| every fixture file under `scripts/tests/**` that the `supervisor-test.py` signing audit flags (initially `scripts/tests/tree-attested-final-audit-test.sh` and `scripts/tests/build-attestation-test.py`), and no others | add no-sign flags to each flagged fixture git commit/commit-tree/tag call, set repo-local gpgsign=false, and sanitize inherited git/GPG env (fixture setup only) | SB-7 | none; edits limited to fixture setup, no assertion changes | supervisor-test.py |
| `scripts/tests/worktree-run-test.sh`, gates-verification-integrity suites and their product code | fix per step 1 recorded cause and expected behavior; where a tool is missing, print `missing prerequisite: <tool>` on stderr and exit nonzero with a code other than 127; if no cause is found, leave unresolved and list it (AC-7 not met) | SB-8 | gate state machine; a prerequisite-message fix is still a red suite for AC-8 and is listed for the PR | those suites |
| `.uncle/docs/IMPLEMENTATION_NOTES.md` | record rationale per test edit, and the fail-closed prerequisite behavior for any missing tool | AC-8 | none | review |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1/2: help/version works regardless of tree state when it is the first recognized flag; mixed or real-run args (`--unattended --version`, `build --help`) still go through full preflight and write no state before it | SB-1, SB-2 | SI-1 | stagegate.sh, change-workflow.sh | unattended-test.sh (including mixed-argument cases: `--version --unattended`, `--help build`, `build --help`, `--help --version`; an unknown argument alone still refused by preflight in a dirty tree), tree-unchanged check (file-hash inventory and git for-each-ref before/after --help/-h/--version) | dirty-tree --version |
| AC-3 | SB-3 | SI-1 | run-policy | run-policy suites | refused build |
| AC-4: in skip contexts no ref, journal, or mutation is produced; detected by comparing `git for-each-ref` output and a file-hash inventory before and after each skip context, where any difference fails. | SB-4 | SI-3 | early-branch | early-branch-test.py (asserts identical for-each-ref output and file-hash inventory before/after each skip context) | none |
| AC-5: attestation-statement-test.py passes both with a host .gitignore containing `.uncle` and with a clean host .gitignore; the fixture writes its own .gitignore in each case, and at least one shard asserts the ignore-containing case. | SB-6 | - | attestation fixtures | attestation-statement-test.py (run twice with the fixture writing its own .gitignore: once containing `.uncle`, once clean; both must pass, at least one shard asserts the ignore-containing case, and triage records the product behavior or out-of-scope decision), run-all-tests.sh | none |
| AC-6: every fixture git commit, commit-tree and tag under scripts/tests/** disables signing via explicit flags and repo-local config, with inherited global git/GPG config neutralized; supervisor-test.py audits all of them and passes. | SB-7 | SI-2 | fixtures | supervisor-test.py | none |
| AC-7: for each of worktree-run, gates-verification-integrity and exit 127, step 1 records the cause and expected behavior, and the suite then either passes, or fails closed on a missing prerequisite by printing `missing prerequisite: <tool>` on stderr and exiting nonzero with a code other than 127 (never a pass or a skip). A prerequisite-failing suite still counts as FAILED for AC-8 and is listed as unresolved for the PR; a suite whose cause is not found is listed as unresolved and AC-7 is marked not met. | SB-5, SB-8 | - | see table | named suites, message-wording check: run the suite with the tool absent from PATH, assert stderr contains `missing prerequisite: <tool>` and exit code is nonzero and not 127; record in IMPLEMENTATION_NOTES.md, home-actions-test.py: worktree listing failure shows refusal, no exception, no state change | none |
| AC-8: `bash scripts/run-all-tests.sh` exits 0 reporting 0 failed and 0 skipped. A suite failing on a missing prerequisite counts as FAILED (red), so AC-8 is unmet until every suite passes; any suite still failing is listed as unresolved in IMPLEMENTATION_NOTES.md and the PR. | all | SI-4 | all | run-all-tests.sh | diff review |

## 20. Implementation sequence

## Implementation sequence

1. Triage: reproduce all failures on a clean main checkout and a dirty one; record in IMPLEMENTATION_NOTES.md which are host-state, environment, or defects. For exit 127 and gates-verification-integrity, record for each the root cause (missing command or ordering defect), the failing check, and the concrete expected behavior (e.g. a missing tool prints `missing prerequisite: <tool>` on stderr, exits nonzero other than 127, and is never a pass or skip). For early-branch (SB-4), record whether the fix is fixture or product and name every early-branch product file to change; step 4 Owns is amended with those exact paths (recorded as a deviation entry) before any edit to them. If no cause is found for a suite, list it as unresolved in IMPLEMENTATION_NOTES.md and mark AC-7 not met for it; do not guess a fix.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
2. Drivers: parse help/version before preflight.
   Owns: `scripts/stagegate.sh`, `scripts/change-workflow.sh`
3. **Signing hygiene in all flagged fixtures** — Every fixture `git commit`, `git commit-tree` and tag call in the files the `supervisor-test.py` signing audit flags (initially tree-attested-final-audit-test.sh and build-attestation-test.py) carries `-c commit.gpgsign=false -c tag.gpgsign=false` plus `--no-gpg-sign` / `--no-sign`. Each disposable fixture repo also sets repo-local commit.gpgsign=false and tag.gpgsign=false, and fixture subprocesses neutralize inherited signing config (GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM pointed at an empty file, HOME set to a temp dir, GPG_AGENT_INFO/GNUPGHOME unset). Scope is exactly the files the audit flags under scripts/tests/** and no others; supervisor-test.py is the enforcer. No unflagged file is edited; any additional flagged file is recorded in IMPLEMENTATION_NOTES.md before editing. Edits are fixture setup only and change no assertion, expected value or skip condition.
   Owns: `scripts/tests/tree-attested-final-audit-test.sh`, `scripts/tests/build-attestation-test.py`
4. Attestation, early-branch, home-actions, worktree-run, gates-verification-integrity fixes per triage; files are named in step 1 notes and limited to the files the triage identifies. Early-branch product files named in step 1 triage are added to this step's Owns (with a deviation entry in IMPLEMENTATION_NOTES.md) before any edit; no early-branch product file is edited until it is so named. Any other file outside this step's Owns list requires an IMPLEMENTATION_NOTES.md deviation entry (file, reason, requirement) written before it is edited. A fixture 'setup edit' changes no assertion, expected value, or skip condition; any edit that does is not permitted. For home-actions: catch WorktreeListError in the resume path and show a refusal with no state change; repair the fixture only if triage shows non-repo was unintended. For AC-5, run attestation-statement-test.py with a host .gitignore containing `.uncle` and again with it clean (restoring the original byte-for-byte); both must pass, and both results are recorded in IMPLEMENTATION_NOTES.md.
   Owns: `scripts/tests/attestation-statement-test.py`, `scripts/tests/early-branch-test.py`, `scripts/tests/home-actions-test.py`, `scripts/tests/worktree-run-test.sh`, `scripts/lib/worktree_runs.py`, `uncle_tui.py`
   Depends on: 1, 3
5. Full run `bash scripts/run-all-tests.sh`; append only a clearly separated results/deviations section to IMPLEMENTATION_NOTES.md (never edit the step 1 triage records). AC-8 is met only if the run exits 0 with 0 failed and 0 skipped; otherwise list each red suite as unresolved. Steps 2 and 3 are independent and may be batched.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`
   Depends on: 1, 2, 3, 4

## 21. Scope cuts

Cut first: nothing that weakens AC. A suite that fails on a missing prerequisite counts as FAILED (red) for AC-8; the change is complete only when `bash scripts/run-all-tests.sh` exits 0 with 0 failed, and AC-8 is unmet until every suite passes. If time expires, leave the suite red and list it as unresolved in IMPLEMENTATION_NOTES.md and the PR rather than skip it or report it as passing; AC-8 is then marked not met.

## 22. Risks and unresolved questions

- Exit 127 and gates-verification-integrity causes unknown until step 1; if the fix needs files outside step 4's Owns list, record a deviation entry in IMPLEMENTATION_NOTES.md before editing those files. Fixture edits are limited to setup that changes no assertion, expected value, or skip condition.
- Failures caused by this worktree's dirty `.gitignore` may vanish on clean main; documented for the PR.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | CAP | Phase |
|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Requirements | AC-8 | no weakened/skipped tests; missing prerequisites fail closed (nonzero exit naming the tool, never a pass or skip) | diff review + 0 skipped | CAP-TESTS | CODING |
| R-2 | REPOSITORY | system rules | AC-6 | no real signer | explicit no-sign flags on every fixture commit/commit-tree/tag under scripts/tests/**, repo-local gpgsign=false, sanitized global config/GPG env; supervisor-test.py audit enforces | CAP-GIT | CODING |
| R-3 | DESIGN | run-policy.sh | AC-3 | clean-main preflight retained for every argv lacking --help/-h/--version; those flags anywhere in argv short-circuit with no state write and --help/-h wins over --version | only the help/version scan moved earlier; --help/-h wins over --version; no side effects on that path; every other argv, including real-run args, runs full preflight before any state write; test covers `--unattended --version` and `build --help` in a dirty tree | CAP-DRIVER | CODING |

Runner binding: `bash scripts/run-all-tests.sh`; feasibility evidence: `scripts/run-all-tests.sh` execs `scripts/lib/all_suites.py`; suites reproduced locally via `python3 -B scripts/tests/<name>-test.py`. No live-authentication prerequisites.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan left argument combinations unspecified; a single precedence rule closes the gap without weakening preflight for real runs. | s1.1 D-1 now states the first-of --help/-h/--version-wins rule; s9.1.r1/r2 and s10.1.r1 updated to match. |
| AR-002 | Accepted | AC-7 and AC-8 conflict; a prerequisite-failing suite is a red suite, so AC-8 is unmet until every suite passes. | Edit s13.1 and AC-7 so a prerequisite-failing suite counts as FAILED for AC-8 and is listed as unresolved in the PR. |
| AR-003 | Accepted | SB-5 offered two incompatible outcomes; one rule is needed: the TUI refuses without raising, and the fixture changes only if the test asserts a valid repo. | Edit s5.1 and s9.1.r5 to fix the refusal behavior and fixture rule, and AC-7 to state the expected result. |
| AR-004 | Accepted | Self-created fixture .gitignore alone leaves the dirty-host case untested; the fixture must cover both ignore variants so AC-5 is exercised. | Edit s1.1 D-2, s9.1.r3 and AC-5 so the attestation fixture writes its own .gitignore with and without .uncle and one shard asserts the ignore-containing case. |
| AR-005 | Accepted | The step-4 Owns list is closed while the exit-127 and gates-verification-integrity fixes may need other files, and 'setup edit' was undefined. | Step 4 text and s14.1.i1 now require an IMPLEMENTATION_NOTES.md deviation entry before editing any file outside Owns, and define a setup edit as changing no assertion, expected value, or skip condition. |
| AR-006 | Accepted | A missing-tool failure needs a defined channel and exit code so it is testable and distinguishable from a shell 'command not found'. | Row s9.1.r7 and AC-7 now require `missing prerequisite: <tool>` on stderr with a nonzero exit other than 127; s8.1 adds a manual check. |
| AR-007 | Accepted | Mixed-argument handling was unspecified; a precise rule keeps SI-1 intact because any real-run args still go through full preflight. | D-1 in s1.1, traceability row s10.1.r1 and restriction R-3 now state the first-recognized-flag rule, no state writes, and that real-run args still run preflight. |
| AR-008 | Accepted | AC-7 prerequisite-failure wording conflicts with AC-8's zero-failed requirement; a prerequisite failure must count as red. | Edited s13.1, AC-7, AC-8 and s9.1.r7 so a prerequisite-failing suite counts as FAILED, AC-8 stays unmet, and the suite is listed for the PR. |
| AR-009 | Accepted | The early-branch fix location is open and step 4 Owns omits the product files, so triage must name them and Owns must be amended before any edit. | Step 1 names early-branch product files; step 4 Owns amended before edits; change-impact row r4 updated. |
| AR-010 | Accepted | Isolating the fixture .gitignore could mask a real product defect when a host .gitignore lists .uncle, so the plan must state the product expectation and a covering check. | Edit s9.1.r3 risk/coverage and AC-5 so one shard uses a .gitignore containing .uncle and triage records the product behavior or out-of-scope decision. |
| AR-011 | Accepted | SB-5 left two incompatible outcomes deferred to step 4; the plan should fix the product behavior and the only condition for touching the fixture. | Edited s5.1 and s9.1.r5 to fix the TUI refusal behavior, and AC-7 and step-4 to match. |
| AR-012 | Accepted | Open-ended 'other flagged fixtures' makes step 3 scope unbounded; tying it to the supervisor-test.py audit bounds it. | Edited s9.1.r6 component/change and step-3 text to scope signing fixes to exactly the files the supervisor-test.py audit flags. |
| AR-013 | Accepted | Mixed-argument parsing was unspecified; a deterministic rule is needed so preflight cannot be bypassed by real-run args. | Added mixed-argument rule to s1 and updated R-3: help/version honored only as the first argument, otherwise full preflight. |
| AR-014 | Accepted | The plan specified only output and exit code for the early help/version path, so side-effect freedom was unstated and untested. | Added a side-effect-freedom rule to s2, extended change-impact rows r1/r2, and added a no-side-effects test to the AC-1/2 traceability row. |
| AR-015 | Accepted | SB-7 and AC-6 cover every fixture commit/tag, so scope must be all of scripts/tests/**, enforced by the supervisor audit, with repo-local config and neutralized global signing env. | Step 3, AC-6, R-2 and change-impact row r6 now cover all fixture git commit/tag/commit-tree calls under scripts/tests/** with repo-local config and sanitized env. |
| AR-016 | Accepted | Fixes need an explicit rule that they never read or mutate the host checkout's .gitignore or git config. | Added a host-isolation rule block to section 1 and updated the s9.1.r3 risk to match. |
| AR-017 | Accepted | A missing tool must fail closed; AC-7 and AC-8 leave that ambiguous, so the plan should state it explicitly. | Add fail-closed rule to s1.1 (D-4), AC-7, and R-1; clarify in the s9.1.r8 notes entry. |
| AR-018 | Accepted | Mixed-argument parsing was unspecified; a single deterministic rule removes ambiguity and keeps preflight for real runs. | D-1 in s1.1 states the anywhere-in-argv rule (--help/-h wins over --version, no preflight, no state); s9.1.r1/r2, s10.1.r1 and R-3 aligned. |
| AR-019 | Accepted | AC-7 and AC-8 conflict; a prerequisite-failing suite is still a failure, so AC-8 governs and the message wording needs a named check. | Edit AC-7, AC-8 and s7.1 so prerequisite failures count as FAIL and the message wording has a named check. |
| AR-020 | Accepted | Causes of exit 127 and gates-verification-integrity failures are unknown, so SB-8/AC-7 need recorded causes and expected behavior or an explicit unresolved/not-met status. | Step 1 records cause and expected behavior per failure; unresolved suites are listed and AC-7 marked not met; s9.1.r7 and AC-7 updated to match. |
| AR-021 | Accepted | AC-5 names a dirty host .gitignore but no step creates it; incidental worktree state is not evidence, so the condition must be created deliberately. | Edit AC-5 and s7.1: run attestation-statement-test.py with host .gitignore containing .uncle and clean; both must pass; step-4 records both runs. |
| AR-022 | Accepted | The baseline came from a dirty tree, so 'fails before' is ambiguous; judging against clean main removes the ambiguity. | Edited s1.1 (triage judged against clean main) and s7.1 (regression claim restated: host-state-only failures need no code change). |
| AR-023 | Accepted | SB-4/SI-3 'no mutation' needs a concrete detector; a before/after ref and file-hash comparison is checkable and cheap. | Edited s9.1.r4 coverage/change and AC-4 requirement/tests to compare git for-each-ref and a file-hash inventory around each skip context. |
