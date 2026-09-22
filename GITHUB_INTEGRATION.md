# GitHub integration

Uncle imports GitHub issues and can publish audited changes as pull requests.

## Setup

Install Git and the GitHub CLI, then run `gh auth login`. Launch `uncle` in your project checkout. PRs require a supported GitHub remote and permission to push and create PRs.

See [Prerequisites](PREREQUISITES.md) for other requirements.

## Import an issue

Choose **From GitHub issue**, enter its URL or number, and select **change request** or **new application**. Uncle creates `CHANGE_REQUEST.md` or `REQUIREMENTS.md` from the issue title and body.

Import uses your current project; it does not clone a repository. Public issues can use a read-only `curl` fallback.

## Create a PR

The change workflow offers PR publication after a READY audit. This also works with a local `CHANGE_REQUEST.md`.

When the verdict is not READY, publication first asks whether to create the PR anyway, showing the recorded verdict. Approving records the override in `.uncle/workflow/pr/verdict-override` and notes it at the top of the PR body; the linked issue stays open. Unattended runs are never asked.

1. Review the audited diff and target.
2. Enter a title, summary, and manual verification steps.
3. Approve the commit, push, and PR creation.

Uncle creates a feature branch when needed and pushes without force. Eligible imported issues are linked with `Closes owner/repo#number`; GitHub closes them on merge into the default branch. Uncle does not merge PRs.

Auto/unattended mode and `WORKFLOW_CLOSE_ISSUE=0` disable a new handoff. A previously approved signing handoff can resume despite these settings after validation. New-application workflows do not use it.

## Signing and recovery

When Git commit signing is enabled, Uncle shows one command block that stages all changes, removes `.uncle/workflow` from the index, includes `.uncle/docs/FINAL_AUDIT.md` even when ignored, and runs `git commit -S` with the approved title. Review the changes, press **c — Copy command**, and run the block in another terminal in the same project. Copying does not execute it. Return and press **Enter** to validate and resume, or **Esc** to cancel and leave the handoff pending. Uncle verifies the signature, audited tree, and sole parent before publication.

Copy requires `pbcopy` on macOS, `wl-copy` on Wayland, or `xclip` (preferred) / `xsel` on X11. A missing or failing helper leaves the dialog open with an error; terminal selection remains available. The CLI prints the same shell-ready block. Arrow keys scroll long signing instructions in the TUI.

Restart Uncle in the same project to resume a pending handoff. Keep `.uncle/workflow/pr/journal.json`; it records progress and helps prevent duplicate PRs. Changes to audited files or repository state may require another audit.

Without Git, Uncle cannot create a PR. The issue remains open; Uncle never closes issues directly.

## Attestation

Every PR the change workflow publishes carries a verifiable record of what was reviewed, verified, and approved, and by whom. Nothing in it is written by a stage model; the driver writes it from validator exit codes, gate records, and its own hashing.

### Envelopes

As each evidence-producing stage finishes, the driver writes `.uncle/workflow/envelopes/<stage>.json` for `requirements`, `review`, `plan`, `implementation`, `verification`, `audit`, and `release`. Each envelope is RFC 8785 canonical JSON with `result` `pass`, `fail`, or `unavailable`, the digests of its evidence documents, and the artifact digest — the Git tree of the working files minus `.uncle/` and the workflow documents. `review.json` and `audit.json` are pre-written as `unavailable` before the reviewer runs, so a reviewer that never returns leaves the reason on record. Re-approving a document, or re-entering implementation or the final audit, deletes every envelope downstream of it. The directory is driver-owned: a write there during the implementation stage is reverted from the pre-stage snapshot, logged in `.uncle/workflow/envelope-tamper.log`, and stops the run.

The release policy is fixed: `review`, `verification`, or `audit` with `fail` or `unavailable` refuses to commit, push, or create the PR. No configuration or environment variable changes it.

### Signing

After you consent to publication, the driver assembles the envelopes into an in-toto Statement (`predicateType: https://uncle.dev/attestation/v1`) whose subject is the artifact tree, writes it to `.uncle/attestation.json`, and adds it to the single PR commit beside the audited files. When `git config gpg.format` is `ssh` and `user.signingkey` names a key file, the Statement is signed with `ssh-keygen -Y sign` into a DSSE envelope at `.uncle/attestation.sig`; when `cosign` is installed and `gpg.x509.program` is `gitsign`, `cosign sign-blob --bundle` is used instead. No new key material is created. Without a signer the attestation is still written with `authentication: none`; a signing failure prints one line and continues the same way.

Approvals record `approved_by` (a person's name) separately from `delegated_by` (`unattended`, `supervisor:explicit:<name>`, `supervisor:standing:<name>`, or `disabled:WORKFLOW_DIFF_GATE=0`). Only a human keystroke satisfies a required gate; the PR block shows delegated gates as delegated.

### Trust root

`uncle verify` trusts SSH signatures listed in an `allowed_signers` file, by default `.uncle/allowed_signers` committed in the repository (un-ignored by `.gitignore` beside `.uncle/attestation.json` and `.uncle/attestation.sig`), or the file named with `--allowed-signers PATH`. Sigstore bundles are checked with `cosign verify-blob` against `--certificate-identity` and `--certificate-oidc-issuer`. A signature without a trust root is reported as `INTEGRITY ONLY — SIGNATURE PRESENT BUT UNTRUSTED`, never `VERIFIED`. A repository that keeps `.uncle/*` ignored without the negation does not commit `allowed_signers`; pass `--allowed-signers` then.

### Verification

```
uncle verify                                  # this checkout, .uncle/attestation.json, HEAD
uncle verify --attestation PATH [--tree SHA]  # explicit inputs
uncle verify <pr-url|pr-number>               # needs gh; verifies the PR head's tree
```

`scripts/uncle-verify.py` is one stdlib-only Python file plus `git`; `ssh-keygen`, `cosign`, and `gh` are optional and their absence is a one-line message. It runs the eight checks in order — canonical bytes and schema, signature, approved document digests, artifact identity across stages, stage results, dispositions for every blocking finding, human approval of every required gate, and the head tree against the release artifact — stops at the first failure, prints both values on a mismatch, and ends with `VERIFIED` (exit 0), `INTEGRITY ONLY — NOT AUTHENTICATED` or `INTEGRITY ONLY — SIGNATURE PRESENT BUT UNTRUSTED` (exit 3), or `NOT VERIFIED` (exit 1). An unsupported `schema_version` or `predicateType` is refused before any check runs.

### Audit override (no release)

A `NOT READY` audit can still be overridden at the audit gate, in the findings dialog, or at publication, and the decision is recorded (`.uncle/workflow/audit-override`, `pr/verdict-override`, or the findings decisions) and reported at completion. With envelopes present that override no longer publishes: `audit.json` keeps `result: fail`, the handoff writes `release.json` with the blocking reason and the recorded override, and refuses with `PR pending: Attestation blocked` before any commit. The route to a PR after `NOT READY` is to fix the findings and re-run from `IMPLEMENT`. Journals from runs that predate envelopes (no `.uncle/workflow/envelopes/` directory) keep the previous behavior, and `uncle verify` reports them as `NOT VERIFIED` because no attestation exists. Rolling back this feature while a handoff is at `prepared` requires `.uncle/attestation.*` to stay in the working tree or a rerun of `FINAL_AUDIT`.
