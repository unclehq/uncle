# Change Request

Issue 276

Seeded from [unclehq/uncle#276](https://github.com/unclehq/uncle/issues/276).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Hand-off builds with no base commit publish no attestation or audit findings: every hosted PR is a non-draft that says "NOT VERIFIED, do not trust its attestation", even when the audit is NOT_READY

## Motivation

## What happened

This was a hosted, unattended build in hand-off mode (`UNCLE_PUBLISH_MODE=handoff`, `UNCLE_HOSTED=1`). The host's build script set up the sandbox work tree from the target repository's files but not its history. The target repository has a commit on `main`. The sandbox had none:

```
[+00:00:00] Initialized Git repository in /home/daytona/work
Run policy: no git history to branch from; continuing without a run branch.
...
$ git log
fatal: your current branch 'master' does not have any commits yet
```

At the end of the build:

```
[+00:14:00] Final audit is NOT_READY; completing so the PR reviewer can decide (findings are in the PR and attestation).
[+00:14:00] Current state: COMPLETE
[+00:14:00] Unattended: no base commit, so no PR was made.
[+00:14:00] PR: none (no base commit)
```

Neither `.uncle/attestation.json` nor a hand-off record was written. The host then published the pull request itself:

- it was a normal pull request, not a draft, even though the audit was `NOT_READY`
- it contained only the three changed files: no attestation and no audit findings
- its description quoted `uncle verify` run in the sandbox before publishing:
  ```
  nothing to verify: HEAD does not exist (this repository has no commits yet; commit the build, including .uncle/attestation.json, then run uncle verify again)
  NOT VERIFIED
  This change could not be verified. Do not trust its attestation as it stands.
  ```

The previous hand-off pull request from the same host, a different build, has the same `NOT VERIFIED` text. So every pull request this host publishes tells the reviewer not to trust it, and none of them carries the audit's verdict or findings.

## Cause

1. With `UNATTENDED=1` and no `HEAD`, the workflow skips `change_pr_complete` entirely ([`scripts/change-workflow.sh#L5261-L5274`](https://github.com/unclehq/uncle/blob/3cecf2b3e46d59fa00389edd50ccb0fc93b2679a/scripts/change-workflow.sh#L5261-L5274)). That function writes the hand-off record and attestation and makes a `NOT_READY` build a draft (issue 107). Without a base commit, hand-off mode therefore has nothing to hand off.
2. The line printed just before it ("findings are in the PR and attestation") is unconditional, so it is wrong on this path.
3. The host's build script copies the target files into a fresh repository instead of cloning or fetching the base branch, so every hosted build takes this path. That script is outside this repository; this item is for the release owner.

## Requested fix

1. In hand-off mode with no base commit, either commit the starting tree as a base before the build starts, so `HEAD` exists, or still write the hand-off record with the attestation, the audit verdict, its findings and `draft: true` when the audit isn't `READY`.
2. Print "findings are in the PR and attestation" only when they will be.
3. Build script (release owner): clone or fetch the target repository's base branch into the sandbox so the build has a base commit and a run branch. Open `NOT_READY` builds as drafts with the verdict and findings in the description. Don't quote `uncle verify` output from a sandbox with no `HEAD`.
4. Add a test: an unattended hand-off build whose work tree has no commits still produces a hand-off record with the attestation, the verdict and the draft flag.

Related: #233 (hand-off mode left the attestation out of `handoff.json`).

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
