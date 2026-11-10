# Change Request

Issue 233

Seeded from [unclehq/uncle#233](https://github.com/unclehq/uncle/issues/233).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Hand-off mode leaves .uncle/attestation.json and .sig out of handoff.json, so a host-published PR has no attestation and `uncle verify <pr>` cannot check it

## Motivation

## Summary

In hand-off mode (`UNCLE_PUBLISH_MODE=handoff`), `.uncle/handoff/handoff.json` never lists `.uncle/attestation.json` or `.uncle/attestation.sig`. A host that publishes the hand-off exactly as written opens a PR that has no attestation file. The attestation appears only as the summary block in the PR body. `uncle verify <pr>` reads `.uncle/attestation.json` from the PR head, so it has nothing to verify.

`.gitignore` is not the cause. The `!.uncle/attestation.json`, `!.uncle/attestation.sig` and `!.uncle/allowed_signers` lines work, and PRs from Uncle's normal publish commit `.uncle/attestation.json` and `.uncle/docs/` (for example #224, #227 and #229). In hand-off mode, the step that writes the attestation never runs.

## How it happens

1. **At bind, after the final audit,** `commit_tree` is the snapshot of the audited tree, and `attestation` is the sealed summary for the PR body (`scripts/lib/change-pr.sh:1939-1942`, `scripts/lib/attestation.py:259-278`). On purpose, the snapshot leaves out `.uncle/attestation.json` and `.sig`. "The attestation names the tree it is committed into", so those files are added only when `snapshot(..., attestation=True)` is called (`change-pr.sh:827-832`, `:884-890`).
2. **Normal publish** calls `attest(j)` after consent (`change-pr.sh:1753-1757`). That builds the release Statement, signs it when a signer exists, writes `.uncle/attestation.json` and `.sig`, and moves `commit_tree` to `snapshot(True, attestation=True)` (`:615-682`, files written at `:685-697`, tree moved at `:680-681`).
3. **Hand-off mode** returns before step 2 (`change-pr.sh:205-213`). `handoff_export.py` then:
   - takes `tree` from the bound `commit_tree` (`:89`), which is the tree without the attestation files;
   - lists `changes` as the diff from the base commit to that tree (`:60-80`, `:112`);
   - uses the bind-time summary, or seals one (`:93-97`), and puts it only in `pr_body` and the `attestation` field (`:106`, `:113-116`).
4. **`uncle verify <pr-url|pr-number>`** reads `.uncle/attestation.json` (and `.sig` when present) from the PR head commit (`scripts/uncle-verify.py:424-426`). A host-published hand-off PR has neither.

`GITHUB_INTEGRATION.md:81-83` already describes this: "Applying those changes to the base commit gives exactly the audited tree", and "Not yet covered: … `uncle verify` against the host-opened PR."

`.uncle/allowed_signers` behaves differently. It is walked like any other file that isn't ignored. When the project has one, it is already in the bound tree and appears in `changes` as usual, so it only needs test coverage. The trust-root rule at `change-pr.sh:780-782` keeps a tracked copy from being deleted.

## Code paths (main `5a5cd30`)

Blame is `git blame -w`.

| Where | What it does | Last changed in |
|---|---|---|
| `scripts/lib/change-pr.sh:205-214` | Hand-off branch: runs `handoff_export.py` and returns, so `change_pr_publish` and `attest(j)` never run. | `23b2da49` 2026-11-09 (#205, PR #219) |
| `scripts/lib/handoff_export.py:60-80` | `changes(base, tree)`: every path that differs between base and `tree`, with full content. | `23b2da49` 2026-11-09 (#205, PR #219) |
| `scripts/lib/handoff_export.py:89-97` | Takes `tree` from the bound `commit_tree`. Uses the bind-time sealed summary, or seals one, and sets `gate_publication` to `HANDOFF`. Writes no file. | `23b2da49` 2026-11-09 (#205, PR #219) |
| `scripts/lib/handoff_export.py:106-116` | Attaches the summary to the PR body and writes `handoff.json` with `tree`, `attestation` and `changes`. | `23b2da49` 2026-11-09 (#205, PR #219) |
| `scripts/lib/change-pr.sh:1939-1942` | Bind: `commit_tree=snapshot(True)` (no attestation files) and `attestation=seal_attestation(j)`. | `57312a8a` 2026-09-10, `63b65476` 2026-09-13 |
| `scripts/lib/attestation.py:259-278` | `seal()`: the PR-body summary (issue, specification, agents, review, verification, tree). This is not the signed Statement. | `63b65476` 2026-09-13 |
| `scripts/lib/change-pr.sh:827-832` | The snapshot walk skips `ATTESTATION_FILES`. | `f365a77c` 2026-09-16 (#59), `d9fd1a72` 2026-09-21 |
| `scripts/lib/change-pr.sh:884-890` | With `attestation=True`, appends `.uncle/attestation.json` and `.sig` to the tree. | `f365a77c` 2026-09-16 (#59), `57312a8a`, `d9fd1a72` |
| `scripts/lib/change-pr.sh:615-623`, `:677-697` | `attest(j)`: Statement, signature, `write_attestation_files`, then `commit_tree = snapshot(True, attestation=True)`. | `f365a77c` 2026-09-16 (#59) |
| `scripts/lib/change-pr.sh:1753-1765` | Normal publish: `attest(j)` when envelopes exist; otherwise only the summary. | `f365a77c` 2026-09-16 (#59), `63b65476`, `efa8cb59` 2026-10-25 |
| `scripts/lib/change-pr.sh:780-782` | Trust root: keeps a tracked `.uncle/allowed_signers` in the tree. | `5d87d59f` 2026-10-31 |
| `scripts/uncle-verify.py:424-426` | `uncle verify <pr>` reads `.uncle/attestation.json` and `.sig` from the PR head. | `f365a77c` 2026-09-16 (#59) |
| `GITHUB_INTEGRATION.md:75-83` | Hand-off docs, including "not yet covered: `uncle verify` against the host-opened PR". | `23b2da49` 2026-11-09 (#205, PR #219) |

## Fix

1. **Attest before exporting.** On the hand-off branch (`change-pr.sh:207`), run the same attestation step the normal publish runs (`change-pr.sh:1753-1765`) before `handoff_export.py`. When envelopes exist, call `attest(j)` with the publication gate recorded as the host hand-off. Otherwise, fall back to the summary as today. Then save the journal. Afterwards `commit_tree` is the attested tree, and `audited_tree` keeps the audited one, as on the normal path (`:680-681`).
2. **Export the attested tree.** `handoff_export.py` then takes `tree` from the updated `commit_tree`. `changes(base, tree)` picks up `.uncle/attestation.json`, and `.sig` when a signer exists, with no special case. "Applying those changes to the base commit gives exactly `tree`" still holds. Add `audited_tree` to `handoff.json` so a host can show both.
3. **Keep the PR-body summary**, taken from the same sealed state, so the body and the committed Statement can't disagree.
4. **Refuse the same way the normal path does.** If `attest(j)` refuses under the blocking policy (an overridden `NOT READY` with envelopes), the hand-off fails with that message (`handoff-failed`) instead of writing a hand-off without an attestation.
5. **Update `GITHUB_INTEGRATION.md:79-83`.** Say the hand-off includes the attestation files, and remove "`uncle verify` against the host-opened PR" from "not yet covered".

## Tests

- A hand-off from a run with envelopes lists `.uncle/attestation.json` as `add`, and its content is byte-for-byte the Statement that `attest(j)` wrote. Applying `changes` to `base_commit` gives `tree`, and `tree` equals the journal's attested `commit_tree`.
- With a signer configured, `.uncle/attestation.sig` is listed too. Without one, it isn't, and no stale `.sig` is listed.
- With `.uncle/allowed_signers` tracked in the base, the hand-off doesn't delete it. With a new one in the working tree (not ignored, thanks to `!.uncle/allowed_signers`), it is listed as `add`.
- End to end: apply the hand-off to a copy of the base in a scratch repository, commit it, and run `uncle verify --tree <commit>` (or `uncle verify` at that `HEAD`). It reaches the integrity checks instead of failing with "no attestation".
- An overridden `NOT READY` run with envelopes refuses the hand-off with the attestation-blocked message, and no `handoff.json` is written.
- A run that predates envelopes still writes a hand-off with the summary only, as today.

## Checks after the fix

- A hosted hand-off on a repository whose `.gitignore` has Uncle's block: the host-opened PR contains `.uncle/attestation.json` (and `.sig` when signed), and `uncle verify <pr>` runs its checks against it.

## Related

- #205 and PR #219 (hand-off mode), #59 (attestations).
- A new-project build has no hand-off path. It attests and then commits locally (`scripts/stagegate.sh:472-484`, `:6892-6911`), so a host publishing one has to collect the files itself. That is out of scope here, but worth noting for hosted runs.

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
