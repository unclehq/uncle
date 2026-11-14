# Change Request

Issue 264

Seeded from [unclehq/uncle#264](https://github.com/unclehq/uncle/issues/264).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Build script gets the preview link once, early in the build, and never renews it, so a hosted build longer than an hour hands over an expired link

## Motivation

## What happens

In hosted mode, the build script (`build-with-uncle/scripts/build.py`) gets a signed preview link exactly once: the first time Uncle's preview appears, which is usually a minute or two into the build.

- `announce_preview` runs on each poll while Uncle works. When `.uncle/preview.json` names a port, it calls `signed_preview`, prints `Preview: <url> (works until <time>)`, sets `sb.announced = True`, and never asks again.
- At the end of `build`, after the pull request, `if getattr(sb, "announced", False): return 0` skips the final link request, because a link was already printed.

The host allows at most 3600 seconds for a signed link (#263). The chat agent sees the script's output only when the build ends, so it passes on the link made at the start, not one made at the finish. Any build that ends more than an hour after its preview appeared hands the person a link that has already expired. Hosted builds may run for up to 4 hours.

Example from a hosted build on 2026-11-13: the preview appeared at +00:01 and the link was valid until +01:01. At +00:12 the build had only finished planning, with five plan steps, the audit and the pull request still to come.

`sb.link_expires` keeps the first link's expiry too. That value is the label `cleanup_expired` uses at the start of the next build, and it's the time printed in `kept for the preview link until`.

## Fix

1. At the end of `build`, after the pull request, always get a fresh signed link and print it as the last `Preview:` line, even if one was printed earlier. Keep the early link while the build runs, for anyone watching it live.
2. Set `sb.link_expires` from the new link, so the kept-sandbox label and the `kept ... until` line follow the link the person actually receives.
3. Optional: expire the earlier link with `POST /sandbox/{id}/ports/{port}/signed-preview-url/{token}/expire` (the host allows it), so only one live link exists.

Related: `Sandbox()` sets `autoStopInterval` from `LINK_SECONDS[0] // 60`, which is 120 minutes while the first lifetime is 7200 (#263). With links capped at an hour, a kept sandbox can keep running, and costing, for up to an hour after its link expires. Fixing #263 to ask for 3600 first also brings this down to 60, which still covers a link made at the end of the build.

## Test

Build script, with a mocked publisher and clock: the preview appears at 1 minute and the build ends at 70 minutes. The last `Preview:` line's end time is at least 55 minutes after the build ends, the kept-sandbox label matches it, and a build whose link was never refused makes no `signed-preview-url` request with `expiresInSeconds` above 3600.

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
