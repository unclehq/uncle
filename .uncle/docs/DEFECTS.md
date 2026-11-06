# Defects

## MC-101

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. test_tui_reload_leaves_gitignore_unchanged calls _ensure_uncle_gitignored 3x; .gitignore u
- **Expected result:** per checklist.
- **Actual result:** test_tui_reload_leaves_gitignore_unchanged calls _ensure_uncle_gitignored 3x; .gitignore unchanged, exclude has block once. TUI launch, touch .uncle/config and project switch not driven.

## MC-102

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. test_deferral_notice_once_per_root: one notice over 3 calls, .gitignore unchanged. Reload/
- **Expected result:** per checklist.
- **Actual result:** test_deferral_notice_once_per_root: one notice over 3 calls, .gitignore unchanged. Reload/switch not driven.

## MC-104

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. test_clean_passes_silently covers guard on clean tree only.
- **Expected result:** per checklist.
- **Actual result:** test_clean_passes_silently covers guard on clean tree only.

## MC-105

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. Guard tests test_extra_staged_paths_fail_naming_both and test_gitignore_managed_line_only_
- **Expected result:** per checklist.
- **Actual result:** Guard tests test_extra_staged_paths_fail_naming_both and test_gitignore_managed_line_only_difference_fails pass via sourced assert_tree_matches_attested; no real publish. Note managed-line test does not stage the change.

## MC-106

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. pr-auto-publish-test.sh passed in driver output.log line 448-450 (10 checks, incl. 2 new f
- **Expected result:** per checklist.
- **Actual result:** pr-auto-publish-test.sh passed in driver output.log line 448-450 (10 checks, incl. 2 new for AC-3); real post-PR flow not run.

## MC-200

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-101.
- **Expected result:** per checklist.
- **Actual result:** same as MC-101.

## MC-201

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-102.
- **Expected result:** per checklist.
- **Actual result:** same as MC-102.

## MC-203

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-104.
- **Expected result:** per checklist.
- **Actual result:** same as MC-104.

## MC-204

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-105 (guard only).
- **Expected result:** per checklist.
- **Actual result:** same as MC-105 (guard only).

## MC-207

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-106; dependency MC-202 is not in the checklist.
- **Expected result:** per checklist.
- **Actual result:** same as MC-106; dependency MC-202 is not in the checklist.

## MC-300

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-101; second repo not exercised.
- **Expected result:** per checklist.
- **Actual result:** same as MC-101; second repo not exercised.

## MC-301

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-102.
- **Expected result:** per checklist.
- **Actual result:** same as MC-102.

## MC-303

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. guard-level only; its dependency MC-302 is not in the checklist.
- **Expected result:** per checklist.
- **Actual result:** guard-level only; its dependency MC-302 is not in the checklist.

## MC-304

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-106.
- **Expected result:** per checklist.
- **Actual result:** same as MC-106.

## MC-401

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-101; docs-visible part covered by test_visibility_root_and_linked_worktree.
- **Expected result:** per checklist.
- **Actual result:** same as MC-101; docs-visible part covered by test_visibility_root_and_linked_worktree.

## MC-402

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-102.
- **Expected result:** per checklist.
- **Actual result:** same as MC-102.

## MC-404

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. no end-to-end run with PR.
- **Expected result:** per checklist.
- **Actual result:** no end-to-end run with PR.

## MC-405

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-105 (guard only).
- **Expected result:** per checklist.
- **Actual result:** same as MC-105 (guard only).

## MC-406

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. guard tests cover clean and dirty (no_attestation_dirty_tracked) cases; no run completion.
- **Expected result:** per checklist.
- **Actual result:** guard tests cover clean and dirty (no_attestation_dirty_tracked) cases; no run completion.

## MC-407

- **Status:** BLOCKED-SETUP
- **Evidence:** Live TUI/change run needed; action: run attended with real runner. same as MC-106.
- **Expected result:** per checklist.
- **Actual result:** same as MC-106.
