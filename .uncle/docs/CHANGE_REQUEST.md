# Change Request

Issue 263

Seeded from [unclehq/uncle#263](https://github.com/unclehq/uncle/issues/263).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Build script still asks for a 7200-second preview link, so the host refuses every hosted build's first link request (#235 step 2 and #251 didn't ship this part)

## Motivation

## What happens

In a hosted build on 2026-11-13, the host refused the build script's first signed-link request, and the retry worked:

| Time (UTC) | Request | Result |
|---|---|---|
| 23:46:44 | `GET /sandbox/{id}/ports/5173/signed-preview-url?expiresInSeconds=7200` | `400`: "expiresInSeconds must be given once, as a whole number of seconds from 1 to 3600." |
| 23:46:45 | The same request with `expiresInSeconds=3600` | `200`. The build printed `Preview: https://5173-<token>.daytonaproxy01.net (works until 00:46 UTC)` |

The person still gets a working link. But every hosted build makes one request the host refuses, and the host now records each refusal as an error, so every build adds a false error to the host's logs.

The rest of #251's link steps shipped: the sandbox was created with `autoStopInterval` 120 and `autoDeleteInterval` 0, and the printed end time matches the link's expiry.

## Why

The host caps signed preview links at 3600 seconds on purpose. A signed link opens the sandbox's app for anyone holding it, so the host keeps it short and expires it when the task ends. #235 (fix step 2) and #251 asked the script for at most 3600, and both are closed, but the shipped script still asks for 7200 first and depends on #207's shorter-lifetime retry.

## Fix

Ask for `expiresInSeconds=3600` or less on the first request. Keep the retry in case a request is refused.

## Test

Build script, with a mocked publisher: the first signed-link request has `expiresInSeconds` of at most 3600, and a build that gets its link makes no refused link request.

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
