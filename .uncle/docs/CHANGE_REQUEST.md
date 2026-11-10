# Change Request

Issue 235

Seeded from [unclehq/uncle#235](https://github.com/unclehq/uncle/issues/235).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Hosted preview link has never worked end to end: the signed-link call is offered now (#236 replaces #209), #208 is untested against Daytona, and Daytona's 15-minute auto-stop ends the app before the link expires

## Motivation

## Summary

For a hosted build, the person who asked for it sees the finished app through a link in the chat. Five issues built that path, and all are closed: #206 (Uncle serves the app for the host), #207 (the build script gets a signed Daytona link), #208 (the script keeps the sandbox while the link works), #209 (the release allows the signed-link call) and #210 (the chat passes the link on).

The path has never run end to end. No hosted build has printed a `Preview:` line yet:

- **#209 was closed with no change,** because the host's Daytona publisher didn't offer the signed-link call yet. It does now, and #236 replaces #209. The publisher lists `GET /sandbox/{sandboxId}/ports/{port}/signed-preview-url`, with `expiresInSeconds` "at most 3600", and `POST /sandbox/{sandboxId}/ports/{port}/signed-preview-url/{token}/expire`.
- **#208 was closed on a change that wasn't merged yet** and was "tested only with a mocked Daytona."
- **#206's last check was never run:** whether the host's link reaches an app listening on `127.0.0.1`. No link could be made to try it.

Two things the earlier issues didn't cover:

- **Daytona's auto-stop doesn't count a running app as activity.** Per Daytona's sandbox docs, auto-stop defaults to 15 minutes. Only preview visits, toolbox calls, SSH and lifecycle changes reset it; "merely having a script or background task running is not sufficient to keep the sandbox alive." Stopping ends every process in the sandbox. So with the default, a link nobody opens within 15 minutes of the build ending reaches a sandbox with no app, even though the chat said the link works for an hour. A signed link survives a restart; the app does not.
- **Daytona shows a warning page** the first time a browser opens each preview link ([Preview and authentication](https://www.daytona.io/docs/en/preview-and-authentication/)). Accepting it lasts 24 hours for that link only, so the person sees it after every build. A click can't send the header that skips it. Removing it needs a higher Daytona account tier or a custom preview proxy, and neither is planned, so the chat should prepare the person for it.

## How it happens

1. Hosted mode defaults `UNCLE_PREVIEW_MODE` to `host` (`stage-config.sh:51`).
2. When a build completes, both drivers call `uncle_host_preview_hook` (`stagegate.sh:6830-6831`, `change-workflow.sh:5020-5021`), which runs `host_preview.py serve`.
3. `serve` starts the app in its own session, on `UNCLE_PREVIEW_HOST`, default `127.0.0.1` (`host_preview.py:210`), and prints `UNCLE_PREVIEW_PORT=<n>` (`:290`).
4. The build script, kept outside this repository, asks the host's Daytona publisher for a signed link to that port (#207), prints `Preview: <url> (works until …)` and keeps the sandbox (#208).
5. The chat instructions pass the `Preview:` line on as a clickable link (`skills/uncle-build/SKILL.md:12-16`).

Steps 4 and 5 have not happened in a real hosted run. Step 4's call was refused until the publisher offered it, and the release that would allow it (#236, replacing #209) hasn't been published.

## Code paths (main `09a832b`)

Blame is `git blame`.

| Where | What it does | Last changed in |
|---|---|---|
| `scripts/lib/stage-config.sh:47-51` | `uncle_is_hosted`; hosted mode defaults `UNCLE_PREVIEW_MODE` to `host`. | `688d2194` 2026-11-09 (#211, PR #223) |
| `scripts/stagegate.sh:6830-6831`, `scripts/change-workflow.sh:5020-5021` | The `COMPLETE` branch sources and calls `uncle_host_preview_hook`. | `bd3cde00` 2026-11-09 (#206, committed without a PR) |
| `scripts/lib/host_preview_hook.sh:7-15` | Runs `host_preview.py serve "$PWD"` only in host mode; failures are ignored. | `bd3cde00` 2026-11-09 (#206) |
| `scripts/lib/host_preview.py:210-213` | The app's address is `UNCLE_PREVIEW_HOST`, default `127.0.0.1`. | `bd3cde00` 2026-11-09 (#206) |
| `scripts/lib/host_preview.py:50-63` | `valid_host` accepts `localhost` or any IPv4 address, `0.0.0.0` included. `urls_for` checks a `0.0.0.0` app through `127.0.0.1`. | `bd3cde00` 2026-11-09 (#206) |
| `scripts/lib/host_preview.py:241-243` | Starts the app with `group_options()`, which is `start_new_session=True` (`process_tree.py:203-206`, `fd6272d5` 2026-09-09), so it outlives Uncle. | `bd3cde00` 2026-11-09 (#206) |
| `scripts/lib/host_preview.py:281-292` | `serve` prints `UNCLE_PREVIEW_PORT=<n>` and always exits 0. | `bd3cde00` 2026-11-09 (#206) |
| `skills/uncle-build/SKILL.md:8-16` | Chat rules for the `Preview:` line. Nothing about Daytona's warning page. | `274a636e` 2026-11-09 (#210, PR #220) |

The build script's signed-link request (#207), its sandbox keep and limits (#208), and the release's publisher grants (#209) are not in this repository.

## Fix

1. **Allow the call and publish (#236, which replaces #209).** Add `GET /sandbox/{sandboxId}/ports/{port}/signed-preview-url` to the release's script publisher grants, plus the `expire` call if the script ends links early, and publish a new release. A hirer can't see a release's grants, so whoever publishes the release has to confirm this.
2. **Ask for at most 3600 seconds.** That's the host's limit and Daytona's recommended lifetime. Keep #207's retry with a shorter lifetime if one is refused.
3. **Ship #208's change, with auto-stop set from the link.** Create the sandbox with `autoStopInterval` of at least the link's lifetime in minutes (60 for a 3600-second link) and `autoDeleteInterval: 0`, so Daytona deletes it as soon as it stops and nothing keeps costing the person afterward. The printed "works until" time must be no later than the time the sandbox is sure to still be running.
4. **Check the app's address against real Daytona (#206's step 4).** If the link can't reach an app on `127.0.0.1`, have the build script set `UNCLE_PREVIEW_HOST=0.0.0.0`. `host_preview.py` already accepts it, and its own checks still go through `127.0.0.1` (`:62`, `:119`), so nothing else changes. If `127.0.0.1` works, keep the default.
5. **Tell the person about the warning page.** Add a rule to `skills/uncle-build/SKILL.md`: when relaying a link, say that Daytona shows a warning page first and they should continue past it to reach the app. Don't quote a button name; Daytona may change its wording.

## Tests

- Build script, with a mocked publisher: a run that prints a link creates its sandbox with `autoStopInterval` of at least the link's lifetime in minutes and `autoDeleteInterval` 0, asks for `expiresInSeconds` of at most 3600, and prints an end time no later than the link's expiry.
- `scripts/tests/chat-skill-test.py`: add a pattern requiring the warning-page rule, beside `preview-line` and `why-when-no-link`.
- If step 4 needs `0.0.0.0`: a `host_preview.py serve` test with `UNCLE_PREVIEW_HOST=0.0.0.0` showing the app answers on a non-loopback address and `.uncle/preview.json` records that host.

## Checks after the fix

In a real hosted build with a real Daytona sandbox:

1. A build of a small web app prints `Preview: https://… (works until …)`, and the chat reply shows a clickable link with the warning-page note.
2. The link opens the app from another computer, after Daytona's warning page.
3. Wait 20 minutes without opening the link, then open it: the app still loads. This is the 15-minute auto-stop case.
4. After the end time, the sandbox is gone without another run.
5. A build that prints no link deletes its sandbox before it ends, as today.

## Related

- #206, #207, #208, #209, #210: the five parts of this path.
- #236: the release permission, replacing #209.
- #211: hosted mode.
- #230, #231, #232: the latest hosted builds stopped at these before completing, so the preview step isn't reached until they're fixed.

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
