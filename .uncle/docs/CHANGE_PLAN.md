# Change Plan (Issue 149)

Issue 149

Seeded from [unclehq/uncle#149](https://github.com/unclehq/uncle/issues/149).

Omitted sections: Schema/persistence (none); Migration (none); Concurrency (none beyond shared exclude file, idempotent); Feature flag (none)

## 1. Selected technical approach

D-1: Add `ensure_exclude(root)` to `scripts/lib/uncle_gitignore.py`: idempotently writes the CANONICAL block into the git common dir's `info/exclude` (via `git rev-parse --git-path info/exclude`), never touching tracked files. Contract: it rewrites exactly one canonical block, removing every existing managed line (partial, duplicated or legacy spellings per MANAGED) and preserving all other lines; it creates `info/` if missing and ends the file with a trailing newline. Path safety: it refuses to write (returns False) if the resolved exclude file or its parent `info/` directory is a symlink, or if the resolved path is not inside the git common dir (`git rev-parse --git-common-dir`); it writes atomically (temp file in the same directory, then `os.replace`), never opening the exclude file with plain truncating `open(path,'w')`. Return semantics: True only when it wrote (content changed); False without writing when the file already holds exactly one canonical block; False without raising on a non-git root, a refused path, or any OSError.
D-2: TUI `_ensure_uncle_gitignored` calls only `ensure_exclude`; if tracked `.gitignore` has a legacy managed line differing from canonical, print a one-line deferral notice (normalization happens in the run worktree pre-audit).
D-3: Keep `ensure()` for worktrees.sh:130 only (pre-audit, in audited diff). CLI main keeps current behavior for that caller.
D-4: In change-pr.sh add a publish guard implemented as a standalone shell function `assert_tree_matches_attested` that can be sourced and invoked directly from a fixture repo (no PR or network needed). It (a) requires `git status --porcelain --untracked-files=no` empty; (b) compares the full set of paths and blob contents in the tree to be published against the attested commit_tree and fails on any difference (added, removed or modified path), with `.gitignore` compared byte for byte; (c) fails if any staged or published path under `.uncle/` is outside the allowlist (`.uncle/docs/**`, `.uncle/attestation.json`, `.uncle/attestation.sig`, `.uncle/allowed_signers`), since `.uncle/` holds run state and API keys. On failure it prints each offending path and the reason on stderr and returns/exits nonzero; on success it returns 0 silently. It runs before commit and after publish, and the same function runs at the no-PR completion path (G-5), so AC-1 and AC-2 are asserted by the Python test sourcing it via subprocess in a fixture repo and checking exit code and stderr. Without an attestation, only checks (a) and (c) apply.
D-5: Keep snapshot managed-line tolerance (in-flight runs); revisit later.

D-1a (AR-016, ensure_exclude semantics): the path comes from `git rev-parse --git-path info/exclude` run in the root, so a linked worktree resolves to the common dir's shared exclude file; a missing `info/` directory is created. `ensure_exclude` owns only its own delimited block, bracketed by marker comments `# >>> uncle managed >>>` and `# <<< uncle managed <<<` and holding exactly the CANONICAL lines. Existing content is read; any existing (including partial) marked block is replaced in place by the single canonical block, never duplicated; every stray line in MANAGED (canonical, partial, duplicated or legacy spellings) outside the block is removed so none is duplicated; if no managed content exists the block is appended once, after adding a missing trailing newline. Every other user line is preserved byte for byte. It returns True only when it changed the file and False when already canonical; it returns False without raising on a non-git root or any OSError, and the TUI prints one warning per process in that case.
D-4a: publish also fails, naming the path and the matching rule from `git check-ignore -v`, if any `.uncle/docs/` artifact in the attested tree is reported ignored by `git check-ignore` (for example, a legacy bare `.uncle` in the tracked `.gitignore`).
D-6: The clean-tracked-tree check (`git status --porcelain --untracked-files=no` empty) also runs at no-PR completion, as the same standalone function invoked from the completion path in change-pr.sh. It is the last item dropped from scope. A test covers a no-PR completion in a fixture repo.

## 2. Alternatives
(a) Only guard at publish, keep TUI writes: leaves dirty main checkout. (b) Move everything to info/exclude including worktrees: legacy bare `.uncle` in tracked `.gitignore` outranks exclude and would hide `.uncle/docs`. (c) Remove tolerance now: breaks in-flight runs.

## 3. Why preferred

Removes the only continuous tracked writer, keeps the safe pre-audit worktree path, adds an enforcing check. The only permitted caller of ensure() is worktree creation (worktrees.sh:130, pre-audit); no other call site may exist in scripts/ or uncle_tui.py (the CLI main in uncle_gitignore.py is invoked only by that worktree caller). A test in gitignore-clean-end-test.py statically scans scripts/ and uncle_tui.py and fails on any other ensure() caller or invocation of the module's CLI.

## 4. Components to modify
See change-impact table.

## 5. Not to modify
CANONICAL/MANAGED contents; `strip_managed`/`only_adds_managed`; `.uncle/workflow/` snapshot rules; parallel step worktrees.

## 6. Data flow
TUI -> ensure_exclude -> `.git/info/exclude` (untracked). Worktree create -> ensure (tracked, pre-audit). Publish -> exact-bytes check.

## 8. Interface changes
New `uncle_gitignore.ensure_exclude(project_root)->bool`. Existing signatures unchanged.

## 10. Compatibility

Existing callers/tests of `ensure`, tolerance helpers retained. In-flight runs whose snapshot predates this change keep managed-line tolerance at publish (strip_managed equality for .gitignore); runs started after it use exact bytes.

## 12. Error and recovery

ensure_exclude returns False (never raises) and does not write when: the root is not a git repo; any OSError occurs; the exclude file or its parent `info/` is a symlink; or the resolved path is outside the git common dir. It returns True only when it wrote. Writes are atomic (temp file then replace); an atomic write failure leaves the previous exclude file intact and the temp file removed. When ensure_exclude returns False for a git root, the TUI prints one warning line to stderr, once per process, and the run continues. A pre-existing partial, legacy or duplicated managed block in info/exclude is replaced by exactly one canonical block (user lines and a missing trailing newline handled per D-1a), never duplicated. Publish guard failure: nonzero exit, names file(s) on stderr.

## 14. Rollback plan
Revert the commit(s); no persisted state changed. The added exclude block is inert and may remain.

## 16. Automated-test strategy

Three new test files, split by owning step. (1) S1 owns `scripts/tests/gitignore-clean-end-test.py`: table-driven `ensure_exclude` tests (AC-4, AC-5, AC-7) covering existing canonical, partial, duplicated and legacy blocks, no trailing newline, missing `info/`, a linked worktree (shared common-dir exclude), user lines preserved, exactly one canonical block after two calls; a fixture with `info/exclude` (and separately `info/`) symlinked to an outside file asserting `ensure_exclude` returns False and the target is unchanged; and the static caller-enumeration test asserting worktree creation (worktrees.sh, read-only, owned by no step) is the only `ensure()` caller in scripts/ and uncle_tui.py. (2) S2 owns `scripts/tests/gitignore-tui-test.py`: drives load_config, reload and project switch each against a fixture repo and asserts `git status --porcelain --untracked-files=no` empty and `.gitignore` bytes unchanged after each (AC-5, including test_tui_reload_leaves_gitignore_unchanged). (3) S3 owns `scripts/tests/gitignore-publish-guard-test.py`: sources `assert_tree_matches_attested` in fixture repos and asserts exit code and stderr for AC-1/AC-2/AC-2b, no-PR completion, managed-line-only difference, and ignored `.uncle/docs`. All fixtures use `git -c commit.gpgsign=false -c tag.gpgsign=false`, `--no-gpg-sign`, repo-local signing disabled. Extend `scripts/tests/pr-auto-publish-test.sh` (AC-3, S4). Defect injection (AC-6) recorded in IMPLEMENTATION_NOTES.

AC-6 defect injection (mutation M-1, 're-add ensure() after audit'): in a throwaway copy of the repo (never the working tree), re-add a call to `uncle_gitignore.ensure()` in `_ensure_uncle_gitignored` in uncle_tui.py. Run `python3 scripts/tests/gitignore-clean-end-test.py` against the copy; it MUST fail (at least `test_tui_reload_leaves_gitignore_unchanged`). The exact command, exit status and failing-test output are recorded in IMPLEMENTATION_NOTES.md. If the tests pass under M-1, the tests are inadequate and must be strengthened before completion.

## 17. Regression strategy
Run both runners; gitignore-tolerance-test.py must stay green unmodified.

## 18. Manual verification
Complete a real change request; confirm main checkout `git status` clean and worktree auto-removed after PR.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST I-3 | AC-5 | no bookkeeping tracked write | ensure_exclude only in TUI | issue invariant | CAP-GIT | uncle_tui.py:281-292,1617 inspected | CODING |
| R-2 | USER | CHANGE_REQUEST I-1/I-2 | AC-2 | published tree equals audited/attested tree: every tracked file matches the attested tree, .gitignore byte for byte at publish; no non-allowlisted .uncle/ path published | publish guard D-4: first verify the attestation signature (.uncle/attestation.sig) against .uncle/allowed_signers; a missing or invalid signature fails publish. Only then compare the full PR tree to the attested commit_tree: every tracked file must match, .gitignore byte for byte with no managed-line tolerance (strip_managed/only_adds_managed are never used by the guard; a difference confined to managed lines fails publish); require empty tracked porcelain status; reject any staged .uncle/ path outside the allowlist. | issue invariant | CAP-GIT | change-pr.sh:704-720 inspected | CODING |
| R-3 | USER | Non-goals | AC-7 | canonical block unchanged; docs visibility asserted only for worktrees and roots without a legacy bare `.uncle` line; legacy roots get the deferral notice and the S1 test documents that case | reuse CANONICAL | non-goal | none | uncle_gitignore.py:53 | CODING |
| R-4 | REPOSITORY | tests | AC-4 | signing disabled in fixtures | git -c flags | CLAUDE.md signing rules | CAP-GIT | n/a | CODING |
| R-5 | DESIGN | D-5 | AC-4 | in-flight tolerance | keep strip_managed/only_adds_managed only for snapshot and approval comparisons of in-flight runs, comparing .gitignore via strip_managed equality only for runs whose snapshot predates this change (exact bytes otherwise); the D-4 publish guard never applies them and applies no managed-line tolerance | revisable; tolerance is scoped to snapshots/approval comparisons and does not weaken publish exactness | none | change-pr.sh:595 | CODING |

Publish/completion guard modes (AR-009): when an attestation exists, the guard compares tracked files against the attested tree. When no attestation exists (for example a no-PR run), only the clean tracked-status check applies (`git status --porcelain --untracked-files=no` empty). Approved artifacts that are legitimately uncommitted (untracked, e.g. `.uncle/docs/*`) never trigger a refusal in either mode, since the guard only inspects tracked paths.

CAP-GIT = git binary in PATH (CODING and LIVE_VERIFICATION). No live authentication needed for coding.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| scripts/lib/uncle_gitignore.py | add `ensure_exclude` | untracked ignore mechanism | Medium: exclude semantics | gitignore-clean-end-test.py |
| uncle_tui.py | `_ensure_uncle_gitignored` uses ensure_exclude, deferral notice; all TUI paths (load_config, reload, project switch, startup) route only through this helper and never call `ensure()` | stop tracked writes | Low | gitignore-clean-end-test.py (drives load_config, reload and project switch each and asserts tracked `.gitignore` bytes and `git status` unchanged) |
| scripts/lib/change-pr.sh | publish/complete guard as standalone function `assert_tree_matches_attested` (nonzero exit, offending paths on stderr): every tracked file compared to the attested tree, `.gitignore` byte for byte with no managed-line tolerance (strip_managed not applied; a managed-line-only difference fails), plus empty `git status --porcelain --untracked-files=no`; evaluated relative to the attested tree (not HEAD of the main checkout) and only after the worktree-creation `.gitignore` edit is included in the audited diff; also invoked on the no-PR completion path (D-6) | I-1, I-2, I-4 | Medium: false refusal; mitigated by comparing to the attested tree so the legitimate pre-audit worktree edit does not count as dirty | gitignore-clean-end-test.py (sources the function in a fixture repo; asserts exit code and stderr; includes no-PR completion case and managed-line-only difference failing), pr-auto-publish-test.sh |
| scripts/tests/gitignore-clean-end-test.py | new: ensure_exclude table-driven, symlink and caller-enumeration tests (S1) | AC-4,5,7 | Low | self |
| scripts/tests/pr-auto-publish-test.sh | extend | AC-3 | Low | self |
| scripts/tests/gitignore-tui-test.py | new (S2): load_config, reload, project switch tests | AC-5 | Low | self |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | G-1, G-5, Guard compares against the attested tree when one exists; with no attestation (no-PR run) only the clean tracked-status check applies | I-4, I-clean-relative: tracked-clean is evaluated relative to the attested tree, after the pre-audit worktree edit is in the audited diff | change-pr.sh | gitignore-clean-end-test.py (PR and no-PR completion cases) | real CR completes clean |
| AC-2 | G-2 | I-1, I-2 | change-pr.sh | gitignore-clean-end-test.py (asserts: a legacy-snapshot run whose .gitignore differs from the attested tree only in managed lines passes via strip_managed equality; a new (non-legacy) run whose .gitignore differs from the attested tree only in a managed line fails at publish, with no managed-line tolerance, because exact bytes are compared) | n/a |
| AC-3 | G-3 | I-4 | from-issue.sh (unchanged) | pr-auto-publish-test.sh | worktree auto-removed |
| AC-4 | G-4 | I-3, The worktree-creation `.gitignore` edit is permitted only before audit and is part of the audited diff; the runtime clean-tree check never treats it as a violation | uncle_gitignore.py | gitignore-clean-end-test.py | n/a |
| AC-5: TUI load_config, reload and project switch never write tracked files; they call only ensure_exclude. `info/exclude` contains the canonical block exactly once after any number of calls; `ensure_exclude` returns True only when it wrote and False when already canonical, non-git, or on OSError. When the tracked .gitignore holds a managed line differing from canonical, exactly one stderr line containing both `.gitignore` and `worktree` is printed (deferral notice), and nothing is printed otherwise. If the notice is cut from scope, AC-5 drops only the notice assertion. | G-6 | I-3 | uncle_tui.py | gitignore-clean-end-test.py: test_tui_reload_leaves_gitignore_unchanged drives each TUI path (load_config, reload, project switch) separately and asserts no tracked file changes and exclude holds the canonical block once, gitignore-clean-end-test.py: static assertion that uncle_tui.py has no call to `ensure(` from uncle_gitignore | start TUI, git status clean, deferral notice appears at most once per project root per process |
| AC-6 | all | I-1 | tests | defect injection M-1 (re-add ensure() after audit) in a throwaway copy: gitignore-clean-end-test.py must fail; command and output recorded in IMPLEMENTATION_NOTES.md | n/a |
| AC-7 is asserted only for worktrees (after pre-audit normalization) and for roots whose tracked .gitignore has no legacy bare `.uncle` line: exclude-only rules keep `.uncle/docs/` visible. With a legacy bare `.uncle` in the root's tracked .gitignore, docs are expected to be hidden until worktree normalization, the TUI prints the deferral notice, and the test documents this expected result. | P-1 | EI-2 | uncle_gitignore.py | gitignore-clean-end-test.py (no-legacy root and worktree: docs visible; legacy root: docs hidden and deferral notice printed) | git status shows docs |
| AC-2 (extra paths): publish fails when the PR tree has any path differing from the attested tree or any non-allowlisted path under .uncle/ | G-2 | I-1, I-2 | change-pr.sh | gitignore-clean-end-test.py: fixture stages .uncle/secret and an extra tracked file; guard exits nonzero naming both on stderr | n/a |

Compliance scope (AR-001): AC-1 and AC-2 compare the final tracked tree against the audited worktree tree, never the main root's pre-existing tracked content. A main checkout whose tracked `.gitignore` holds a legacy managed line left unnormalized by the TUI is compliant; the TUI prints the deferral notice and writes no tracked file. Tests assert the main-root `.gitignore` bytes are unchanged by the TUI and do not treat the legacy line as a failure.

Bug regression test: `test_tui_reload_leaves_gitignore_unchanged` lives in scripts/tests/gitignore-tui-test.py (owned by S2); it fails before (load_config rewrites `.gitignore`) and passes after.

## Implementation sequence

1. Step S1 add `ensure_exclude` and its unit tests (decision D-1; AC-4, AC-5, AC-7). AC-7 is asserted for worktrees and roots without legacy lines; a test documents that a legacy bare `.uncle` root hides docs until worktree normalization. Tests cover: absent file, absent info/ dir, no trailing newline, partial block, duplicated block, legacy spellings, already-canonical (returns False, bytes unchanged), foreign lines preserved, non-git root and unwritable file (False, no raise). Owns: `scripts/lib/uncle_gitignore.py`, `scripts/tests/gitignore-clean-end-test.py`
2. Step S2 switch TUI helper to `ensure_exclude` plus deferral notice (D-2; AC-5); builds on S1's new function. Every TUI path that touched `.gitignore` (load_config, reload, project switch, startup at uncle_tui.py:281-292,1617) must call only `_ensure_uncle_gitignored`, which calls only `ensure_exclude`; no TUI code path may call `ensure()` or write a tracked file, and the test drives each path. The notice is a single stderr line containing `.gitignore` and `worktree`, printed only when a tracked managed line differs from canonical, and at most once per project root per process (tracked per-process set of roots); the test asserts a second reload/project switch for the same root prints nothing further. S1's caller-enumeration test (only worktree creation may call ensure()) must stay green after this change. Owns: `uncle_tui.py` — Depends on: 1
3. Step S3 publish guard in change-pr.sh (D-4; AC-1, AC-2): implement `assert_tree_matches_attested` as a standalone sourceable function (nonzero exit, offending files and reason on stderr), called at publish and at no-PR completion. It first verifies the attestation signature against `.uncle/allowed_signers` and fails on a missing or invalid signature; then compares every tracked file in the full PR tree to the attested tree, comparing `.gitignore` byte for byte with no managed-line tolerance (a test asserts that a managed-line-only difference fails; for runs whose snapshot predates this change, `.gitignore` is compared by strip_managed equality instead); and rejects any staged `.uncle/` path outside the allowlist. Untracked approved artifacts do not fail the guard. Independent of S2; first grep tests referencing `_ensure_uncle_gitignored`/`ensure(` to avoid breaking them. Owns: `scripts/lib/change-pr.sh` — Depends on: 1
4. Step S4 extend publish shell test for removal (AC-3) and run defect injection M-1 (AC-6): apply M-1 in a throwaway copy, confirm the new tests fail, and record the command and output. Owns: `scripts/tests/pr-auto-publish-test.sh`, `.uncle/docs/IMPLEMENTATION_NOTES.md` — Depends on: 2, 3

Ownership (overrides step file lists above): S1 owns only gitignore-clean-end-test.py (ensure_exclude and caller-enumeration tests). S2 additionally owns `scripts/tests/gitignore-tui-test.py` (TUI-path tests, so they pass at S2 completion). S3 additionally owns `scripts/tests/gitignore-publish-guard-test.py` (guard tests, so they pass at S3 completion); no 'append via S4' workaround exists. `scripts/lib/worktrees.sh` is read-only and owned by no step. S4 Depends on 1, 2 and 3 and runs, in a throwaway copy outside the repo, mutation M-1 (re-add `ensure()` on the TUI path) and mutation M-2 (remove/no-op the publish guard); the new tests must fail under each, and the exact commands and output are recorded in IMPLEMENTATION_NOTES.md. S4 cannot modify tests it does not own.

## 21. Scope cuts

Cut first: removal of snapshot tolerance (already deferred); then the TUI deferral notice text (AC-5 then drops its notice assertion, and the test no longer checks stderr for it). The pre-commit exact-bytes check and the post-publish status check are required by D-4 and are not cut; if time forces a cut, the post-publish check goes last and only after recording a deviation in IMPLEMENTATION_NOTES.

## 22. Risks

- Exact live trigger not confirmed; mitigated by removing all non-worktree tracked writes.
- Legacy tracked managed lines (e.g. bare `.uncle`) in the main root's tracked `.gitignore` are left untouched by the TUI; this is compliant and not a failure. Because such a line outranks `info/exclude`, it can hide `.uncle/docs` in the main root. Mitigation (AR-016): AC-1 and AC-2 compare against the audited worktree tree, never the main root; normalization via `ensure()` happens only in the run worktree before audit; and publish fails on any ignored `.uncle/docs` artifact per `git check-ignore`, so hidden docs cannot ship silently.
- Publish guard false positives on legit tracked changes: guard compares only against attested tree.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan left unstated whether a main-root run with a legacy tracked managed line is compliant; stating it removes the AC-1/AC-5 ambiguity. | Edited s19.1.i2 and added a compliance-scope prose block to s16 after s16.1. |
| AR-002 | Accepted | AC-2 and I-1 cover any tracked file, so D-4 comparing only .gitignore was too narrow; managed-line tolerance must not apply at publish. | Edit R-2 and change-impact row s15.1.r3 so the guard compares every tracked file to the attested tree, .gitignore byte for byte, no tolerance; step S3 text updated. |
| AR-003 | Accepted | A tracked-clean check must not reject the legitimate pre-audit worktree .gitignore edit, so it is defined relative to the attested tree after that edit is audited. | Edit R-4 intent in s14.1 via new restriction row, AC-1/AC-4 rows and change-impact r3: clean check evaluated against attested tree, after worktree edit is in audited diff. |
| AR-004 | Accepted | Failure behavior for unwritable, partial-block and non-git cases was unspecified and spec/plan disagreed on warning. | s9.1 now specifies False on OSError/non-git, one TUI warning per process, partial block replaced not duplicated; s1.1 D-1 gets matching sentence. |
| AR-005 | Accepted | A legacy bare `.uncle` in tracked .gitignore outranks exclude, so AC-7 cannot hold for that combination before worktree normalization. | Scope AC-7 and R-3 to bases with no legacy bare `.uncle`; add a test documenting hidden docs for the legacy case. |
| AR-006 | Accepted | The no-PR completion path (G-5/AC-1) had no named guard, test, or cut-order position. | D-4 extended to no-PR completion; s15.1.r3 and AC-1 cover it; s18 cut order keeps the clean-tracked-tree check last. |
| AR-007 | Accepted | A legacy bare `.uncle` in tracked .gitignore outranks exclude, so docs visibility in the main root is undefined unless AC-7 is scoped explicitly. | Scope AC-7 and R-3 to worktrees and roots without legacy lines; require the deferral notice for legacy roots; S1 test documents the legacy case. |
| AR-008 | Accepted | D-3 keeps ensure() without enumerating callers; I-1/I-3 need proof that nothing can run it after audit. | s3.1 states worktree creation is the only permitted ensure() caller; S1 test asserts no other call sites in scripts/ or uncle_tui.py. |
| AR-009 | Accepted | Guard behavior without an attestation or with legitimately uncommitted approved artifacts was undefined; a two-mode rule resolves it. | Add guard-mode rule to s14 (restriction text), amend R-2 mechanism, AC-1 behavior, and step S3 text. |
| AR-010 | Accepted | Exact-bytes publish check would refuse in-flight runs whose snapshot carries legacy managed lines that D-5 deliberately tolerates; the comparison mode must depend on snapshot vintage. | Edit R-2, R-5, AC-2, S3 step and Compatibility: legacy-snapshot runs compare .gitignore via strip_managed equality; others exact bytes. |
| AR-011 | Accepted | ensure_exclude's behavior for partial, duplicated or already-canonical blocks and its return value were unspecified; a precise contract is needed for AC-5. | D-1 in s1.1 now defines the one-block rewrite and return semantics; step S1 (s17.1.i1) tests them. |
| AR-012 | Accepted | The helper runs on every reload and project switch, so the notice needs a frequency bound to be assertable. | AC-5 and S2 now state the deferral notice prints at most once per project root per process. |
| AR-013 | Accepted | Real gap: git-path may resolve to a symlinked or out-of-tree exclude file and ensure() uses plain open(path,'w'), so ensure_exclude needs explicit symlink and atomic-write rules. | Edit D-1 (s1.1) and section 12 (s9.1) to refuse symlinked/outside-common-dir paths, write atomically, else return False. |
| AR-014 | Accepted | Real gap: a .gitignore-bytes plus --untracked-files=no check cannot detect extra staged paths such as .uncle/* secrets. | D-4 now compares the full PR tree to the attested tree and rejects any staged .uncle/ path outside the allowlist; R-2, change-impact, AC-2 and S3 aligned. |
| AR-015 | Accepted | The attested commit_tree is the guard's trust anchor, so it must be signature-verified against .uncle/allowed_signers before any comparison. | Edit R-2 mechanism and S3 (s17.1.i3) so the guard verifies the attestation signature first and fails publish on a missing or invalid signature. |
| AR-016 | Partially accepted | Real gap: exclude may hold user or partial .uncle rules, and a legacy bare .uncle can hide .uncle/docs; a delimited block and a check-ignore publish check close it. (1 edit(s) could not be placed in the plan and were left out.) | Section 1 adds D-1a/D-4a (delimited block, check-ignore publish check); sequence and risks updated accordingly. |
| AR-017 | Accepted | AC-5 covers load_config, reload and project switch, but D-2 named only the helper; the plan must say every TUI path calls only that helper and the test drives each path. | Edit S2 step text, AC-5 traceability row, and the s15.1.r2 change-impact row to require all TUI .gitignore paths to route through ensure_exclude and the test to drive each. |
| AR-018 | Accepted | The guard's entry point, exit code, message and no-PR path were unspecified, so tests could not drive it. | D-4 in s1.1 and S3 in s17.1.i3 now define a standalone function with exit code, stderr message and the same check for no-PR completion. |
| AR-019 | Accepted | Defect injection was only a note with an undefined mutation; a named mutation with recorded evidence makes AC-6 verifiable. | Define named mutation M-1 in s11 and AC-6, and make step S4 apply it in a throwaway copy and record command and output. |
| AR-020 | Accepted | ensure_exclude's handling of existing, partial and legacy blocks, missing newline, missing info/ and linked worktrees was unspecified and affects AC-5/AC-7. | Added D-1a to s1 and updated s9.1 to define block replacement, line preservation, info/ creation, worktree resolution and False-without-raising. |
| AR-021 | Accepted | Exact-bytes guard and D-5 tolerance conflict; tolerance must stay out of publish, and the post-publish check must not be first cut. | Edit R-2, R-5, s15.1.r3, AC-2, s17.1.i3 and s18.1: no managed-line tolerance at publish, test asserts it, post-publish check not cut first. |
| AR-022 | Accepted | The deferral notice needs a defined stream, text and trigger to be assertable, and its cut must also drop the assertion. | AC-5 and S2 specify one stderr line naming .gitignore and worktree, printed only on a differing tracked managed line; scope cuts drop that assertion with it. |
