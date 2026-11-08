# Change Request

Issue 190

Seeded from [unclehq/uncle#190](https://github.com/unclehq/uncle/issues/190).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Home composer: Enter submits, Ctrl+Enter inserts newline; support Claude CLI-style copy/paste

## Motivation

## Summary
Two improvements to the home page composer.

## 1. Key bindings
- **Enter** submits the composer text to the home supervisor.
- **Ctrl+Enter** inserts a newline in the composer instead of submitting.

## 2. Copy/paste
Allow copy and paste in the composer the way the Claude CLI does, including pasting multi-line text without it being submitted or mangled.

## Acceptance criteria
- Pressing Enter with non-empty text sends it to the home supervisor and clears the composer.
- Pressing Ctrl+Enter inserts a newline at the cursor and does not submit.
- Pasting text (single or multi-line) inserts it at the cursor; newlines in pasted text do not trigger submit.
- Copying selected composer text works with the standard system shortcut.

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
