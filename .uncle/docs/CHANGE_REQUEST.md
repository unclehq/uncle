# Change Request

Issue 283

Seeded from [unclehq/uncle#283](https://github.com/unclehq/uncle/issues/283).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Add --oss: follow the upstream project's submission and testing guidelines

## Motivation

## Summary

Add an `--oss` argument that tells Uncle the GitHub issue comes from an open source project that Uncle's user does not own. In this mode, Uncle must follow the project's own submission and testing guidelines, not Uncle's defaults, and must produce a PR that the project's maintainers would accept.

## Desired behavior

- **Discover the project's rules before planning.** Uncle reads the guidance the project publishes, where present:
  - `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `README`, and `docs/` contributor guides;
  - the PR template and issue templates (`.github/PULL_REQUEST_TEMPLATE*`, `.github/ISSUE_TEMPLATE/`);
  - `CODEOWNERS`, `AGENTS.md` or similar agent instructions, and any AI-assistance or contribution policy;
  - CI configuration (`.github/workflows/`), lint and format config, `Makefile` or task runners, and test configuration.
- **Record what was found.** The guidelines Uncle will follow are written into the plan, with a source for each (file and line). Guidelines it could not find are listed as unknown, not assumed.
- **Submission guidelines are followed.** Examples: branch naming, commit message format (Conventional Commits, DCO sign-off `Signed-off-by`, CLA requirements), PR title and description template, changelog entries, linked-issue syntax, target branch, and whether the project asks for an issue to be claimed before work starts.
- **Testing guidelines are followed.** Uncle uses the project's own test, lint, format and type-check commands, in the versions and environments CI uses, in place of its own verification commands. New or changed behavior gets tests in the project's style and location. Uncle runs the project's full required checks before opening the PR.
- **Minimal, in-style change.** Match the project's code style and conventions. No unrelated cleanup, no reformatting of untouched code, and no new dependencies unless the guidelines and the issue allow them.
- **No Uncle artifacts in the PR.** Uncle's workflow files stay out of the diff. The PR text follows the project's template, not an Uncle audit. The project's AI-assistance policy is followed, including disclosure where required, and the PR is not submitted if the policy prohibits AI-assisted contributions.
- **Conflicts are surfaced.** If the guidelines conflict with each other, with the issue, or with Uncle's rules, Uncle stops at a human gate and asks. It does not choose silently. Uncle's approval gates and the human merge decision are unchanged.

## Failure behavior

- **No contributing guidance found:** Uncle says so, falls back to conventions inferred from recent merged PRs and CI, and marks them as inferred.
- **Project cannot be built or tested locally:** the run reports which required checks could not run. It does not claim they passed.
- **Policy forbids AI-assisted PRs:** Uncle stops before creating a PR and tells the user.
- **Issue is not claimable** (assigned to someone else, labeled as not open for contribution, or the project asks for prior discussion): Uncle warns and waits for a human decision.

## Acceptance criteria

- Run against a fixture repository with a `CONTRIBUTING.md`, a PR template, a DCO requirement and a non-default test command, the resulting commits, PR text and verification commands all match them.
- The plan lists each guideline with its source, and lists missing guidance as unknown.
- With no guidance present, Uncle falls back to inferred conventions and labels them as inferred.
- A fixture whose policy prohibits AI contributions stops before PR creation.
- Required project checks that cannot run are reported as not run, never as passed.
- The PR diff contains no Uncle-generated files, and the PR body follows the project's template.
- Without `--oss`, behavior is unchanged.
- README documents the flag and its limits.

## Open questions

1. How does `--oss` relate to `--no-footprint` (#280)? One option is for `--oss` to imply it.
2. Should Uncle fork and open the PR from the fork automatically, or stop for the user to do that?
3. How should Uncle treat guidance that exists only in a wiki or an external site?
4. Should `--oss` be inferred when the issue's repository is not one the user has write access to?

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
