# Defects

## None. Action: free disk space on the host volume, then rerun.

- **Status:** BLOCKED-SETUP
- **Evidence:** Terminal output; df -h shows /System/Volumes/Data 100% used; 'no space left on device' errors from zsh and cp.
- **Expected result:** Both runs pass; .gitignore hash identical after restoration.
- **Actual result:** Run 1 (.uncle present): 13 tests, FAILED (failures=1, errors=2). Run 2 (clean): FAILED (errors=13). Shell reported 'no space left on device' (ENOSPC) during writes; volume at 100% (249Mi free). Failures are not attributable to the application. Restored .gitignore hash equals original (f65fdeed...), cmp byte-identical.

## Missing-tool handling in worktree-run-test.sh does not emit 'missing prerequisite: <tool>'. Without the nested override the suite exits 77 (skip). No DEFECTS.md entry was written, because workers may not edit that file.

- **Status:** FAIL
- **Evidence:** exit=77 with empty stderr; exit=1 with stderr 'mktemp: command not found / mktemp -d failed'. grep -rIn 'missing prerequisite' in scripts/ returned nothing.
- **Expected result:** stderr contains `missing prerequisite: <tool>`, exit is nonzero and not 127, and it is reported as FAILED, never passed or skipped.
- **Actual result:** Plain run: stdout said 'skipped, an uncle build is driving this checkout', exit 77, stderr empty. That is a skip, not a failure. With UNCLE_TEST_ALLOW_NESTED=1: exit 1, stderr was 'line 59: mktemp: command not found' and 'worktree-run-test.sh: mktemp -d failed'. No 'missing prerequisite: <tool>' text appeared. The grep found no emitter of that string in scripts/; the only hits were in docs and prompts.

## None. Free disk space on the host's tmp volume, then rerun with only git removed from PATH. A possible defect, still unconfirmed, is that no code emits `missing prerequisite: <tool>`.

- **Status:** BLOCKED-SETUP
- **Evidence:** worktree-run-test.sh: exit 1 with cp 'No space left on device' on the tmp fixture. gates-test.sh: exit 1 with 'canonical artifact missing: ...ADVERSARIAL_REVIEW.json' and FAIL [sg-missing-driver-results-block], and rm 'No such file or directory'. The only 'missing prerequisite' string in the repo is a prompt sentence in scripts/lib/gates.sh:406, not a runtime message about a missing tool.
- **Expected result:** Stderr shows `missing prerequisite: <tool>`, and the exit code is nonzero and not 127. The suite is not reported as passed or skipped.
- **Actual result:** Inconclusive. Both suites exited 1 (nonzero, not 127), but neither printed `missing prerequisite: git` in the captured output (grep for missing/prereq/skip found nothing relevant). The output was dominated by `No space left on device` (cp ENOSPC in the worktree-run fixtures) and cascading fixture failures such as 'canonical artifact missing'. The disk-full condition confounds the result, so it can't be attributed to the hidden tool. Without UNCLE_TEST_ALLOW_NESTED, worktree-run-test.sh exited 77 (skipped, because a build is driving the checkout). Suites that previously exited 127 were not separately enumerated.

## None. Action: free disk space, then rerun.

- **Status:** BLOCKED-SETUP
- **Evidence:** Same output as MC-105; disk 100% full.
- **Expected result:** Both runs pass; .gitignore hash identical after restoration.
- **Actual result:** Same as MC-105: runs failed under a full disk (ENOSPC), so they are inconclusive. Hash restored identically to the original.

## None; free disk space on the host (/tmp or the volume), then rerun MC-305.

- **Status:** BLOCKED-SETUP
- **Evidence:** H0=fb94ad9fa6cae8a1, H1=fb94ad9fa6cae8a1. Test tail output: 'FAILED (failures=1, errors=1)' and 'FAILED (errors=13)'. Error: 'cp: /tmp/gi.bak: could not copy extended attributes to .gitignore: No space left on device'.
- **Expected result:** Both runs pass; the restored .gitignore hash equals the original hash.
- **Actual result:** Run with `.uncle` line: 13 tests, FAILED (failures=1, errors=1), 37s. Run clean: 13 tests, FAILED (errors=13), 0.7s. Restored hash fb94ad9fa6cae8a1 equals the original. The restore `cp` also reported 'No space left on device' (xattr copy), and a shell cwd write to /tmp failed with the same error, so the host disk was full during the runs. I could not read the failure detail or tell whether the failures are caused by the disk or by the code. The all-errors clean run points to an environment fault.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** Test output ended 'Ran 39 tests ... OK' and 'Ran 12 tests ... OK'. Direct call printed: ValueError Cannot list this project's worktrees: fatal: not a git repository (or any of the parent directories): .git. Temp dir had 0 entries afterwards. Source: uncle_tui.py:5874-5882.
- **Expected result:** Both suites pass; the TUI shows a refusal message when worktree listing fails, without a traceback and without changing state.
- **Actual result:** Both suites passed (home-actions: 39 tests OK; early-branch: 12 tests OK). The resolver raised ValueError "Cannot list this project's worktrees: fatal: not a git repository ...", which is the refusal text, and the temp dir was left empty (no state change). I did not observe the rendered TUI screen, so I could not confirm that the TUI displays this ValueError without a traceback. No existing test covers the 'Cannot list' message.

## None. Action: free disk space, then rerun.

- **Status:** BLOCKED-SETUP
- **Evidence:** Same output as MC-105; disk 100% full.
- **Expected result:** Both runs pass; .gitignore hash after restoration equals the original.
- **Actual result:** Same as MC-105: runs failed under a full disk (ENOSPC), so they are inconclusive. Hash restored identically to the original.

## New: worktree-run-test.sh does not detect a missing required tool or emit `missing prerequisite: <tool>`. It fails late with unrelated errors.

- **Status:** FAIL
- **Evidence:** Attempt 2 (git removed) exit=1; stderr contained 'bin/git: line 3: exec: : not found'. Attempt 1 stderr: 'chmod: command not found', 'cp: command not found'. grep for 'missing prerequisite' found only scripts/lib/gates.sh:406 (prose). worktree-run-test.sh lines 1-90 read: no `command -v` prerequisite guard other than REAL_GIT="$(command -v git)" at line 84, which is unchecked.
- **Expected result:** Stderr shows `missing prerequisite: <tool>` and the exit code is nonzero and not 127; the result is not a pass or skip.
- **Actual result:** The suite never printed `missing prerequisite: <tool>`. Attempt 1 exited 1 with 'chmod: command not found' and 'cp: command not found' on stderr, and fixtures reported 'expected exit 0, got 127' (the 127 came from fixtures, not the suite's own exit). Attempt 2 (git removed) exited 1 with FAIL lines such as 'Not a git repository' and the stub git wrapper's 'exec: : not found'; REAL_GIT resolved to empty and the suite carried on. The only occurrence of 'missing prerequisite' in scripts/ or uncle_tui.py is a prose sentence at scripts/lib/gates.sh:406. The suite has no up-front tool check. The exit was nonzero and not 127, but the required stderr message is absent.
