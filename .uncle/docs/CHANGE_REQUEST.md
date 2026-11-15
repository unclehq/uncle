# Change Request

Issue 282

Seeded from [unclehq/uncle#282](https://github.com/unclehq/uncle/issues/282).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Review the full issue thread, including comments, when creating a change request

## Motivation

## Summary

When Uncle builds a change request from a GitHub issue, it should read the whole issue: the body and every comment in the thread. The change request must reflect what the thread asks for now, not only what the opening post said.

## Current behavior

`scripts/from-issue.sh` fetches comments with `gh issue view --json ...,comments` and, on the Python path, appends each comment to the body under a `### Comment from <author>` heading. That works only on one path:

- **curl fallback** (no `gh`, or `gh` not authenticated): the REST `issues/<n>` endpoint does not include comments, so they are silently dropped.
- **jq fallback** (no `python3`): only `.body` is extracted, so comments are dropped.
- **Long threads:** there is no check that the fetch returned every comment, so a truncated or paginated fetch is indistinguishable from a complete one.
- **Thread meaning:** comments are concatenated in order, with no handling of the cases where the thread changes the request.

## Desired behavior

- **Every fetch path returns the full thread.** The curl path also calls `issues/<n>/comments` and follows pagination. The jq path includes comments. A run that cannot fetch comments says so instead of proceeding as though there were none.
- **Completeness is checked.** Uncle compares the number of comments it received with the issue's comment count and fails loudly, or warns, on a mismatch.
- **The thread is reviewed, not just appended.** When drafting the change request, Uncle identifies:
  - clarifications and added requirements from comments;
  - comments that supersede or contradict the opening post (the later maintainer statement wins, and the change request says so);
  - edited comments and the body's current text, not an earlier version;
  - discussion that is not a requirement, such as +1s and status chatter, kept out of the requirements.
- **Provenance is preserved.** Each requirement in the change request traces back to the body or to a specific comment (author and link), so a reviewer can check the source.
- **Untrusted input.** Comment text is untrusted input, the same as the body. It cannot override Uncle's rules or approval gates. Comment authorship is recorded, and the existing handling for untrusted piped text applies.

## Acceptance criteria

- A test issue with a clarifying comment produces a change request that includes that clarification on the `gh`, curl and jq paths.
- A comment that contradicts the body produces a change request that follows the later statement and records the conflict.
- A thread longer than one API page is fully included, and a short fetch fails or warns.
- Noise-only comments do not appear as requirements.
- Each requirement cites its source (body or comment).
- A comment containing instructions aimed at the agent does not change Uncle's behavior.
- README or GITHUB_INTEGRATION.md documents that the whole thread is read.

## Open questions

1. Should comments from non-collaborators be included by default, flagged, or excluded?
2. Should a very long thread be summarized, and how does the summary stay faithful to the source?
3. How should a thread that changes after the change request is drafted (new comments mid-run) be handled?

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
