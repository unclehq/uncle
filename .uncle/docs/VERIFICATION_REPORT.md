# Verification report

## Findings

### MC-100

- **Action:** In the dirty working tree (git status shows many modified files), ran scripts/stagegate.sh and scripts/change-workflow.sh with --version, --help and -h; captured output and exit codes.
- **Expected result:** Each version call prints 0.1.0 and exits 0; each help call prints usage mentioning --unattended and exits 0, with no run-policy refusal.
- **Actual result:** All six invocations exited 0 (the checklist says eight; the two scripts times three flags make six, and the check named only these flags). --version printed '0.1.0' (1 line) for both scripts. --help and -h printed usage on both scripts, starting 'Usage: ...sh [-h|--help] [--version] [--attended] [--unattended]', and the output mentions --unattended (1 line in stagegate, 2 in change-workflow). No refusal message was seen.
- **Defects:** None

### MC-105

- **Action:** Hashed .gitignore (f65fdeed...), ran attestation-statement-test.py with a .uncle line and with it removed, restored from backup and re-hashed.
- **Expected result:** Both runs pass; .gitignore hash identical after restoration.
- **Actual result:** Run 1 (.uncle present): 13 tests, FAILED (failures=1, errors=2). Run 2 (clean): FAILED (errors=13). Shell reported 'no space left on device' (ENOSPC) during writes; volume at 100% (249Mi free). Failures are not attributable to the application. Restored .gitignore hash equals original (f65fdeed...), cmp byte-identical.
- **Defects:** None. Action: free disk space on the host volume, then rerun.

### MC-106

- **Action:** Ran scripts/tests/worktree-run-test.sh with a restricted PATH (/tmp/nogit containing only bash, env, dirname) so required tools were absent. Ran twice: once plain, once with UNCLE_TEST_ALLOW_NESTED=1 to get past the nested-build guard. Also grepped the repo for the string 'missing prerequisite'.
- **Expected result:** stderr contains `missing prerequisite: <tool>`, exit is nonzero and not 127, and it is reported as FAILED, never passed or skipped.
- **Actual result:** Plain run: stdout said 'skipped, an uncle build is driving this checkout', exit 77, stderr empty. That is a skip, not a failure. With UNCLE_TEST_ALLOW_NESTED=1: exit 1, stderr was 'line 59: mktemp: command not found' and 'worktree-run-test.sh: mktemp -d failed'. No 'missing prerequisite: <tool>' text appeared. The grep found no emitter of that string in scripts/; the only hits were in docs and prompts.
- **Defects:** Missing-tool handling in worktree-run-test.sh does not emit 'missing prerequisite: <tool>'. Without the nested override the suite exits 77 (skip). No DEFECTS.md entry was written, because workers may not edit that file.

### MC-107

- **Action:** Ran python3 -B scripts/tests/home-actions-test.py, early-branch-test.py, and supervisor-test.py from the repo root.
- **Expected result:** All pass: resume with worktree listing failure shows a refusal without exception, early-branch skip contexts create no ref, and the signing audit reports no unflagged fixture commits.
- **Actual result:** All three suites reported OK: home-actions 39 tests, early-branch 12 tests, supervisor 78 tests. No failures or errors. The exit status was not captured because the PIPESTATUS echo printed empty; the unittest 'OK' summaries are the evidence.
- **Defects:** None

### MC-203

- **Action:** Ran scripts/tests/worktree-run-test.sh and scripts/tests/gates-test.sh with PATH set to a directory of symlinks to every tool in /usr/bin, /bin, /usr/local/bin and /opt/homebrew/bin except git, with UNCLE_TEST_ALLOW_NESTED=1. An earlier run with a minimal PATH (sh, python3, bash, env, dirname only) was discarded because it also hid mktemp and awk.
- **Expected result:** Stderr shows `missing prerequisite: <tool>`, and the exit code is nonzero and not 127. The suite is not reported as passed or skipped.
- **Actual result:** Inconclusive. Both suites exited 1 (nonzero, not 127), but neither printed `missing prerequisite: git` in the captured output (grep for missing/prereq/skip found nothing relevant). The output was dominated by `No space left on device` (cp ENOSPC in the worktree-run fixtures) and cascading fixture failures such as 'canonical artifact missing'. The disk-full condition confounds the result, so it can't be attributed to the hidden tool. Without UNCLE_TEST_ALLOW_NESTED, worktree-run-test.sh exited 77 (skipped, because a build is driving the checkout). Suites that previously exited 127 were not separately enumerated.
- **Defects:** None. Free disk space on the host's tmp volume, then rerun with only git removed from PATH. A possible defect, still unconfirmed, is that no code emits `missing prerequisite: <tool>`.

### MC-205

- **Action:** Same procedure as MC-105 (same action, same run).
- **Expected result:** Both runs pass; .gitignore hash identical after restoration.
- **Actual result:** Same as MC-105: runs failed under a full disk (ENOSPC), so they are inconclusive. Hash restored identically to the original.
- **Defects:** None. Action: free disk space, then rerun.

### MC-300

- **Action:** Copied project to a temp dir (git init, README.md modified for dirty tree) and ran scripts/stagegate.sh and scripts/change-workflow.sh with --version and --help, capturing exit codes, stdout and stderr.
- **Expected result:** Each exits 0; --version prints 0.1.0; --help documents --unattended; no run-policy refusal.
- **Actual result:** All four exited 0. Both --version printed 0.1.0. stagegate --help usage line includes [--unattended] (1 match for --unattended); change-workflow --help includes it (2 matches). stderr was empty for all four; no refusal.
- **Defects:** None

### MC-305

- **Action:** Hashed host .gitignore (sha256 prefix fb94ad9fa6cae8a1; it already had a bare `.uncle` line at line 36). Ran `python3 -B scripts/tests/attestation-statement-test.py` with the `.uncle` line present, then with all bare `.uncle` lines removed, then restored from a backup and re-hashed.
- **Expected result:** Both runs pass; the restored .gitignore hash equals the original hash.
- **Actual result:** Run with `.uncle` line: 13 tests, FAILED (failures=1, errors=1), 37s. Run clean: 13 tests, FAILED (errors=13), 0.7s. Restored hash fb94ad9fa6cae8a1 equals the original. The restore `cp` also reported 'No space left on device' (xattr copy), and a shell cwd write to /tmp failed with the same error, so the host disk was full during the runs. I could not read the failure detail or tell whether the failures are caused by the disk or by the code. The all-errors clean run points to an environment fault.
- **Defects:** None; free disk space on the host (/tmp or the volume), then rerun MC-305.

### MC-306

- **Action:** Ran `python3 -B scripts/tests/home-actions-test.py` and `scripts/tests/early-branch-test.py`. Then, in an empty non-repo temp dir, called the TUI's `_find_run_worktree(root, '#5', '/resume')` (the resume target resolver) directly on an instance created with __new__. I did not drive the interactive TUI screen.
- **Expected result:** Both suites pass; the TUI shows a refusal message when worktree listing fails, without a traceback and without changing state.
- **Actual result:** Both suites passed (home-actions: 39 tests OK; early-branch: 12 tests OK). The resolver raised ValueError "Cannot list this project's worktrees: fatal: not a git repository ...", which is the refusal text, and the temp dir was left empty (no state change). I did not observe the rendered TUI screen, so I could not confirm that the TUI displays this ValueError without a traceback. No existing test covers the 'Cannot list' message.
- **Defects:** None

### MC-401

- **Action:** In the dirty working tree, ran scripts/stagegate.sh --version, scripts/change-workflow.sh --version, and --help on both; captured stdout and exit codes.
- **Expected result:** Version prints 0.1.0 with exit 0; help prints usage including --unattended with exit 0; no run-policy refusal appears.
- **Actual result:** stagegate.sh --version: '0.1.0', exit 0. change-workflow.sh --version: '0.1.0', exit 0. stagegate.sh --help: exit 0, 'Usage: stagegate.sh [-h|--help] [--version] [--attended] [--unattended]' (1 match for --unattended). change-workflow.sh --help: exit 0, usage line includes --unattended (2 matches). No run-policy refusal text observed.
- **Defects:** None

### MC-404

- **Action:** Same procedure as MC-105 (same action, same run).
- **Expected result:** Both runs pass; .gitignore hash after restoration equals the original.
- **Actual result:** Same as MC-105: runs failed under a full disk (ENOSPC), so they are inconclusive. Hash restored identically to the original.
- **Defects:** None. Action: free disk space, then rerun.

### MC-405

- **Action:** Ran `python3 -B scripts/tests/home-actions-test.py`. Then, in a temp non-git directory, called worktree_runs.runs() and the TUI's resume lookup (uncle_tui _find_run_worktree(root, '#5', 'resume')) directly, without driving the full interactive TUI.
- **Expected result:** The suite passes; the resume path shows a refusal message without a traceback or WorktreeListError escaping, and no state is changed.
- **Actual result:** The suite ran 39 tests and reported OK. In the non-repo directory worktree_runs.runs() raised WorktreeListError (fatal: not a git repository). _find_run_worktree converted it into a ValueError refusal: "Cannot list this project's worktrees: fatal: not a git repository (or any of the parent directories): .git". No WorktreeListError or traceback escaped. The lookup only reads, and I observed no state change.
- **Defects:** None

### MC-407

- **Action:** Ran scripts/tests/worktree-run-test.sh under /bin/bash with UNCLE_UNATTENDED and UNCLE_STATUS_STAGE unset. Two attempts: (1) a minimal PATH of symlinks lacking chmod, cp and git; (2) a PATH of symlinks to every tool in /bin, /usr/bin and /opt/homebrew/bin except git. Also grepped scripts/ and uncle_tui.py for the string 'missing prerequisite'.
- **Expected result:** Stderr shows `missing prerequisite: <tool>` and the exit code is nonzero and not 127; the result is not a pass or skip.
- **Actual result:** The suite never printed `missing prerequisite: <tool>`. Attempt 1 exited 1 with 'chmod: command not found' and 'cp: command not found' on stderr, and fixtures reported 'expected exit 0, got 127' (the 127 came from fixtures, not the suite's own exit). Attempt 2 (git removed) exited 1 with FAIL lines such as 'Not a git repository' and the stub git wrapper's 'exec: : not found'; REAL_GIT resolved to empty and the suite carried on. The only occurrence of 'missing prerequisite' in scripts/ or uncle_tui.py is a prose sentence at scripts/lib/gates.sh:406. The suite has no up-front tool check. The exit was nonzero and not 127, but the required stderr message is absent.
- **Defects:** New: worktree-run-test.sh does not detect a missing required tool or emit `missing prerequisite: <tool>`. It fails late with unrelated errors.

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | YES | PASS | Shell loop output: stagegate --version exit=0; stagegate --help exit=0 unattended_lines=1; stagegate -h exit=0 unattended_lines=1; change-workflow --version exit=0; change-workflow --help exit=0 unattended_lines=2; change-workflow -h exit=0 unattended_lines=2. git status showed uncommitted modifications. |
| MC-105 | YES | BLOCKED-SETUP | Terminal output; df -h shows /System/Volumes/Data 100% used; 'no space left on device' errors from zsh and cp. |
| MC-106 | YES | FAIL | exit=77 with empty stderr; exit=1 with stderr 'mktemp: command not found / mktemp -d failed'. grep -rIn 'missing prerequisite' in scripts/ returned nothing. |
| MC-107 | YES | PASS | home-actions: 'Ran 39 tests in 4.283s OK'; early-branch: 'Ran 12 tests in 10.548s OK'; supervisor: 'Ran 78 tests in 3.674s OK'. I did not inspect which individual tests cover the worktree-listing refusal, the no-ref skip contexts, or the signing audit. |
| MC-203 | YES | BLOCKED-SETUP | worktree-run-test.sh: exit 1 with cp 'No space left on device' on the tmp fixture. gates-test.sh: exit 1 with 'canonical artifact missing: ...ADVERSARIAL_REVIEW.json' and FAIL [sg-missing-driver-results-block], and rm 'No such file or directory'. The only 'missing prerequisite' string in the repo is a prompt sentence in scripts/lib/gates.sh:406, not a runtime message about a missing tool. |
| MC-205 | YES | BLOCKED-SETUP | Same output as MC-105; disk 100% full. |
| MC-300 | YES | PASS | Terminal transcript: 'stagegate --version exit 0 0.1.0', 'stagegate --help exit 0 Usage: stagegate.sh [-h/--help] [--version] [--attended] [--unattended]', 'change-workflow --version exit 0 0.1.0', 'change-workflow --help exit 0 Usage: change-workflow.sh ... [--unattended]'; stderr empty each. |
| MC-305 | YES | BLOCKED-SETUP | H0=fb94ad9fa6cae8a1, H1=fb94ad9fa6cae8a1. Test tail output: 'FAILED (failures=1, errors=1)' and 'FAILED (errors=13)'. Error: 'cp: /tmp/gi.bak: could not copy extended attributes to .gitignore: No space left on device'. |
| MC-306 | YES | BLOCKED-HUMAN | Test output ended 'Ran 39 tests ... OK' and 'Ran 12 tests ... OK'. Direct call printed: ValueError Cannot list this project's worktrees: fatal: not a git repository (or any of the parent directories): .git. Temp dir had 0 entries afterwards. Source: uncle_tui.py:5874-5882. |
| MC-401 | YES | PASS | Terminal output of the four commands in the dirty working tree (git status shows many modified files); exit=0 for each. An initial combined run had its output truncated by head, so --version and --unattended counts were re-run separately and confirmed. |
| MC-404 | YES | BLOCKED-SETUP | Same output as MC-105; disk 100% full. |
| MC-405 | YES | PASS | home-actions-test.py output: 'Ran 39 tests in 1.366s / OK'. Refusal text as quoted above. Code at uncle_tui.py:5880-5882. Limitation: the TUI was not driven interactively, so the user-visible rendering of the refusal was not observed. |
| MC-407 | YES | FAIL | Attempt 2 (git removed) exit=1; stderr contained 'bin/git: line 3: exec: : not found'. Attempt 1 stderr: 'chmod: command not found', 'cp: command not found'. grep for 'missing prerequisite' found only scripts/lib/gates.sh:406 (prose). worktree-run-test.sh lines 1-90 read: no `command -v` prerequisite guard other than REAL_GIT="$(command -v git)" at line 84, which is unchecked. |
