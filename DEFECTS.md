## Summary

See VERIFICATION_REPORT.md for all 12 dispositions.
E = /tmp/uncle-primary-verify-2103; verification made no product-source edits.

## Findings

| ID | Classification | Evidence and disposition |
|---|---|---|
| F-1 | Critical acceptance failure; MC-001/002/007 | scripts/lib/change-pr.sh:338–339 requests empty summary/manual input. E/MC-001-*.log rejects 12 usable-source defaults with "must be nonempty"; 20 edits succeed. E/MC-002.log rejects four regular-blob defaults without leaking external contents. Implement P-6–9 after STOP-1 resolution. |
| F-2 | Important acceptance failure; MC-005/007 | uncle_tui.py:_detect_prompt lacks P-11 framing. E/MC-005.log, exit 1: 342 framing failures; embedded terminator yields buffer "café " before completion. CLI editing passes (E/MC-005-cli.log, exit 0). Implement length framing and full-buffer assertions. |
| F-3 | Critical checklist/contract mismatch; MC-004 | E/MC-004*.log shows UNATTENDED=1 still prompts in directory/worktree fixtures; --unattended suppresses both. scripts/change-workflow.sh:62 resets the variable and :67 parses the option; E/MC-004-contract.log finds the same contract in HEAD. Correct the invocation or approve environment-variable support. |
| F-4 | Important suite failure; MC-012 | bash scripts/tests/document-budget-test.sh exits 1. E/MC-012-budget-diagnostic.log: "can't open file" standalone/scripts/lib/repair-acceptance.py. scripts/lib/gates.sh:399 now invokes that helper; scripts/tests/document-budget-test.sh:164 omits it from its copied fixture. Repair the fixture after E-3. |
| F-5 | Important fixture failure; MC-012 | bash scripts/tests/background-performance-test.sh exits 1. E/MC-012-background-performance.log: "PROJECT_ROOT: unbound variable", then test line 32 fails before cancellation is exercised. Supply the fixture prerequisite; cancellation remains unverified. |
| E-1 | BLOCKED-SETUP; MC-010 | Adapter suite exits 1: "tee: /dev/fd/63: Operation not permitted"; usage assertion receives empty output. Run bash scripts/tests/agent-codex-test.sh through the unrestricted driver. 32-case matrix/jq validation pass; driver evidence does not cover this suite. |
| E-2 | BLOCKED-SETUP; MC-011/012 | Provide a Git Bash runner for the required Windows executions. Bash 3.2.57/Python 3.14.7 and 3.9.6 isolation pass (E/MC-011-*.log, MC-012-min-env.log); Windows remains untested. |
| E-3 | BLOCKED-SETUP; MC-008/009 | Freeze and reconcile the candidate, then rerun affected verification. E/MC-009-final.log records new gates.sh, stagegate.sh, review-compaction-test.sh edits and untracked repair-acceptance.py beyond the supplied diff. Excluding these tracked edits plus MANUAL_CHECKLIST.md restores IMPLEMENTATION_NOTES.md U-6 digest; C-1–4 diff remains empty. Attribution is unknown. |
| H-1 | BLOCKED-HUMAN; MC-006/012 | Brian must resolve CHANGE_PLAN.md R-2 and supply a disposable GitHub account/repository, merge permission and acceptance. No live issue, merge, separate comment or sign-off evidence exists. |
| H-2 | BLOCKED-HUMAN; MC-005/012 | Brian must exercise and inspect full TUI keyboard editing. Parser/CLI checks do not establish TUI interaction. |
| H-3 | BLOCKED-HUMAN; MC-012 | Brian must approve applicable lint/type commands and performance thresholds (MANUAL_CHECKLIST.md AS-4). Syntax/AST and performance instrumentation tests pass; no approved latency threshold was tested. |

## Assumptions

| ID | Unverified item | Settled by |
|---|---|---|
| A-1 | No attribution or historical runtime classification for F-4/5 and E-3 | Fixed-snapshot comparison and owner disposition |

## Open questions

| ID | Required disposition |
|---|---|
| Q-1 | CT-5/6 map to MC-001/002/005/007 failures; CT-11 to H-1; CT-16 to MC-002; CT-19 to MC-001–006. |
| Q-2 | CT-7 native commands and CT-9 syntax/AST are in E/MC-012-results.tsv; CT-10 and CT-15 threshold acceptance await H-3. |
| Q-3 | MC-011 sequential/parallel elapsed seconds: 0.050/0.095 with sentinels, 0.047/0.094 unset; no speed criterion was approved. |
