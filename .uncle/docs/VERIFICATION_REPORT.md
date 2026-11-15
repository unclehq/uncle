# Verification report

## Findings

### MC-200

- **Action:** Ran the real change_pr_engine handoff (scripts/lib/change-pr.sh) in a disposable fixture repo with UNCLE_NO_FOOTPRINT=1 (no-footprint mode, journal no_footprint=true) and a READY frozen/bound audit. First sent empty stdin, then answered the prompts (default title, summary, manual steps) and answered 'n' at the publication consent prompt. Used a temporary probe in /tmp/mc200 that reuses the pr-auto-commit-test fixtures (fake gh and git shims, signing disabled).
- **Expected result:** The prompt requires an explicit decision, and declining leaves the completed work available locally without publishing or treating that decision as a verification failure.
- **Actual result:** With empty input the engine printed the audited diff and title prompt, then 'PR pending: No answer received; PR remains pending. Rerun to resume.' No commit and no PR were created. After 'n' at 'Commit and publish exactly this audited diff and create the PR? [y/n]:' it printed 'PR pending: Publication declined; rerun to resume PR handoff.' It exited with returncode 1 as a pending state, and no commits, commit-tree calls or gh pr create calls were made. HEAD stayed equal to the original, the journal phase stayed 'bound' (resumable), and the audited working-tree change in source.txt ('audited') was kept locally. The exit is non-zero, and this check did not run the driver's gate handling, so I did not observe how the driver classifies that non-zero exit (for example, whether it counts as a verification failure).
- **Defects:** None

### MC-400

- **Action:** Read the checklist row and inspected scripts/lib/change-pr.sh for the publication prompt path. Did not run an interactive default-mode workflow, because it needs live human approvals and a human answering the publication prompt.
- **Expected result:** Declining publication preserves successful completion and does not trigger publication or require repeating completed verification or approvals.
- **Actual result:** Not observed. The row needs a complete interactive default-mode run (--no-footprint omitted, UNCLE_NO_FOOTPRINT unset) with human-gated approvals and a person declining the optional publication offer at the terminal. A worker cannot supply that. The code shows an interactive publish consent path (change_pr_publish 1) but no run was observed, so no pass or fail is claimed.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-200 | YES | PASS | Probe output: 'EMPTY rc 1 ... PR pending: No answer received'; 'DECLINE rc 1 ... PR pending: Publication declined; rerun to resume PR handoff.'; 'creates 0 commits [] head==orig True'; 'journal bound True'; 'source.txt audited'. The probe's unittest run passed (Ran 1 test, OK). Source: scripts/lib/change-pr.sh lines ~2018-2023. |
| MC-400 | YES | BLOCKED-HUMAN | MANUAL_CHECKLIST.json row MC-400; scripts/lib/change-pr.sh (change_pr_publish, lines ~239-276). No terminal observation of the decline path. |
