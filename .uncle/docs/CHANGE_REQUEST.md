# Change Request

Issue 246

Seeded from [unclehq/uncle#246](https://github.com/unclehq/uncle/issues/246).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

--noui builds should show the preview and the app as they build, as the UI does

## Motivation

## Problem
Builds started with `--noui` (or `UNCLE_NOUI=1`) do not show the preview and the app as the build progresses the way builds in the full-screen UI do.

## Desired behavior
- A `--noui` build shows the preview and the app as it builds, in the same way the non-`--noui` build does (for example by printing the preview link/URL and app location/status as they become available).
- Users still see the preview and the app while the build runs, not only after it ends.

## Notes
- See docs/noui.md for the current `--noui` contract (exit codes, signals, plain output).
- Must not start curses or change `--noui` exit codes.

## Success criteria
- Running a build with `--noui` surfaces the preview and the app during the build, matching what the UI build shows.
- Existing `--noui` behavior and exit codes are unchanged.

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
