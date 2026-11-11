# Verification report

## Findings

### MC-901

- **Action:** Extracted the real finalize_no_pr_worktree from scripts/from-issue.sh and ran it in two disposable roots (/tmp/mc901/root-ok, root-fail) with a mocked git (mocked commit logs root and marker existence) and stubbed worktree helpers. Did not execute the scripts/lib/change-pr.sh publish branch (embedded Python handoff needing a real remote/push, intended_head and attestation state) or the scripts/stagegate.sh completion-merge branch (deep inside the driver) live; only read their diffs.
- **Expected result:** Successful publish freezes the intended root after push success; failed push creates no marker; finalize and merge freeze the intended root before their mocked commit; no real signer invoked.
- **Actual result:** from-issue finalize: marker already existed at the mocked commit, in the intended root, for both outcomes (freeze precedes commit). On commit success the marker stayed. On commit failure the marker, which this attempt had created, was removed. The mocked git never invoked a signer. Not executed: the change-pr post-push freeze and the stagegate merge-time freeze. From the diffs, the change-pr freeze sits after the push and the 'Published SHA mismatch' check, so a failed push raises before it. The stagegate freeze runs before worktree_merge_finish_all. These are code reading only, not execution evidence.
- **Defects:** None. Setup needed: a mocked-remote harness for change-pr.sh handoff (success and failed push) and a harness for the stagegate.sh completion-merge branch, so those two call sites can be traced live.

### MC-902

- **Action:** Built four disposable git fixtures in temp dirs (finalize and merge call sites, each with an absent and a pre-existing .uncle/workflow/gitignore-frozen marker) holding a legacy .gitignore. I ran the real freeze and cleanup lines extracted by sed from scripts/from-issue.sh (lines 399-408) and scripts/stagegate.sh (lines 7157-7160 and 7165), with git commit and worktree_merge_finish_all mocked to fail. The fixtures had commit.gpgsign=false and UNCLE_GITIGNORE_FROZEN was unset. After each failure I ran uncle_gitignore.ensure() in a fresh python process with the guard variable unset and compared .gitignore with a pre-attempt byte snapshot.
- **Expected result:** A marker created by the failed attempt is removed and retry normalization works. A pre-existing marker is preserved and .gitignore stays byte-identical. No real commit or signer is invoked.
- **Actual result:** Finalize/absent: marker no -> no after the mocked commit failure; .gitignore byte-identical; ensure() returned True and normalized the file. Merge/absent: marker no -> no; byte-identical; ensure() returned True and normalized the file. Finalize/present: marker yes -> yes; byte-identical; ensure() returned False and the file stayed identical. Merge/present: marker yes -> yes; byte-identical; ensure() returned False and the file stayed identical. The guard stayed unset in all four cases (freeze succeeded). Only mocked commit and merge ran, so no real commit or signer was invoked. An earlier merge run used the wrong cleanup line numbers and was discarded; I corrected the harness and re-ran it.
- **Defects:** None

### MC-903

- **Action:** Ran temp probe /tmp/mc903/probe.sh in disposable roots (legacy .gitignore with managed entries; absent .gitignore; both with .git dir). A sitecustomize patch made os.open raise PermissionError(13) for the gitignore-frozen marker. Per root: freeze() then ensure() in-process; the stagegate/from-issue shell call-site line (python3 -c freeze || warn + export UNCLE_GITIGNORE_FROZEN=1), reproduced verbatim as a pasted line, not executed from those scripts; the change-pr.sh publish-site try/except block, reproduced verbatim and run in the root; CLI child process (scripts/lib/uncle_gitignore.py) and an sh -c resumed step inheriting the env. Snapshotted sha/absence before and compared after.
- **Expected result:** freeze() returns false without raising; each call site warns visibly; in-process, child and resumed normalization leave bytes unchanged and absent files absent via the in-process record or the inherited guard.
- **Actual result:** Both cases: freeze returned False with no exception; ensure returned False; no marker created. Shell site printed 'Warning: could not record the .gitignore freeze marker...' and exported UNCLE_GITIGNORE_FROZEN=1. The change-pr block printed its stderr warning, set the guard and ensure returned False. The CLI child exited 0, and the resumed sh step saw UNCLE_GITIGNORE_FROZEN=1. Legacy .gitignore sha was identical before and after (UNCHANGED); the absent .gitignore stayed ABSENT. Caveat: call-site code was replicated by copy, not run from the actual script files.
- **Defects:** None

### MC-904

- **Action:** In a mktemp git fixture with a legacy .gitignore (node_modules, *.log, .uncle/*) and an old .uncle/workflow/state, ran uncle_gitignore.freeze() with UNCLE_GITIGNORE_FROZEN unset and recorded the marker and .gitignore bytes. Then ran the stagegate fresh-run branch (stagegate.sh line 5697: state file absent, so finished_extras reset and plan-check-repair file removal, then a new state file written) in the same root. Then ran scripts/lib/uncle_gitignore.py <root> with UNCLE_GITIGNORE_FROZEN unset (env -u) and compared bytes with cmp.
- **Expected result:** Fresh run state preserves .uncle/workflow/gitignore-frozen, and .gitignore stays byte-identical to the original snapshot.
- **Actual result:** The marker existed before and after the fresh-run state creation. The CLI run exited without changing .gitignore, and cmp reported it identical to the snapshot.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-901 | YES | BLOCKED-SETUP | Trace: 'mocked-commit root=/tmp/mc901/root-ok marker_exists=yes outcome=ok'; 'mocked-commit root=/tmp/mc901/root-fail marker_exists=yes outcome=fail'. After the runs: root-ok marker=yes, root-fail marker=no. Existing scripts/tests/gitignore-post-push-test.py only does source-text assertions for the other two sites. |
| MC-902 | YES | PASS | Harness output: 'MOCK commit fail' and 'MOCK merge fail' traces; 'after marker: no; guard=unset' plus 'ensure changed: True' for both absent cases; 'after marker: yes; guard=unset' plus 'ensure changed: False' for both present cases; 'gitignore byte-identical' (cmp against the pre-attempt snapshot) in all four. |
| MC-903 | YES | PASS | Probe output: 'freeze returned False', 'ensure returned False', 'env guard: 1', 'resumed-env=1', 'UNCHANGED' (legacy sha d6a5b8cc... both times), 'after: ABSENT' for the absent case. Injected error: PermissionError(13,'injected EACCES'). |
| MC-904 | YES | PASS | Output: freeze True; before=exists; .uncle/workflow listed gitignore-frozen and state after the restart; after=exists; IDENTICAL; env=unset. Limits: the restart path was reproduced by running the real fresh-run commands of stagegate.sh line 5697 against the fixture state dir, not by launching the full stagegate. The fixture did not show that an unfrozen ensure() would have changed this .gitignore, so byte-identity here rests on the marker alone. |
