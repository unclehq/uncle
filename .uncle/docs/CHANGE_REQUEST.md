# Change Request

Issue 236

Seeded from [unclehq/uncle#236](https://github.com/unclehq/uncle/issues/236).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Release must allow Daytona's signed preview-link call: the host offers it now, but #209 was closed before it did

## Motivation

## Summary

A hosted build can only make the publisher calls its release lists. To print a preview link (#207), the release must list Daytona's signed-link call. #209 asked for that and was closed with no change, because the host's Daytona publisher didn't offer the call yet. A release that listed it was refused with `Template grant 'daytona GET …' must match one publisher operation.`

The host's Daytona publisher offers the call now. Until a release lists it, every hosted build's link request is refused and no `Preview:` line is printed. This is step 1 of #235.

## What the host offers now

Read from the host's Daytona publisher on 2026-11-10:

| Method and path | What it does | Limits |
|---|---|---|
| `GET /sandbox/{sandboxId}/ports/{port}/signed-preview-url` | A link to the port with its token inside, so it opens with a click. | `expiresInSeconds` at most 3600. Daytona's default is 60. |
| `POST /sandbox/{sandboxId}/ports/{port}/signed-preview-url/{token}/expire` | Ends a signed link early. | Needed only if the script ends links early. |
| `GET /sandbox/{sandboxId}/ports/{port}/preview-url` | The plain link. Its token goes in a request header, which a click can't send. | Not needed. |

The host classes the signed-link call as a change (a "mutation"), even though it is a GET.

## How the host checks the release's list

- Each entry is matched by method and path to exactly one publisher operation. The signed-link path differs from the plain-link path, so the entry matches one operation and needs no `operation_id`.
- A script entry for a call that makes a change is allowed without approval on each call. On the script surface the host supports per-call approval only for sending mail, so set `require_approval` to false or leave it out.
- Daytona runs on the host's own key, not on an account the person signed in with. Adding this entry doesn't make anyone approve the update before it installs.
- The release already declares Daytona for its script, since the script creates and deletes sandboxes through it.

## Fix

1. Add to the release's script publisher grants: publisher `daytona`, method `GET`, path `/sandbox/{sandboxId}/ports/{port}/signed-preview-url`, `require_approval` false.
2. Only if the script ends links early, add `POST /sandbox/{sandboxId}/ports/{port}/signed-preview-url/{token}/expire` the same way.
3. Have the script ask for an `expiresInSeconds` of at most 3600.
4. Publish a new release.

## Code paths (main `09a832b`)

Blame is `git blame`.

| Where | What it does | Last changed in |
|---|---|---|
| The release definition (not in this repository) | Lists the script's publisher grants. This is where the change goes. | |
| The build script (not in this repository) | Asks for the signed link to the port Uncle reports (#207). | |
| `scripts/lib/host_preview.py:281-292` | Prints `UNCLE_PREVIEW_PORT=<n>`, the port the script asks a link for. | `bd3cde00` 2026-11-09 (#206, committed without a PR) |
| `skills/uncle-build/SKILL.md:8-16` | Chat rules for the `Preview:` line the script prints. | `274a636e` 2026-11-09 (#210, PR #220) |

## History

- #207 (closed 2026-11-09): the build script asks for the signed link. It was written while the host still refused the call with 403.
- #209 (closed 2026-11-09, no change): closed because the grant couldn't be published until the host's publisher offered the call. The closing comment asked for it to be reopened once it could be. It can't be reopened, so this issue replaces it.
- #235: the end-to-end fix this unblocks.

## Tests

None in this repository: the change is in the release definition. The checks below run against the host.

## Checks after the fix

1. The release publishes without the "must match one publisher operation" refusal.
2. In a hosted build of a small web app, the signed-link call returns a link instead of being refused as not granted, and the output has a `Preview:` line.
3. An existing hire installs the new release without being asked to approve a Daytona write.

## Related

#206, #207, #208, #209, #210, #235.

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
