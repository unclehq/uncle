## AR-001: AC-1/G-1 require a clean tree and a .gitignore byte-identical to the audited tree after the TUI runs, but a legacy track

- Severity: HIGH
- References: CHANGE_PLAN D-2 and Risks (legacy bare `.uncle` remains in the main root) against CHANGE_SPEC AC-1/AC-5. Settle with: 'Legacy tracked managed lines in the main checkout are left untouched; AC-1 and AC-2 compare against the audited worktree tree, never the main root, and this case is not a failure.'
- Failure: AC-1/G-1 require a clean tree and a .gitignore byte-identical to the audited tree after the TUI runs, but a legacy tracked managed line is left unnormalized in the main checkout. The plan never says whether a main-root run with such a line is compliant.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: D-4 says the guard compares .gitignore bytes to the attested commit_tree entry, but AC-2 and I-1 say any tracked file mu

- Severity: HIGH
- References: CHANGE_PLAN D-4 (only `.gitignore` exact bytes, plus porcelain empty) against CHANGE_SPEC AC-2 ('or any tracked file'). Settle with: 'The guard compares every tracked file to the attested tree, with .gitignore compared byte for byte and no managed-line tolerance applied at publish.'
- Failure: D-4 says the guard compares .gitignore bytes to the attested commit_tree entry, but AC-2 and I-1 say any tracked file must match. The scope of the byte comparison is ambiguous, and so is how it interacts with the tolerated snapshot managed lines (D-5).
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: A runtime tracked-clean check conflicts with the shipped scenario where `.gitignore` is legitimately created or modified

- Severity: MEDIUM
- References: CHANGE_SPEC G-1 and I-4 ('no tracked modifications') against AC-4 (tracked edit allowed at worktree creation). Settle with: 'The clean-tree check runs only after the worktree edit is committed or included in the audited diff, and it is evaluated relative to the attested tree.'
- Failure: A runtime tracked-clean check conflicts with the shipped scenario where `.gitignore` is legitimately created or modified at worktree creation. Whether the pre-audit worktree edit counts as 'clean' is not stated, and the plan does not say what happens when the TUI or a parallel session modifies the main checkout.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Failure behavior is unspecified when the exclude file cannot be written, is already present with partial or conflicting

- Severity: MEDIUM
- References: CHANGE_SPEC §8 ('Unwritable info/exclude: warn') against CHANGE_PLAN §12 ('return False, run continues'). Settle with: 'ensure_exclude returns False on any OSError or non-git root, the TUI prints one warning line once per process, and a pre-existing partial block is replaced by the canonical block, never duplicated.'
- Failure: Failure behavior is unspecified when the exclude file cannot be written, is already present with partial or conflicting blocks, or when the repo is not a git repo. The spec says 'warn, continue' and the plan says 'return False', which differ on whether a warning is printed.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: AC-7 requires exclude-only rules to keep `.uncle/docs/` visible, but the plan itself concedes a legacy bare `.uncle` in

- Severity: MEDIUM
- References: CHANGE_SPEC §15 assumption and CHANGE_PLAN alternative (b), against AC-7. Settle with: 'AC-7 is asserted only for a base .gitignore with no legacy bare `.uncle`; a legacy tracked line is expected to hide docs until worktree normalization and the test documents that.'
- Failure: AC-7 requires exclude-only rules to keep `.uncle/docs/` visible, but the plan itself concedes a legacy bare `.uncle` in tracked .gitignore outranks exclude and hides them. No expected result is defined for that combination in the main root or in a linked worktree before normalization.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The 'no PR' completion path in G-5/AC-1 is covered by neither a named guard nor a test.

- Severity: LOW
- References: CHANGE_SPEC G-5 and AC-1 ('with and without PR') against CHANGE_PLAN D-4 and §21. Settle with: 'The clean-tracked-tree check also runs at no-PR completion and is the last item dropped from scope.'
- Failure: The 'no PR' completion path in G-5/AC-1 is covered by neither a named guard nor a test. D-4 only places the guard in change-pr.sh publish, and the cut list drops the post-publish check without saying what remains for the no-PR path.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Docs visibility in the main checkout is undefined when its tracked .gitignore holds a legacy bare `.uncle`, which outran

- Severity: HIGH
- References: CHANGE_PLAN §22 risk 2 against CHANGE_SPEC AC-7 and P-1.
- Failure: Docs visibility in the main checkout is undefined when its tracked .gitignore holds a legacy bare `.uncle`, which outranks exclude. Add: 'With a legacy bare .uncle line in the root's tracked .gitignore, the TUI prints the deferral notice and AC-7 is asserted only for worktrees and for roots without legacy lines.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: D-3 keeps ensure() and the CLI main, but the plan never enumerates callers or says none can run after audit, which confl

- Severity: HIGH
- References: CHANGE_PLAN D-3 and S3 against CHANGE_SPEC I-1 and I-3.
- Failure: D-3 keeps ensure() and the CLI main, but the plan never enumerates callers or says none can run after audit, which conflicts with I-1 and I-3. Add: 'The only permitted callers of ensure() are worktree creation; a test asserts no other call sites in scripts/ or uncle_tui.py.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The publish guard's behavior is undefined when there is no attestation (G-5 no-PR run) or when approved artifacts are le

- Severity: MEDIUM
- References: CHANGE_PLAN D-4 against CHANGE_SPEC G-5 and risk of false positives (§22).
- Failure: The publish guard's behavior is undefined when there is no attestation (G-5 no-PR run) or when approved artifacts are legitimately uncommitted. Add: 'The guard compares against the attested tree when one exists; otherwise only the clean tracked-status check applies.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Exact .gitignore bytes at publish (D-4, AC-2) contradict retained managed-line tolerance (D-5), so an in-flight run coul

- Severity: MEDIUM
- References: CHANGE_PLAN D-4 against D-5 and R-5; CHANGE_SPEC AC-2 says bytes, Compatibility keeps tolerance.
- Failure: Exact .gitignore bytes at publish (D-4, AC-2) contradict retained managed-line tolerance (D-5), so an in-flight run could be refused. Add: 'The guard compares .gitignore by strip_managed equality for runs whose snapshot predates this change, and by exact bytes otherwise.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: ensure_exclude is unspecified for a partial or duplicated managed block in exclude, and for its return value when alread

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 and §12 against AC-5 ('exclude contains canonical block once').
- Failure: ensure_exclude is unspecified for a partial or duplicated managed block in exclude, and for its return value when already present. Add: 'ensure_exclude returns True only when it wrote; it rewrites exactly one canonical block, removing existing managed lines; it returns False without raising on non-git or OSError.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The deferral notice frequency is unspecified although the helper is called on every reload and project switch.

- Severity: LOW
- References: CHANGE_PLAN D-2 and CHANGE_SPEC G-6, AC-5.
- Failure: The deferral notice frequency is unspecified although the helper is called on every reload and project switch. Add: 'The deferral notice is printed at most once per project root per process.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: No rule for a symlinked or shared info/exclude path from `git rev-parse --git-path`.

- Severity: HIGH
- References: CHANGE_PLAN D-1 and section 12 say only 'return False'; ensure() in uncle_gitignore.py uses plain open(path,'w') with no symlink handling.
- Failure: No rule for a symlinked or shared info/exclude path from `git rev-parse --git-path`. Say: 'ensure_exclude refuses to write if the resolved file or its parent is a symlink or outside the git common dir, writes atomically, else returns False.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The guard checks only `.gitignore` bytes and uses --untracked-files=no, so extra files, including ignored `.uncle/*` sec

- Severity: HIGH
- References: CHANGE_PLAN D-4 compares `.gitignore` bytes plus `git status --untracked-files=no`; uncle_gitignore.py header says .uncle holds API keys.
- Failure: The guard checks only `.gitignore` bytes and uses --untracked-files=no, so extra files, including ignored `.uncle/*` secrets, could enter the PR. Say: 'Publish fails if the PR tree differs from the attested tree, and no path under .uncle/ outside the allowlist may be staged.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The attested commit_tree is the guard's trust anchor, but the plan never says it is verified.

- Severity: MEDIUM
- References: CHANGE_PLAN D-4 and R-2 reference the 'attested commit_tree entry' with no signature-verification step.
- Failure: The attested commit_tree is the guard's trust anchor, but the plan never says it is verified. Say: 'The guard verifies the attestation signature against .uncle/allowed_signers before comparing; a missing or invalid signature fails publish.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: The plan says nothing about info/exclude already holding user or partial `.uncle` rules, or a legacy bare `.uncle` that

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 'idempotently writes the CANONICAL block'; Risks: legacy bare `.uncle` remains until a worktree run.
- Failure: The plan says nothing about info/exclude already holding user or partial `.uncle` rules, or a legacy bare `.uncle` that hides `.uncle/docs`. Say: 'ensure_exclude replaces only its own delimited block, and publish fails if any .uncle/docs artifact is ignored per git check-ignore.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: AC-5 says load_config, reload and project switch never write tracked files, but D-2 changes only _ensure_uncle_gitignore

- Severity: HIGH
- References: CHANGE_SPEC AC-5 and the regression test test_tui_reload_leaves_gitignore_unchanged versus D-2/S2 (uncle_tui.py:281-292,1617).
- Failure: AC-5 says load_config, reload and project switch never write tracked files, but D-2 changes only _ensure_uncle_gitignored. Plan should say: every TUI path that touched .gitignore must call only that helper, and the test drives each path.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The D-4 guard lives in change-pr.sh but AC-1/AC-2 are verified from a Python test; the entry point, exit code and messag

- Severity: HIGH
- References: CHANGE_PLAN D-4 and S3 versus gitignore-clean-end-test.py; CHANGE_SPEC G-5 has no entry point.
- Failure: The D-4 guard lives in change-pr.sh but AC-1/AC-2 are verified from a Python test; the entry point, exit code and message are unspecified, as is the no-PR path (G-5). Plan should say: the guard is a standalone function the test invokes in a fixture repo, exits nonzero naming files on stderr, and the no-PR path runs the same check.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: AC-6 defect injection is only a note in IMPLEMENTATION_NOTES, and the mutation is undefined.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-6 verification; CHANGE_PLAN S4.
- Failure: AC-6 defect injection is only a note in IMPLEMENTATION_NOTES, and the mutation is undefined. Plan should say: a named mutation re-adding ensure() after audit is applied in a throwaway copy, the new tests must fail, and the command and output are recorded.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: ensure_exclude behavior is unspecified for existing canonical, partial or legacy blocks, a missing trailing newline, a m

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 and section 12 versus AC-5/AC-7.
- Failure: ensure_exclude behavior is unspecified for existing canonical, partial or legacy blocks, a missing trailing newline, a missing info/ dir, and a linked worktree. Plan should say: it replaces managed lines with one canonical block, preserves other lines, creates info/, and returns False without raising on failure.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: The guard's exact-bytes check conflicts with D-5 managed-line tolerance, and the post-publish check is the first cut in

- Severity: MEDIUM
- References: CHANGE_PLAN D-4 vs D-5 and section 21; CHANGE_SPEC I-2.
- Failure: The guard's exact-bytes check conflicts with D-5 managed-line tolerance, and the post-publish check is the first cut in scope cuts although D-4 requires it. Plan should say: the comparison has no managed-line tolerance, a difference only in managed lines fails, and the test asserts it.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: AC-5 requires a deferral notice, yet its text, stream and trigger are unspecified and it is cut early in scope cuts, so

- Severity: LOW
- References: CHANGE_SPEC AC-5/G-6 versus CHANGE_PLAN D-2 and section 21.
- Failure: AC-5 requires a deferral notice, yet its text, stream and trigger are unspecified and it is cut early in scope cuts, so it cannot be asserted. Plan should say: one stderr line containing .gitignore and worktree, printed only when a tracked managed line differs from canonical; if cut, AC-5 drops that assertion.
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
