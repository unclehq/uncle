# Change Request

Issue 231

Seeded from [unclehq/uncle#231](https://github.com/unclehq/uncle/issues/231).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

A project plan that fails its check ends a headless build (exit 1) with no repair turn; a code span on an Owns: line becomes an owned file

## Motivation

## Summary

A project plan that fails its check ends the build with exit 1. The error says `Correct the saved document and resume.`, but in a headless hosted run nothing does: the supervisor that reacts to validation failures runs only inside the TUI. Other stages already give the model one repair attempt; the project plan doesn't.

In this run, the token that failed the check was not a file the model meant to own. It was most likely a code span on the step's `Owns:` line that Uncle's parser took as a path.

## What happened (2026-11-10, UTC)

Headless self-hosted run on a host (no terminal in the sandbox) for a small Haskell app. After the parallel plan was discarded (#230), the single-pass plan was written, converted and checked. It failed:

```
.uncle/docs/PROJECT_PLAN.md: step-2 owns: replace '-- EOF-GUARD' with a file or glob (directory/**). Correct the saved document and resume.
```

Uncle exited 1 at 08:13:30, and the build ended with no code written. A one-line correction of that step's file list would have let it continue.

**Where `-- EOF-GUARD` most likely came from.** `plan_steps.paths()` (`scripts/lib/plan_steps.py:69-85`) takes **every** backticked span on an `Owns:` line as a path, with no check (`:70-71`). Without backticks it accepts only tokens matching `[\w./*?\[\]@-]+` (`:74-77`), which `-- EOF-GUARD` (it contains a space) does not. So the plan most likely had a line like ``Owns: `app/Tutorial.hs` (ends with a `-- EOF-GUARD` comment)``. The saved plan was deleted with the sandbox, so this is inferred from the code.

## Code paths (main `5a5cd30`)

Blame is `git blame -w`.

| Where | What it does | Last changed by |
|---|---|---|
| `scripts/stagegate.sh:4571-4594` | Single-pass plan: copies the investigation to `PROJECT_PLAN.md`, runs the shape-only repair (`repair_document_format.py`, `:4586-4588`), then `export-project-plan` and `render-project-plan` (`:4589-4592`), each `\|\| exit 1`. | `ed8609fb9` 2026-09-23, `82fbc92a9` 2026-10-27, `b3ef425f0` 2026-10-28 |
| `scripts/stagegate.sh:4602-4607` | `plan-unprotected` check: on failure it prints the error, calls `supervision_validation_failed`, and runs `exit 1`. No repair. | `ebe265a9a` 2026-09-23, `78d391a49` 2026-09-24 |
| `scripts/lib/plan_model.py:474-482` (in `validate`) | Rejects an `owns` token that isn't a valid path or is a directory. The check is right; the plan reached it with a bad token. | `1c89bbad9` 2026-10-31 |
| `scripts/lib/plan_context.py:358-361` | Prints `{path}: {error}. Correct the saved document and resume.` and exits 1. | `31bfe97b1` 2026-09-23, `ebe265a9a` 2026-09-23 |
| `scripts/lib/plan_steps.py:69-85` (`paths`) | Backticked spans on an `Owns:` line are taken as paths without the path-shape test that plain tokens get. All three `Owns:` routes use it (`:179`, `:224`, `:228`). | `a3a507e28` 2026-10-31, `e0a548e83` 2026-10-31 |
| `scripts/lib/plan_model.py:738-749` (`split_list`) | The JSON route: any string in an `owns` array is kept after stripping backticks. | `70af75017` 2026-10-28, `8c5257472` 2026-10-28 |
| `scripts/lib/supervision.sh:43-49` (`supervision_validation_failed`) | Only writes a status event. Its comment: "the outcome of that handling is unchanged". | `32b16e627` 2026-09-14 |
| `scripts/lib/supervisor.py:1204-1225` (`_validation_failed`) | Reacts to that event with a diagnosis and correction note. The supervisor runs inside the TUI (`uncle_tui.py:113`). | |
| `uncle:484-498` and `scripts/lib/uncle_headless.py` | With no terminal (a cloud sandbox, CI), a startup action runs headlessly through `uncle_headless.py`. That file never starts the supervisor or retries, so in hosted runs nothing reads the event. | |
| `scripts/stagegate.sh:6612-6627` | For comparison: the checklist acceptance report gets one retry with the format error as instructions before it exits 1. | `fbda706d8` 2026-10-30 |

## Fix

1. **Parser.** In `paths()`, apply the same path-shape test to backticked spans as to plain tokens, and drop spans that fail it, with a warning naming the step. Apply the same filter in `split_list` for `owns`.
2. **Repair once.** When the project-plan check fails (`stagegate.sh:4586-4607`, and the updated-plan check at `:5662-5666`):
   - Run one repair turn. Give the model the saved plan and the validator's exact errors, and ask it to fix only those.
   - Re-check, and exit 1 only if it still fails.
   - Use a one-time marker, as the checklist retry does, so it can't loop.
   - The repair turn is a model call, so it must also stop cleanly on a host spending stop (#230).
3. **Message.** In headless runs the "Correct the saved document and resume" message has no one to act on it. After a failed repair, say which file and step to fix and the command to resume.

## Tests to add

- `plan_steps` test: ``Owns: `app/Main.hs`, `test/Spec.hs` (ends with a `-- EOF-GUARD` comment)`` gives `owns == ['app/Main.hs', 'test/Spec.hs']`.
- Stage test: a single-pass plan whose step 2 owns `-- EOF-GUARD` gets one repair turn and continues. A plan still invalid after the repair exits 1 with the diagnostic, and no second repair runs.
- Headless run of the same, with no TUI.

## Related

- #230: the refused call that led to the single-pass plan.
- #226: a supervision setting that turned off corrections for unattended runs. This issue is about headless runs, which never start the supervisor.

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
