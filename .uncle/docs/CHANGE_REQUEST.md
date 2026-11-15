# Change Request

Issue 280

Seeded from [unclehq/uncle#280](https://github.com/unclehq/uncle/issues/280).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

--no-footprint: produce a PR with no trace of Uncle

## Motivation

## Summary

Add a `--no-footprint` mode in which the pull request Uncle produces looks like an ordinary contribution to the target project. No Uncle-created files appear in the PR, and the PR text reads the way a maintainer would want a PR to read, not like an Uncle audit report. The PR honestly discloses that AI assistance was used.

## Desired behavior

- **No Uncle files in the PR diff.** Nothing under `.uncle/`, no workflow docs (`PROJECT_PLAN.md`, `CHANGE_PLAN.md`, `IMPLEMENTATION_NOTES.md`, verification and audit reports), and no other generated artifact is committed or visible in the PR. Only the intended source changes remain.
- **No attestation.** This mode does not produce, commit or attach an attestation, and the PR does not reference `uncle verify`.
- **Maintainer-style PR text.** The title, description and comments follow what an OSS project expects:
  - what changed and why, linked to the issue it addresses;
  - how it was tested, in terms of the project's own tests and commands;
  - notable trade-offs or follow-ups;
  - no stage logs, gate records, review dispositions, audit tables or Uncle-specific vocabulary.
- **AI-assistance disclosure.** The PR includes a short, standard disclosure that AI tooling assisted, in the form projects increasingly ask for (a line in the description, and a commit trailer where the project's policy calls for one). It does not name Uncle or describe Uncle's internals unless the user opts in. The human submitter remains the accountable author.
- **No Uncle residue in the tree.** Uncle's working state lives outside the branch (untracked or out-of-tree) and is never staged.
- **Normal mode is unchanged.** `--no-footprint` is opt-in and does not alter default behavior.

## Decisions

- **Attestation:** dropped in this mode.
- **Disclosure:** included. The mode reduces Uncle's footprint. It does not conceal that AI assisted.

## Open questions

1. **Footprint boundary.** Define a concrete, testable boundary: files, PR title and body, commit messages and trailers, branch names and labels.
2. **Human gates.** The approval gates and the human merge decision stay exactly as they are. This issue must not weaken them.
3. **Disclosure wording.** Decide the default text and trailer format, and how a project's own contribution policy can override them.
4. **Agent CLI attribution.** Decide how the mode interacts with agent CLIs that add their own attribution lines by default.

## Acceptance criteria

- With `--no-footprint`, the PR diff contains only the intended source changes, with no Uncle-generated files and no attestation.
- The PR description follows a maintainer-style template (what, why, testing, follow-ups) and contains no Uncle stage, gate or audit content.
- The PR contains the AI-assistance disclosure and no reference to Uncle unless the user opts in.
- Without the flag, output is byte-identical to today's.
- Tests cover the mode, including a regression test that fails if a generated artifact is staged or an audit section leaks into the PR text.
- README documents the mode, its limits, and the disclosure behavior.

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
