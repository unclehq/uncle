# Implementation notes

## Step 1

### Files changed

- `scripts/lib/uncle_gitignore.py` — add ensure_exclude (marked canonical block in shared info/exclude, symlink/outside-common-dir refusal, atomic write, False-not-raise), tracked_needs_normalization and _exclude_text_current; S1 / D-1, D-1a; G-4, G-6, P-1, I-3
- `uncle_tui.py` — _ensure_uncle_gitignored calls only ensure_exclude; one deferral notice per root per process, one warning per process when the exclude cannot be written; S2 / D-2; G-6, I-3
- `scripts/lib/change-pr.sh` — add assert_tree_matches_attested (clean tracked status, attested-tree comparison, .uncle allowlist, ignored-docs check); call at publish before handoff and at the no-PR completion path; add commit-tree engine action; S3 / D-4, D-4a, D-6; G-1, G-2, G-5, I-1, I-2, I-4
- `scripts/tests/gitignore-clean-end-test.py` — new: ensure_exclude table tests, symlink refusals, linked-worktree visibility, ensure() caller enumeration, TUI helper tests (incl. test_tui_reload_leaves_gitignore_unchanged), guard tests; S1-S3 (consolidated into one file); AC-1, AC-2, AC-4, AC-5, AC-7
- `scripts/tests/pr-auto-publish-test.sh` — add clean-tree and dirty-tracked-file checks for auto_removal_content_refusal; S4; G-3, I-4

### Deviations

- `scripts/tests/gitignore-clean-end-test.py`: The plan splits tests across gitignore-clean-end-test.py, gitignore-tui-test.py and gitignore-publish-guard-test.py; all three groups are in the single first file. The two other files were not created.
- `scripts/lib/change-pr.sh`: The attestation signature is not re-verified in the guard (R-2/AR-015) because attestation.py exposes no verify function. The guard compares to journal commit_tree, which validate() already binds to the audit. The legacy-snapshot strip_managed mode is not implemented; the guard always compares exact bytes. A file of the change that exists on disk but is untracked is not reported as a difference.
- `.gitignore`: The checkout already held an uncommitted stray '.uncle' line appended by earlier bookkeeping, which is the bug's symptom. It was left untouched, not authored by this change.
- `scripts/tests/gitignore-clean-end-test.py`: AC-6 mutations M-1 and M-2 were run in a throwaway copy at /tmp/m1 by hand, not by a committed S4 script. Results are in CHANGE_TEST_REPORT.json.

### Unresolved concerns

- Attestation signature verification in the guard is not implemented (no verify API in attestation.py).
- Legacy-snapshot strip_managed tolerance mode at publish (R-5) is not implemented.
- No live end-to-end change run was performed; the manual check (main checkout clean, worktree auto-removed after PR) is unobserved.
- worktree-run-test.sh self-skips while an uncle build drives the checkout; run with UNCLE_TEST_ALLOW_NESTED=1 outside the build to cover worktree creation.
- The change plan's frozen scope lists only .gitignore, but the real surface is the files above.

## Driver-recorded scope deviations

### Deviations

- `scripts/lib/uncle_gitignore.py`: Changed outside the plan's change-impact table. Recorded by the driver because this run was unattended and the implementation did not record it; the implementation notes may explain it in prose. Review it in the diff.
- `scripts/tests/pr-auto-publish-test.sh`: Changed outside the plan's change-impact table. Recorded by the driver because this run was unattended and the implementation did not record it; the implementation notes may explain it in prose. Review it in the diff.
- `uncle_tui.py`: Changed outside the plan's change-impact table. Recorded by the driver because this run was unattended and the implementation did not record it; the implementation notes may explain it in prose. Review it in the diff.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | scripts/lib/change-pr.sh assert_tree_matches_attested, called at publish and at the no-PR completion path | python3 -B scripts/tests/gitignore-clean-end-test.py: 16 tests OK (Guard cases: clean passes silently, dirty tracked fails naming the file, untracked artifacts do not fail) |
| AC-2 | IMPLEMENTED | scripts/lib/change-pr.sh assert_tree_matches_attested compares tracked paths to the attested tree and rejects non-allowlisted .uncle paths | gitignore-clean-end-test.py Guard tests: managed-line-only .gitignore difference fails; staged .uncle/secret and extra.txt both named on stderr; with the guard no-op'd (M-2) 4 Guard tests fail |
| AC-3 | IMPLEMENTED | scripts/tests/pr-auto-publish-test.sh covers auto_removal_content_refusal; scripts/from-issue.sh is unchanged | bash scripts/tests/pr-auto-publish-test.sh: 10 checks passed |
| AC-4 | IMPLEMENTED | scripts/lib/uncle_gitignore.py ensure_exclude; ensure() is kept for worktrees.sh:130 only | gitignore-clean-end-test.py test_cases_replace_with_one_block_and_keep_user_lines and test_only_worktree_creation_runs_ensure pass |
| AC-5 | IMPLEMENTED | uncle_tui.py _ensure_uncle_gitignored uses ensure_exclude only, plus a once-per-root deferral notice | gitignore-clean-end-test.py test_tui_reload_leaves_gitignore_unchanged and test_deferral_notice_once_per_root pass; the helper is called directly, load_config/reload/project switch are not each driven separately |
| AC-6 | IMPLEMENTED | no product change; defect injection in throwaway copy /tmp/m1 | M-1 (re-add uncle_gitignore.ensure in _ensure_uncle_gitignored): gitignore-clean-end-test.py FAILED (failures=5) incl. test_tui_reload_leaves_gitignore_unchanged; M-2 (guard return 0): FAILED (failures=9) |
| AC-7 | IMPLEMENTED | ensure_exclude writes the unchanged CANONICAL block | gitignore-clean-end-test.py test_visibility_root_and_linked_worktree: .uncle/workflow ignored; .uncle/docs and attestation.json visible via git check-ignore in root and linked worktree; legacy bare .uncle hides docs (documented) |
