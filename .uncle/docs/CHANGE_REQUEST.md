# Change Request

Issue 251

Seeded from [unclehq/uncle#251](https://github.com/unclehq/uncle/issues/251).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Hosted builds still can't give the person a preview link: the release grant (#236), the build script's link and sandbox changes (#207, #208) and #235's fix steps never shipped

## Motivation

## Summary

A person who hires the hosted build Employee still can't get a link to the app she builds. The five issues that built the preview path (#206, #207, #208, #209, #210) and the two that followed up (#235, #236) are all closed, but three parts never shipped:

1. **The release's grant for the signed-link call.** #209 was closed with no change. #236, its replacement, was closed by PR #237, which added no grant. That PR's own notes say so.
2. **The build script's link request and sandbox keep (#207, #208).** Both were closed on a change in the build script's repository that "was not merged when this was closed" and was "tested only with a mocked Daytona".
3. **#235's fix steps 1–3.** #235 was closed by PR #241, which only added the warning-page rule to `skills/uncle-build/SKILL.md` and two tests. PR #241's own final audit says "Issue 235 is not closed by this change alone".

The host's half works. A sandbox app answers through a signed link, including an app on `127.0.0.1`, so #235's step 4 needs no change (details below).

## What happens today

**Live test, 2026-11-11 17:29 UTC.** A fresh hire of the hosted Employee was serving release revision 41. The message was: *"Build a one-page website in plain HTML (no framework) that shows the heading "Preview link test" and a short paragraph. I don't need a pull request yet. I want to see it running first, so please send me the preview link to the running app."*

She replied after 8 seconds and made no tool calls:

> I can build this and open a pull request for it — that's how I work. I don't have a way to run or host a live preview app outside of that; my process always goes through a GitHub pull request, not a standalone running preview link.

She then asked for a repository. The chat-side gap is filed separately (see Related). This issue covers the parts that would still be missing once she runs a build.

**Host check, 2026-11-11 17:32–17:33 UTC,** through the host's Daytona publisher, in a throwaway sandbox (deleted afterwards):

| Step | Result |
|---|---|
| `python3 -m http.server 3000 --bind 127.0.0.1` and `… 3001 --bind 0.0.0.0` | Both answer inside the sandbox |
| `GET /sandbox/{id}/ports/3000/signed-preview-url?expiresInSeconds=1800` | `200`, `{port, sandboxId, token, url}` |
| Open the port-3000 link from another computer (curl, then Chrome) | `200` and the page. No warning page appeared in Chrome. |
| Open the port-3001 link | `200` and the page |
| `expiresInSeconds=7200` | `400`: "expiresInSeconds must be given once, as a whole number of seconds from 1 to 3600" |
| `POST /sandbox/{id}/ports/3001/signed-preview-url/{token}/expire` | `201`; the 3001 link then returns `401`, and the 3000 link still returns `200` |

So an app on the default `127.0.0.1` is reachable (#235 fix step 4: keep the default). The 3600-second cap is enforced, and the expire call works.

## Why: what never shipped

| Part | How it was closed | Evidence |
|---|---|---|
| Release grant for `GET /sandbox/{sandboxId}/ports/{port}/signed-preview-url` (#209) | Closed 2026-11-09 with no change | Closing comment: "Closed without a change … Reopen when the release definition is available." |
| Same grant (#236, replacing #209) | Closed 2026-11-10 by merging PR #237 (`2c956a6`) | PR #237's `.uncle/docs/IMPLEMENTATION_NOTES.md`: "AC-1 \| BLOCKED \| No grant added; release definition not in repo." AC-1 to AC-6 are all BLOCKED. The PR was "Published over a **NOT_READY** audit verdict". Its diff changes `scripts/lib/plan_steps.py`, `scripts/lib/self_hosted_http.py` and two tests, none of them about the grant. |
| Build script prints a signed link (#207) | Closed 2026-11-09 | Closing comment: implemented in the build script repository's PR #1, "not merged when this was closed … Tested only with a mocked Daytona." |
| Build script keeps the sandbox while the link works (#208) | Closed 2026-11-09 | Same comment: implemented in that PR #1, not merged when closed, "Tested only with a mocked Daytona." |
| #235 fix steps 1–3 and "Checks after the fix" 1–5 | Closed 2026-11-10 by merging PR #241 (`8b1182b`) | PR #241 changed only `skills/uncle-build/SKILL.md` (line 17, the warning-page rule) and two tests. Its `FINAL_AUDIT.md` FA-005 says: "Live Daytona checks (warning-page behavior, wildcard host reachability, out-of-repo build script and #236 release) were not performed … Issue 235 is not closed by this change alone." FA-012: the live checks are "BLOCKED and have no waiver". |

A hirer can't see a release's grants, so whether revision 41 has the grant can't be checked from outside. No record of adding it exists in this repository or in any issue or PR linked from the seven issues above.

## Code paths in this repository (main `b27e23c`)

Blame is `git blame`.

| Where | What it does | Last changed in |
|---|---|---|
| `scripts/lib/stage-config.sh:47-51` | `uncle_is_hosted`; in hosted mode, `UNCLE_PREVIEW_MODE` defaults to `host`. | `688d219` 2026-11-10 (#211, PR #223) |
| `scripts/stagegate.sh:7076`, `scripts/change-workflow.sh:5124` | At `COMPLETE`, calls `uncle_host_preview_hook`. | Added in `bd3cde0` 2026-11-09 (#206) |
| `scripts/lib/host_preview_hook.sh:7-17` | Runs `host_preview.py serve "$PWD"` in host mode and ignores failures. Lines 10-11 first stop the live preview so the finished app can take its port. | `bd3cde0` 2026-11-09 (#206); lines 10-11 `5abbe7d` 2026-11-11 |
| `scripts/lib/host_preview.py:217` | Binds the app to `UNCLE_PREVIEW_HOST`, default `127.0.0.1`. The host check above shows this default is reachable through a signed link. | `bd3cde0` 2026-11-09 (#206) |
| `scripts/lib/host_preview.py:290-301` | `serve` prints `UNCLE_PREVIEW_PORT=<n>` and always exits 0. This is the port the build script must ask a link for. | `bd3cde0` 2026-11-09 (#206) |
| The release definition (not in this repository) | Lists the script's publisher grants. The signed-link grant goes here. | |
| The build script (not in this repository) | Must request the signed link, print `Preview: <url> (works until …)` and keep the sandbox (#207, #208). | |

## Fix

1. **Release.** Add to the release's script publisher grants: publisher `daytona`, `GET /sandbox/{sandboxId}/ports/{port}/signed-preview-url`, `require_approval` false. Publish the release, and record its revision number on this issue.
2. **Build script.** Merge the #207 and #208 change, with #235's step 3:
   - Ask for `expiresInSeconds` of at most 3600. The host refuses anything larger with `400`.
   - Create the sandbox with `autoStopInterval` of at least the link's lifetime in minutes, and `autoDeleteInterval: 0`.
   - Print `Preview: <url> (works until HH:MM UTC)`, with a time no later than when the sandbox is sure to be stopped.
   - Keep the sandbox when a link was printed, delete expired kept sandboxes at the start of each run, and delete the sandbox as before when no link was printed.
3. **Address.** Keep `UNCLE_PREVIEW_HOST` at its default, `127.0.0.1`. It was verified above.
4. **Prove it end to end.** Run #235's "Checks after the fix" 1–5 on a real hosted build, and post the result here before closing.

## Tests

- Build script, with a mocked publisher: the link request has `expiresInSeconds` ≤ 3600. The create request has `autoStopInterval` ≥ the link lifetime in minutes and `autoDeleteInterval` 0. The printed end time is no later than the link's expiry. A `400` or `403` on the link request finishes the run with a reason and no `Preview:` line.
- Release: a check run before publishing confirms that the grant list contains the signed-link entry.

## Checks after the fix

On a real hosted build of a small web app:

1. The output has `Preview: https://… (works until …)`, and the chat reply shows it as a clickable link.
2. The link opens the app on another computer.
3. Wait 20 minutes without opening it, then open it: the app still loads (Daytona's 15-minute auto-stop).
4. After the end time, the sandbox is gone without another run.
5. A build that prints no link deletes its sandbox before it ends.

## Related

#206, #207, #208, #209, #210, #235, #236; PR #237, PR #241.

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
