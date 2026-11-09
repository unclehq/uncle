# Verification report

## Findings

### MC-104

- **Action:** In a scratch git repo (main, no remote), sourced the real scripts/lib/run-policy.sh and called run_policy_change_branch (the guard change-workflow.sh runs before any stage) with WORKFLOW_WORKTREE=0: (1) from main; (2) re-ran on the created branch (resume); (3) from a feature branch feature/x. I did not run the full change-workflow.sh driver, to avoid launching agent stages.
- **Expected result:** Each first run prints `Branch: <name>` and `git branch --show-current` shows a new branch; the resume creates no further branch.
- **Actual result:** From main: printed `Branch: uncle/change`, current branch uncle/change, main SHA unchanged. Resume on uncle/change: no output, rc=0, branch list unchanged (main, uncle/change). From feature/x: printed `Branch: uncle/change-2`, current branch uncle/change-2, feature/x left intact.
- **Defects:** None

### MC-106

- **Action:** In a scratch git repo (/tmp/mc106.TOiw/repo, main, stub gh returning issue 7 'Add widget'), ran `from-issue.sh 7 --change --worktree --seed-only` (seed-only added so no agent driver started), then `from-issue.sh 7 --new --worktree`. Also ran `from-issue.sh 7 --worktree` without --change (mode derivation reached the agent step, which failed in the scratch environment; not relevant to the guard).
- **Expected result:** The first creates a worktree on a new branch as before; the second exits 1 with `--worktree and --worktree-dir require --change`.
- **Actual result:** First run printed 'Created worktree /tmp/mc106.TOiw/repo-issue-7 on branch uncle/add-widget' and wrote CHANGE_REQUEST.md; git worktree list shows the new worktree on uncle/add-widget. Second printed '--worktree and --worktree-dir require --change; --new is not supported.' plus usage, and exited 1 (exit status observed in an earlier invocation of the same form; the later PIPESTATUS capture was empty because of the pipeline). Caveats: the literal `N --worktree` without --change was not exercised for worktree creation, and the bare `--new --worktree` form without an issue number prints usage only.
- **Defects:** None

### MC-203

- **Action:** In a scratch git repo on main (no remote), invoked the change run guard run_policy_change_branch from scripts/lib/run-policy.sh (the first thing change-workflow.sh runs before any stage) with WORKFLOW_WORKTREE=0; listed branches and main SHA before and after. Did not launch the full agent workflow, only the guard it calls.
- **Expected result:** Run is on a new non-main branch, 'Branch: <name>' printed, main SHA unchanged, no other branch created/deleted.
- **Actual result:** Printed 'Branch: uncle/change'; current branch uncle/change; branches before: main; after: main, uncle/change. main SHA 74c909a4... before and after. run-branch marker written with uncle/change.
- **Defects:** None

### MC-204

- **Action:** Re-invoked the guard in the MC-203 repo (already on its recorded run branch). Separately, in two fresh scratch repos on main, planted .uncle/workflow/run-branch containing 'main' and 'ghost' (nonexistent) respectively and invoked the guard.
- **Expected result:** Resumed run creates no further branch; planted stale markers do not suppress the guard, so run moves to a new branch.
- **Actual result:** Resume: no output, rc=0, branches unchanged (main, uncle/change). Stale 'main' marker: printed 'Branch: uncle/change', now on uncle/change, main preserved. Stale 'ghost' marker: same result.
- **Defects:** None

### MC-206

- **Action:** In a scratch git repo (origin github.com/o/r, committed .uncle/config file) with a stub `gh` returning issue 7, ran `from-issue.sh 7 --change --worktree --seed-only` with UNCLE_PROJECT_ROOT set to the scratch repo; then ran `from-issue.sh 7 --new --worktree`. Also ran `from-issue.sh --new --worktree` literally.
- **Expected result:** The first creates a sibling worktree on a new branch with a copy of .uncle/config. The second exits 1 with '--worktree and --worktree-dir require --change'.
- **Actual result:** First run: 'Created worktree .../repo-issue-7 on branch uncle/scratch-thing'; git worktree list showed the sibling worktree on uncle/scratch-thing; its .uncle/config contained 'KEY=val' (a copy). Second run printed '--worktree and --worktree-dir require --change; --new is not supported.' followed by usage. Literal `--new --worktree` with no issue number instead printed 'Unrecognized issue argument: --new', so the message needs an issue number first. Exit codes were not captured (PIPESTATUS was empty in this shell); the message is printed immediately before an `exit 1` in scripts/from-issue.sh. Side effect: early runs that lacked UNCLE_PROJECT_ROOT created a stray worktree and branch uncle/scratch-thing in the real project, and one unexplained stray worktree reappeared after later runs. Both were removed with `git worktree remove --force` and `git branch -D`, and the final worktree list had no scratch entries.
- **Defects:** None

### MC-304

- **Action:** In a scratch git repo on main (no remote), with WORKFLOW_WORKTREE=0, invoked the same guard change-workflow.sh calls at startup (run_policy_change_branch from scripts/lib/run-policy.sh, sourced as change-workflow.sh does) rather than the full agent-driven run; then ran git branch --show-current and git branch.
- **Expected result:** Checkout is on a newly created branch, not main; a 'Branch: <name>' line printed; main unchanged.
- **Actual result:** Printed 'Branch: uncle/change'; current branch uncle/change; main commit SHA unchanged. The full change run with agent stages was not launched; only the startup branch guard was exercised.
- **Defects:** None

### MC-305

- **Action:** In the same scratch repo, re-invoked the run-policy branch guard (the resume path, run_policy_change_branch) while on the run branch, then ran git branch.
- **Expected result:** No further branch is created on resume.
- **Actual result:** No new branch created, no Branch line printed, and the checkout stayed on uncle/change. The branch listing was identical before and after. Resume was simulated by re-invoking the guard, not by stopping and resuming a real agent-driven run.
- **Defects:** None

### MC-306

- **Action:** In scratch repo /tmp/mc306/repo (main, origin=github.com/acme/widget, stub gh returning issue 7) ran `from-issue.sh 7 --change --worktree --seed-only`, then `git worktree list`/`git branch`. Then ran `from-issue.sh 7 --new --worktree` and the literal `from-issue.sh --new --worktree` (no issue number), recording exit codes.
- **Expected result:** First creates a worktree on a new branch as before. Second exits 1 with '--worktree and --worktree-dir require --change'.
- **Actual result:** First: exit 0, 'Created worktree /tmp/mc306/repo-issue-7 on branch uncle/stub'; worktree list shows the new worktree and branch uncle/stub; main untouched. Second (with issue number 7): exit 1, message '--worktree and --worktree-dir require --change; --new is not supported.' (starts with the expected text, plus a suffix and usage). The literal command without an issue number exits 1 with 'Unrecognized issue argument: --new' because the issue number is a required positional, so the checklist wording needs an <N> to reach the check. I added --change and --seed-only to the first run to avoid launching the full driver.
- **Defects:** None

### MC-401

- **Action:** Created a scratch git repo (/private/tmp/mc401.EbmyEG/proj, main, one commit, .uncle/config containing 'x', origin https://github.com/o/r.git) and a stub `gh` on PATH returning issue #7 'Fix widget'. Ran the repo's scripts/from-issue.sh with a clean env (env -i, UNCLE_PROJECT_ROOT set to the scratch repo, so the installed-runtime UNCLE_* variables did not redirect it): `from-issue.sh 7 --worktree --change --seed-only`. Then ran `git worktree list`, `git branch -a` and inspected the worktree's .uncle. Earlier attempts that inherited the worker env or used the real repo as project root failed for setup reasons (installed runtime root / real repo's pre-existing issue-7 worktree) and were discarded.
- **Expected result:** An opt-in issue worktree is created on a new branch exactly as before, with a copy of .uncle/config; no policy refusal or 'worktrees not used' notice appears.
- **Actual result:** Exit 0. Output: 'Preparing worktree (new branch 'uncle/fix-widget')', 'Created worktree /private/tmp/mc401.EbmyEG/proj-issue-7 on branch uncle/fix-widget', 'Freezing files attached to o/r#7', 'Wrote .uncle/docs/CHANGE_REQUEST.md'. git worktree list shows main and proj-issue-7 [uncle/fix-widget]; git branch shows the new branch uncle/fix-widget. The worktree's .uncle/config exists with content 'x' (copied). Output contained no refusal or 'worktrees not used' text (grep count 0). Only --seed-only was used, so the full workflow was not run. Scratch dir was not deleted (rm blocked by a safety check); it is left at /private/tmp/mc401.EbmyEG.
- **Defects:** None

### MC-402

- **Action:** In a scratch git repo ran `scripts/from-issue.sh 1 --new --worktree` (issue number required as first arg; a first attempt without it was rejected as an unrecognized argument and is not the tested path). Checked exit status, message, and compared the line in the script against HEAD.
- **Expected result:** Exits 1 with message `--worktree and --worktree-dir require --change`, unchanged from before.
- **Actual result:** Exit status 1. Message: `--worktree and --worktree-dir require --change; --new is not supported.` followed by usage. The message line is byte-identical to HEAD (scripts/from-issue.sh:543 in both HEAD and the working tree; git diff HEAD for that file is empty). The expected text is a prefix of the full message.
- **Defects:** None

### MC-403

- **Action:** Created a scratch git repo (branch main, bare remote origin, pushed, clean apart from an untracked CHANGE_REQUEST.md brief) and called worktree_auto from scripts/lib/worktrees.sh with WORKFLOW_WORKTREE unset and kind 'change'. This is the driver's default-worktree function, not the full ./scripts/change-workflow.sh launcher. Then ran git worktree list and git branch, and compared main's SHA before and after.
- **Expected result:** The change run still gets its default worktree on a new branch, and main's ref is unchanged.
- **Actual result:** worktree_auto printed a new worktree directory, <scratch>-change, on new branch uncle/change. git worktree list shows the original checkout on [main] and the new one on [uncle/change]. main stayed at 9776eb1b5e406047d32f0b0708e2c7d728405a01 before and after. Caveat: my harness sourced worktrees.sh from the scratch directory, so it printed a harmless 'state.sh: no such file' error. It did not affect the result. The full launcher was not run.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-104 | YES | PASS | Terminal output: 'main' -> 'Branch: uncle/change' -> 'uncle/change', 'main-sha-same'; resume 'rc=0' with 'main, * uncle/change'; feature run 'Branch: uncle/change-2' with branches feature/x, main, uncle/change, * uncle/change-2. .uncle/workflow/run-branch recorded uncle/change. |
| MC-106 | YES | PASS | git worktree list: /private/tmp/mc106.TOiw/repo a015d9a [main]; /private/tmp/mc106.TOiw/repo-issue-7 a015d9a [uncle/add-widget]. Message text begins with the expected string. |
| MC-203 | YES | PASS | Terminal output from scratch repo: before '* main'; after '  main / * uncle/change'; identical main SHA; rc=0. |
| MC-204 | YES | PASS | Terminal output: resume branch list 'main, * uncle/change'; both stale-marker repos show 'Branch: uncle/change' and '* uncle/change'. |
| MC-206 | YES | PASS | Terminal output as above. A first attempt with a directory-valued .uncle/config failed with 'Could not copy .uncle/config ... worktree removed', which was a fixture error (the real one is a file), not a product defect. Exit status 1 for the second command is inferred from the code, not observed. |
| MC-304 | YES | PASS | Console: 'Branch: uncle/change'; git branch: '  main' / '* uncle/change'; 'main same: yes'. |
| MC-305 | YES | PASS | git branch after resume: '  main' / '* uncle/change' (same as before). |
| MC-306 | YES | PASS | git worktree list: /private/tmp/mc306/repo 7027547 [main]; /private/tmp/mc306/repo-issue-7 7027547 [uncle/stub]. git branch: * main, + uncle/stub. Exit codes: A=0, B=1, C=1. |
| MC-401 | YES | PASS | Console output in /private/tmp/mc401.EbmyEG/out.txt; git worktree list: '/private/tmp/mc401.EbmyEG/proj 1caa073 [main]' and '/private/tmp/mc401.EbmyEG/proj-issue-7 1caa073 [uncle/fix-widget]'; ls -a proj-issue-7/.uncle: config docs workflow x; cat config: x. |
| MC-402 | YES | PASS | exit=1; stderr/stdout first line: '--worktree and --worktree-dir require --change; --new is not supported.'; git show HEAD:scripts/from-issue.sh line 543 equals working tree line 543; no diff for from-issue.sh. |
| MC-403 | YES | PASS | dir=.../scratch-change; 'Preparing worktree (new branch uncle/change)'; before=after=9776eb1b5e406047d32f0b0708e2c7d728405a01; git branch: '* main', '+ uncle/change'. |
