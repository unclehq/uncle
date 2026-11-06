# Verification report

## Findings

### MC-101

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** test_tui_reload_leaves_gitignore_unchanged calls _ensure_uncle_gitignored 3x; .gitignore unchanged, exclude has block once. TUI launch, touch .uncle/config and project switch not driven.
- **Defects:** None

### MC-102

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** test_deferral_notice_once_per_root: one notice over 3 calls, .gitignore unchanged. Reload/switch not driven.
- **Defects:** None

### MC-104

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** test_clean_passes_silently covers guard on clean tree only.
- **Defects:** None

### MC-105

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** Guard tests test_extra_staged_paths_fail_naming_both and test_gitignore_managed_line_only_difference_fails pass via sourced assert_tree_matches_attested; no real publish. Note managed-line test does not stage the change.
- **Defects:** None

### MC-106

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** pr-auto-publish-test.sh passed in driver output.log line 448-450 (10 checks, incl. 2 new for AC-3); real post-PR flow not run.
- **Defects:** None

### MC-107

- **Action:** Ran fixture test test_visibility_root_and_linked_worktree (git check-ignore in root and linked worktree).
- **Expected result:** per checklist.
- **Actual result:** Test passed; `python3 -B scripts/tests/gitignore-clean-end-test.py -v` exit 0, 16 tests OK (run by me).
- **Defects:** None

### MC-200

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-101.
- **Defects:** None

### MC-201

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-102.
- **Defects:** None

### MC-203

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-104.
- **Defects:** None

### MC-204

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-105 (guard only).
- **Defects:** None

### MC-206

- **Action:** Ran fixture test test_visibility_root_and_linked_worktree + test_legacy_bare_uncle_hides_docs_until_worktree_normalizes (git check-ignore in root and linked worktree).
- **Expected result:** per checklist.
- **Actual result:** Test passed; `python3 -B scripts/tests/gitignore-clean-end-test.py -v` exit 0, 16 tests OK (run by me).
- **Defects:** None

### MC-207

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-106; dependency MC-202 is not in the checklist.
- **Defects:** None

### MC-300

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-101; second repo not exercised.
- **Defects:** None

### MC-301

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-102.
- **Defects:** None

### MC-303

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** guard-level only; its dependency MC-302 is not in the checklist.
- **Defects:** None

### MC-304

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-106.
- **Defects:** None

### MC-305

- **Action:** Ran fixture test test_visibility_root_and_linked_worktree (check-ignore rc: workflow 0, docs/attestation 1, both checkouts) (git check-ignore in root and linked worktree).
- **Expected result:** per checklist.
- **Actual result:** Test passed; `python3 -B scripts/tests/gitignore-clean-end-test.py -v` exit 0, 16 tests OK (run by me).
- **Defects:** None

### MC-401

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-101; docs-visible part covered by test_visibility_root_and_linked_worktree.
- **Defects:** None

### MC-402

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-102.
- **Defects:** None

### MC-404

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** no end-to-end run with PR.
- **Defects:** None

### MC-405

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-105 (guard only).
- **Defects:** None

### MC-406

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** guard tests cover clean and dirty (no_attestation_dirty_tracked) cases; no run completion.
- **Defects:** None

### MC-407

- **Action:** No live run. Fixture/function tests only.
- **Expected result:** per checklist.
- **Actual result:** same as MC-106.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. test_tui_reload_leaves_gitignore_unchanged calls _ensure_uncle_gitignored 3x; .gitignore u |
| MC-102 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. test_deferral_notice_once_per_root: one notice over 3 calls, .gitignore unchanged. Reload/ |
| MC-104 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. test_clean_passes_silently covers guard on clean tree only. |
| MC-105 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. Guard tests test_extra_staged_paths_fail_naming_both and test_gitignore_managed_line_only_ |
| MC-106 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. pr-auto-publish-test.sh passed in driver output.log line 448-450 (10 checks, incl. 2 new f |
| MC-107 | YES | PASS | test_visibility_root_and_linked_worktree passed, exit 0 |
| MC-200 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-101. |
| MC-201 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-102. |
| MC-203 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-104. |
| MC-204 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-105 (guard only). |
| MC-206 | YES | PASS | test_visibility_root_and_linked_worktree + test_legacy_bare_uncle_hides_docs_until_worktree_normalizes passed, exit 0 |
| MC-207 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-106; dependency MC-202 is not in the checklist. |
| MC-300 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-101; second repo not exercised. |
| MC-301 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-102. |
| MC-303 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. guard-level only; its dependency MC-302 is not in the checklist. |
| MC-304 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-106. |
| MC-305 | YES | PASS | test_visibility_root_and_linked_worktree (check-ignore rc: workflow 0, docs/attestation 1, both checkouts) passed, exit 0 |
| MC-401 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-101; docs-visible part covered by test_visibility_root_and_linked_worktree. |
| MC-402 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-102. |
| MC-404 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. no end-to-end run with PR. |
| MC-405 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-105 (guard only). |
| MC-406 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. guard tests cover clean and dirty (no_attestation_dirty_tracked) cases; no run completion. |
| MC-407 | YES | BLOCKED-SETUP | Live TUI/change run needed; action: run attended with real runner. same as MC-106. |
