# Change Request

Issue 174

Seeded from [unclehq/uncle#174](https://github.com/unclehq/uncle/issues/174).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Send all errors to stderr and surface them in --noui and the build window

## Motivation

## Problem
Errors from Uncle are not reliably visible. Programs that run Uncle (scripts, CI, wrappers) cannot see why a run failed.

## Desired behavior
- Every error is written to stderr.
- Errors are also displayed in `--noui` mode.
- Errors are also displayed in the build window.
- Errors must be visible to programs that invoke Uncle (stderr output plus a non-zero exit status on failure).

## Success criteria
- Triggering a failure with `--noui` prints the error on stderr (verifiable with `2>file`).
- The same error appears in the build window in UI mode.
- A calling program capturing stderr receives the error text.

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
