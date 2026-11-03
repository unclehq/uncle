# Verification report

## Findings

### MC-100

- **Action:** Read the checklist row only. Did not execute a real --worktree run of scripts/from-issue.sh: it needs a live agent CLI run to COMPLETE with no PR plus an interactive attended tty, which this non-interactive worker cannot provide.
- **Expected result:** No y/N prompt; worktree dir gone; main project on run branch with changed and untracked files; exactly one 'Branch <b>: worktree removed; project switched.' line.
- **Actual result:** Not performed. No observation made.
- **Defects:** None

### MC-101

- **Action:** Read the checklist row only. Did not execute the --unattended and piped-stdin no-PR COMPLETE runs, which require full real workflow runs in fresh scratch repos with an agent CLI.
- **Expected result:** Commit made, worktree removed, main switched, success summary printed once, no prompt, no 'Worktree ... kept; remove with:' line.
- **Actual result:** Not performed. No observation made.
- **Defects:** None

### MC-102

- **Action:** In two fresh scratch git repos, created a worktree on feat/x-1 with a new file and COMPLETE state, dirtied main (modified tracked hello.txt; untracked-only u.txt), then called finalize_no_pr_worktree from scripts/from-issue.sh (the no-PR COMPLETE finalization function) directly.
- **Expected result:** Worktree kept, main not switched, dirty file untouched, summary 'Branch <b>: worktree kept; project not switched.' with git switch <b> and scripts/lib/worktrees.sh remove <dir> printed.
- **Actual result:** Both variants: output 'Branch feat/x-1: worktree kept; project not switched.', 'Switch the project with: git switch feat/x-1', and 'remove with: scripts/lib/worktrees.sh remove <dir>'; rc=0. Worktree dir still exists; main still on 'main'; git status shows ' M hello.txt' (variant 1) and '?? u.txt' (variant 2). Note: exercised the finalizer directly rather than a full from-issue.sh run (the full-run equivalent is covered by driver green-check case no-pr-dirty-main-keeps / no-pr-untracked-main-keeps, FIXED).
- **Defects:** None

### MC-103

- **Action:** In scratch repos, (a) put main on branch 'other' (extra commit, not an ancestor of feat/x-1) and (b) detached main's HEAD, then called finalize_no_pr_worktree for a COMPLETE worktree with a new file.
- **Expected result:** Both cases keep the worktree and do not switch; summary says 'worktree kept; project not switched'; git switch <b> printed; main branch/detached HEAD unchanged.
- **Actual result:** Case (a): 'not an ancestor of feat/x-1' reason, summary 'Branch feat/x-1: worktree kept; project not switched.', 'git switch feat/x-1' printed; HEAD b6e0020e unchanged before/after, branch still 'other'. Case (b): 'not on a named branch' reason, same summary and switch hint; HEAD 58ee66d2 unchanged, branch empty (still detached). Worktrees exist in both. Same direct-function caveat as MC-102; full-run equivalents no-pr-other-branch-keeps and no-pr-detached-main-keeps pass in driver green-check.
- **Defects:** None

### MC-106

- **Action:** Read the fixture scenarios in scripts/tests/worktree-run-test.sh (pr-created removal, pr-created-driver-fails-keeps, pr-created-not-complete-keeps, no-pr-driver-fails-nothing-finalized, no-pr-already-on-run-branch) and cited the driver green-check result for that suite. Did not re-run the suite.
- **Expected result:** PR run auto-removes worktree with no commit or switch. Failure and non-COMPLETE runs commit, remove and switch nothing, with status equal to the driver's. Source already on run branch skips the switch and reports 'project switched'. Branch survives everywhere.
- **Actual result:** The green-check log records worktree-run-test.sh: 404 checks passed. The suite contains the cases above (pr-created-driver-fails-keeps expects status 3 and kept; pr-created-not-complete-keeps; no-pr-already-on-run-branch checks main on the run branch). I read the case definitions but did not read each assertion line by line.
- **Defects:** None

### MC-201

- **Action:** Cited the green-check for the existing no-pr-dirty-main-keeps (tracked modification) and no-pr-other-branch-keeps cases. Also ran a temporary copy of worktree-run-test.sh in /tmp (UNCLE_TEST_ALLOW_NESTED=1) with two extra cases: untracked-only file in main, and main on a detached HEAD. The copy lived outside the repo and the repo was not modified. The suite also now contains no-pr-untracked-main-keeps and no-pr-detached-main-keeps.
- **Expected result:** Each case keeps the worktree, does not switch main, leaves main file edits intact, prints exactly one 'Branch <b>: worktree kept; project not switched.' line plus the literal 'git switch <b>' command, and the branch still exists.
- **Actual result:** All assertions in the added untracked-only and detached cases passed. They covered kept worktree, main not switched (still main / still detached), local file intact, summary line, git switch line and branch exists. The only 5 failures in the temp copy were the unrelated concurrent-runs case, because the /tmp copy lacked the ./uncle launcher. The tracked-modification and non-ancestor branch cases pass in the green-check (404 checks passed). 'Exactly one' summary line is checked through expect_out containment, not a count.
- **Defects:** None

### MC-203

- **Action:** Read the checklist row, then inspected the driver green-check (bash scripts/run-shell-tests.sh = FIXED, no regressions) and the scripts/tests/worktree-run-test.sh cases that exercise this scenario. Did not re-run them, per policy.
- **Expected result:** Hook rejection keeps the worktree intact, prints 'worktree kept; project not switched.' and the remove command, with no --no-verify. Unreachable-source/symlink cases commit nothing, keep the worktree, and print the keep summary and remove command.
- **Actual result:** The driver-run suite covers both scenarios and passed. Case no-pr-commit-fails-keeps installs a rejecting pre-commit hook with untracked work. It asserts the summary is 'kept'/'not switched', 'Commit failed' and the worktrees.sh remove command are printed, the worktree is kept, and no commit is made. Case no-pr-unreachable-source-keeps makes the source cd fail with untracked work present. It asserts HEAD is unchanged, the worktree is kept, and the output contains 'the source checkout is unreachable', 'Branch feat/unreachable-42: worktree kept; project not switched.' and the remove command. The symlink alternative was not run live; the unreachable-source variant, which the row allows as an alternative, is covered. I did not confirm from the test source that --no-verify is absent.
- **Defects:** None

### MC-205

- **Action:** Read the checklist row, then inspected the driver green-check and the worktree-run-test.sh cases for unattended/pty/clean-tree/already-on-run-branch. Did not re-run them, per policy.
- **Expected result:** No 'Remove worktree ...? [y/N]' prompt and no old 'kept; remove with:' line in any mode. A clean tree creates no commit and still removes and switches. Main already on the run branch reports 'project switched' without error.
- **Actual result:** The driver-run suite covers these cases and passed. no-pr-switches asserts expect_not_out 'Remove worktree' and 'removed switched'. unattended-under-pty asserts no 'Remove worktree' prompt and no 'kept; remove with' line. no-pr-clean-tree-no-commit asserts exit status 0, 'removed switched' and main on the run branch. no-pr-already-on-run-branch asserts exit status 0, 'removed switched', the worktree removed and a single summary line. The attended-pty no-PR case with no prompt is covered only through the unattended-under-pty case; I did not find an attended no-PR pty case. I did not confirm that the clean-tree case compares HEAD before and after; it checks only the summary and branch state.
- **Defects:** None

### MC-301

- **Action:** Ran scripts/tests/worktree-run-test.sh (UNCLE_TEST_ALLOW_NESTED=1), which builds disposable scratch repos with stub gh/driver and runs from-issue.sh --worktree --unattended (no tty, stdin /dev/null) for no-PR COMPLETE cases, incl. case no-pr-clean-tree-no-commit and the committing case. I did not drive a hand-built scratch repo myself.
- **Expected result:** Same as attended: commit created, worktree removed, main switched to run branch, summary 'removed; switched', exit status equals driver's.
- **Actual result:** Suite exit 0, '404 checks passed'. Unattended no-PR cases asserted exit status 0, summary 'removed switched', and 'main on run branch' (src_branch == RB). Evidence is from the hermetic harness with a stub driver, not a manual run in a separate scratch repo; the driver-exit-propagation was covered by the suite's FAKE_DRIVER_EXIT cases, which I did not individually inspect.
- **Defects:** None

### MC-302

- **Action:** Built two scratch git repos (main with a tracked .gitignore and hello.txt; a linked worktree on feat/x holding new output). Dirtied main once with a modified tracked file (hello.txt) and once with an untracked-only file. Ran the real finalize_no_pr_worktree function, extracted verbatim from scripts/from-issue.sh lines 253-407 and sourced with scripts/lib/worktrees.sh, for each variant. This is the function-level no-PR COMPLETE path, not a full from-issue.sh run with a stub driver. Signing was disabled throughout.
- **Expected result:** Worktree kept, main not switched and the dirty files untouched. Output contains 'Branch <b>: worktree kept; project not switched.' plus literal 'git switch <b>' and 'scripts/lib/worktrees.sh remove <dir>' commands.
- **Actual result:** Both variants matched. Output: 'Committed 1 file(s) on branch feat/x.', 'Not removing <dir> or switching the project: the source checkout has uncommitted changes.', 'Branch feat/x: worktree kept; project not switched.', 'Switch the project with: git switch feat/x', 'Worktree <dir> kept; remove with: scripts/lib/worktrees.sh remove <dir>'. Afterwards main was still on 'main'. git status showed ' M hello.txt' (modified variant) and '?? local-untracked.txt' (untracked variant), so the dirty files were intact. The wt directory still existed.
- **Defects:** None

### MC-303

- **Action:** Same suite run: cases no-pr-other-branch-keeps (main moved to unrelated branch 'other' with its own commit) and no-pr-detached-main-keeps (main HEAD detached) run a no-PR COMPLETE worktree run unattended. Not a hand-built scratch repo.
- **Expected result:** Worktree kept, project not switched, one 'kept; not switched' summary line, manual 'git switch <b>' and remove commands printed; run branch still exists.
- **Actual result:** Both cases passed in the 404-check run: summary kept 'not switched', output contains 'git switch $RB', worktree dir kept, main still on 'other' / still detached. Remove command printed was asserted in the sibling dirty-main/failed-removal cases (scripts/lib/worktrees.sh remove), not explicitly in the other-branch case; run-branch existence and 'exactly one summary line' were not separately confirmed by me.
- **Defects:** None

### MC-304

- **Action:** In the clean main of the 'mod' scratch repo (hello.txt reverted), ran the printed recovery commands. First I ran 'git switch feat/x' in the order printed. Then I ran 'scripts/lib/worktrees.sh remove <dir>', which at first refused ('state is absent, not COMPLETE') because my scratch worktree had no .uncle/workflow/state. I wrote 'COMPLETE' there to match a real finished run and re-ran remove, then 'git switch feat/x'. Finally I ran 'git branch --list' and checked that out.txt was present.
- **Expected result:** Removal succeeds with 'Removed worktree <dir> (branch kept)', the branch remains, and git switch <b> succeeds showing the committed run output.
- **Actual result:** As printed, switch first: 'git switch feat/x' failed with "fatal: 'feat/x' is already used by worktree at <dir>" (rc 128) while the worktree still exists. After remove with COMPLETE state: 'Removed worktree <dir> (branch kept)' (rc 0); git branch --list showed '  feat/x' and '* main'; 'git switch feat/x' then returned "Switched to branch 'feat/x'" (rc 0); out.txt (the committed run output) and hello.txt were present. Every expected result held. One caveat: the recovery output prints the switch line before the remove line, and the switch only works once the worktree has been removed, so the printed order is misleading.
- **Defects:** None (advisory: printed 'git switch' hint precedes the worktree removal that it requires)

### MC-306

- **Action:** Ran scripts/tests/worktree-run-test.sh (UNCLE_TEST_ALLOW_NESTED=1) which builds scratch git repos with stub driver. Relevant cases: no-pr-commit-fails-keeps (rejecting pre-commit hook via core.hooksPath, COMPLETE no-PR run) and no-pr-driver-fails-nothing-finalized (driver exit 3).
- **Expected result:** Hook-rejected run: worktree kept with uncommitted output intact, 'kept; not switched' and remove command printed. Failed driver run: no commit, no removal, no switch, no summary line, exit status equals driver's.
- **Actual result:** Suite finished with 404 checks passed. Hook case: status 0, summary 'worktree kept; project not switched.', 'Commit failed' and 'scripts/lib/worktrees.sh remove' printed, worktree dir kept, no uncle commit on run branch. Failed-driver case: exit status 3, no 'Branch ...: worktree' summary line, worktree kept, no commit, main still on main. Note: the check that uncommitted output remains intact is only indirect (worktree dir kept, no commit).
- **Defects:** None

### MC-401

- **Action:** Ran a temporary copy of the worktree suite (/tmp/mc401/t.sh) adding assertions after the pr-created-removes-{unattended,pty,pipe} cases: stub driver ends COMPLETE with a fresh journal (phase created, matching head_branch and URL); checked output, filesystem and git state.
- **Expected result:** Worktree removed, run branch exists, no prompt, no new commit on run branch, main not switched, no 'Branch ...:' summary line.
- **Actual result:** All pass in all three modes: worktree dir removed ('Removed worktree ... (branch kept)'), branch feat/add-widget-42 exists, no 'Remove worktree' prompt, run branch HEAD is still the fake driver's commit with no 'uncle: issue 42' commit, source checkout stays on main, no 'Branch feat/add-widget-42:' line printed. The suite reported 416 checks passed (404 plus 12 added probe checks). Branch HEAD sha was not compared before/after literally; HEAD subject equality used instead.
- **Defects:** None

### MC-402

- **Action:** Did not run live --worktree runs (they need a real driver). Inspected scripts/tests/worktree-run-test.sh and the driver green-check log, which exercise these cases with a fake driver.
- **Expected result:** Worktree kept with uncommitted output when the driver exits non-zero or the final state is not COMPLETE; no commit, main project not switched, no no-PR summary line, script exit status equals driver's.
- **Actual result:** The shell suite includes cases 'pr-created-driver-fails-keeps' (FAKE_DRIVER_EXIT=3, expect_status 3, expect_kept), 'pr-created-not-complete-keeps' (FAKE_STATE=IMPLEMENT, expect_kept), and an unpushed-plus-driver-fail case. The driver green-check shows 'worktree-run-test.sh: 404 checks passed' and 'Shell suites: 215 passed, 0 failed, 0 skipped'. The suite's coverage of 'no commit' and 'no summary line' on these paths was not individually confirmed.
- **Defects:** None

### MC-403

- **Action:** Did not run live PR-created --worktree runs. Inspected worktree-run-test.sh and the driver green-check log for the untracked-file and unpushed-commit refusal cases.
- **Expected result:** Worktree kept; refusal strings 'the worktree contains untracked files' and 'the worktree has N commit(s) not pushed to a remote' unchanged; 'Worktree <dir> kept; remove with: scripts/lib/worktrees.sh remove <dir>' line printed.
- **Actual result:** The suite has 'pr-created-untracked-refused-{unattended,pty}' (FAKE_UNTRACKED=1: expect_kept, expect_not_out 'Remove worktree', expect_out 'scripts/lib/worktrees.sh remove') and unpushed cases (FAKE_UNPUSHED=1: expect_out 'not pushed to a remote', lines 916-979). 'pr-created-dirty-refused' asserts the exact 'Worktree <dir> kept; remove with: scripts/lib/worktrees.sh remove' line. The green-check log shows the whole suite passing. The exact untracked-files refusal string assertion was not individually confirmed.
- **Defects:** None

### MC-404

- **Action:** In a disposable git repo (signing disabled) created three COMPLETE worktrees: wt-a with .uncle/workflow/lock, wt-b with a dirty tracked file, wt-c clean with no lock (.uncle gitignored). Ran `bash scripts/lib/worktrees.sh remove <dir>` on each, then `git worktree list` and `git branch --list`.
- **Expected result:** First two refuse with existing messages and keep worktree; third removes and prints `Removed worktree <dir> (branch kept)`; branch survives.
- **Actual result:** wt-a: 'Refusing to remove <dir>: a run holds .uncle/workflow/lock', exit 1, worktree kept. wt-b: git 'contains modified or untracked files' + 'git worktree remove refused <dir>; worktree kept', exit 1, kept. wt-c (clean, fresh fixture): 'Removed worktree <dir> (branch kept)', exit 0; worktree list showed only main; branch br-c still listed.
- **Defects:** None

### MC-405

- **Action:** Inspected scripts/from-issue.sh no-PR path (calls finalize_no_pr_worktree with no prompt; 'kept; remove with' lines appear only in the PR_CREATED==1 branch). Did not perform a live no-PR COMPLETE --worktree run under a pty and with --unattended.
- **Expected result:** No 'Remove worktree <dir>? [y/N]' prompt and no 'Worktree <dir> kept; remove with:' line on the no-PR path; single final line 'Branch <b>: worktree removed; project switched.'; exit status matches driver's.
- **Actual result:** Not executed live. A real run needs a full change-workflow driver with agent CLIs, a GitHub issue and a pty harness, which this lane cannot set up; the fixture suite scripts/tests/worktree-run-test.sh is covered only by the driver green-check, not a live observation of captured pty/unattended transcripts.
- **Defects:** None. Setup needed: a real or stubbed-driver no-PR COMPLETE --worktree run on a clean project, executed once under a pty and once with --unattended, with transcripts captured.

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | YES | BLOCKED-HUMAN | None. Driver green-check may cover related script tests but does not replace this live attended end-to-end observation. |
| MC-101 | YES | NOT RUN | None. |
| MC-102 | YES | PASS | Console output of scratch script; ls -d of worktree succeeded; git status --short and branch --show-current after run. |
| MC-103 | YES | PASS | Console output with before/after rev-parse HEAD and branch --show-current; ls -d of worktrees. |
| MC-106 | YES | PASS | .uncle/workflow/logs/green-check.log line 1054 ('404 checks passed'); .uncle/workflow/green-check.md (no regressions); scripts/tests/worktree-run-test.sh lines ~742-747 and ~1050-1130. |
| MC-201 | YES | PASS | Temp-run output: 'worktree-run-test.sh: 5 of 417 checks failed', all concurrent-runs ('/tmp/mc2/uncle: No such file'); no x-untracked-only-main or x-detached failures. green-check.log line 1054. /tmp/mc2 and /tmp/mc201 left behind because the rm was denied by a safety check. |
| MC-203 | YES | PASS | .uncle/workflow/green-check.md (FIXED, no regressions); scripts/tests/worktree-run-test.sh lines 1052-1089 (no-pr-commit-fails-keeps, no-pr-unreachable-source-keeps). No separate live transcript was captured; the result relies on driver-run automated evidence. |
| MC-205 | YES | PASS | .uncle/workflow/green-check.md (FIXED); scripts/tests/worktree-run-test.sh lines 676-683, 994-1010, 1115-1128. No separate live transcript was captured; the result relies on driver-run automated evidence. |
| MC-301 | YES | PASS | /tmp/wt141.out tail: 'worktree-run-test.sh: 404 checks passed'; test source scripts/tests/worktree-run-test.sh lines ~1005-1010 (no-pr-clean-tree-no-commit) and the preceding commit case. |
| MC-302 | YES | PASS | Transcript of both runs in this session. Main status after the modified run: ' M hello.txt'. After the untracked run: '?? local-untracked.txt'. Directory listing in each case: proj, wt. Scratch dir path is in /tmp/mc302dir. |
| MC-303 | YES | PASS | /tmp/wt141.out: 404 checks passed, exit 0; test source lines ~1022-1030 (no-pr-other-branch-keeps) and ~1102-1111 (no-pr-detached-main-keeps). |
| MC-304 | YES | PASS | Command transcripts in this session: the initial switch failure with its fatal message, the first remove refusal caused by my missing state file, and the second run with remove rc=0, branch list '  feat/x / * main', switch rc=0, and ls showing hello.txt and out.txt. Not a verified application defect against the stated expected result, but the ordering caveat should be noted. |
| MC-306 | YES | PASS | Suite output 'worktree-run-test.sh: 404 checks passed'; assertions at scripts/tests/worktree-run-test.sh lines ~1052-1062 and ~1130-1136. |
| MC-401 | YES | PASS | Output 'MC401 probe unattended ok / pty ok / pipe ok' and 'worktree-run-test.sh: 416 checks passed'. |
| MC-402 | YES | PASS | .uncle/workflow/green-check.md (bash scripts/run-shell-tests.sh: FIXED, no regressions); .uncle/workflow/logs/green-check.log lines 1054-1056; scripts/tests/worktree-run-test.sh lines ~742-750, 499-505, 924. This is automated fake-driver evidence, not a live run. |
| MC-403 | YES | PASS | .uncle/workflow/logs/green-check.log lines 1054-1056; scripts/tests/worktree-run-test.sh lines ~790-830, 905-980. This is automated fake-driver evidence, not a live run. |
| MC-404 | YES | PASS | Command transcripts from /tmp/mc404.sh (a,b) and /tmp/mc404c.sh (c) with exit codes and git worktree list / git branch --list output as above. Note: in the first combined fixture wt-c was refused only because the fixture's untracked .uncle dir was not gitignored; that was a fixture artifact, corrected in the rerun. |
| MC-405 | YES | BLOCKED-SETUP | Source read of scripts/from-issue.sh lines ~955-980 only; green-check.md shows FIXED for run-shell-tests.sh and run-python-tests.sh, which is not a pty transcript. |
