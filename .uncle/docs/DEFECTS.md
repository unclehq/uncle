# Defects

## None. Setup needed: a mocked-remote harness for change-pr.sh handoff (success and failed push) and a harness for the stagegate.sh completion-merge branch, so those two call sites can be traced live.

- **Status:** BLOCKED-SETUP
- **Evidence:** Trace: 'mocked-commit root=/tmp/mc901/root-ok marker_exists=yes outcome=ok'; 'mocked-commit root=/tmp/mc901/root-fail marker_exists=yes outcome=fail'. After the runs: root-ok marker=yes, root-fail marker=no. Existing scripts/tests/gitignore-post-push-test.py only does source-text assertions for the other two sites.
- **Expected result:** Successful publish freezes the intended root after push success; failed push creates no marker; finalize and merge freeze the intended root before their mocked commit; no real signer invoked.
- **Actual result:** from-issue finalize: marker already existed at the mocked commit, in the intended root, for both outcomes (freeze precedes commit). On commit success the marker stayed. On commit failure the marker, which this attempt had created, was removed. The mocked git never invoked a signer. Not executed: the change-pr post-push freeze and the stagegate merge-time freeze. From the diffs, the change-pr freeze sits after the push and the 'Published SHA mismatch' check, so a failed push raises before it. The stagegate freeze runs before worktree_merge_finish_all. These are code reading only, not execution evidence.
