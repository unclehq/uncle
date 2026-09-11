# Change Specification

Omitted sections: Performance requirements (no claims); Security requirements (no new surface); Migration requirements (no migration); Prototype-isolation requirements (not a prototype).

## Change type

Bug Fix / Feature.

## Problem statement

`scripts/from-issue.sh --new` exits 1 when `REQUIREMENTS.md` is absent, although the user asked to seed a new application. BASELINE_REPORT.md §4 B-1, §9 T-8.

## Current behavior

- `--new` requires `REQUIREMENTS.md` with a `# Project brief` marker; absent marker exits 1 with no file written.
- `--new` with the marker preserves the prefix and replaces the brief section.
- `--change` writes `CHANGE_REQUEST.md` and prompts for `RUN`; auto-mode defaults to `--change` when `CHANGE_REQUEST.md` exists or the repo is non-empty.

## Desired behavior

- `--new` creates `REQUIREMENTS.md` when absent, seeded from the issue.
- `--new` with an existing `# Project brief` marker preserves the prefix and replaces the brief section.
- `--change` and auto-mode selection are unchanged.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `--new` with absent `REQUIREMENTS.md` exits 0 and creates it seeded with title/body. | Mocked fetch test |
| AC-2 | `--new` with existing `# Project brief` preserves prefix and replaces brief. | Existing test |
| AC-3 | `--change` behavior unchanged. | Existing tests |

## Observable behavior table

| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| B-1 | MODIFY | `--new`, `REQUIREMENTS.md` absent | Exit 1; no file | Create `REQUIREMENTS.md` seeded from issue | Mocked fetch test |
| B-2 | PRESERVE | `--new`, `# Project brief` exists | Keep prefix; replace brief through EOF | Keep prefix; replace brief through EOF | Existing test |
| B-3 | PRESERVE | `--change`, `CHANGE_REQUEST.md` absent | Write `CHANGE_REQUEST.md`; prompt `RUN` | Write `CHANGE_REQUEST.md`; prompt `RUN` | Existing tests |
| B-4 | PRESERVE | Auto mode | Select `--change` for existing request/code | Select `--change` for existing request/code | Existing tests |
| B-5 | PRESERVE | `--change`, EOF at prompt | Seed only; no run | Seed only; no run | Existing test |

## Invariant table

| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | `--new` writes `REQUIREMENTS.md` | `from-issue.sh` new path | `write_new_project_brief` | B-1, B-2 |
| I-2 | EXISTING | `--change` refuses to overwrite foreign in-flight run | `from-issue.sh` change path | `check_origin_or_refuse` | Existing tests |
| I-3 | EXISTING | Close requires matching run/origin/audit | Change workflow | `scripts/lib/issue-close.sh` | Existing tests |
| I-4 | **RELAXED** | New seed no longer requires existing `# Project brief` marker | `from-issue.sh` new path | `write_new_project_brief` | B-1 |
| I-5 | NEW | `--new` creates full `REQUIREMENTS.md` when absent | `from-issue.sh` new path | `write_new_project_brief` | B-1 |

## Compatibility requirements

- Preserve `--change` behavior (AC-3, B-3, B-5).
- Preserve `--new` behavior with existing marker (B-2).
- Absent-file `--new` path is additive.

## Error and failure behavior

- Fetch failure, invalid issue argument, or missing `python3`/`jq` exits non-zero.
- Write failure propagates via `set -e`.
- `--new` does not auto-run or close the issue.

## Rollback expectations

Revert `scripts/from-issue.sh`.

## Explicit non-goals

- Change `--change` flow, auto-mode selection, or issue-close logic.
- Add prompt or auto-run to `--new`.
- Alter `REQUIREMENTS.md` template beyond issue title/body seeding.

## Assumptions and unresolved questions

- ASSUMPTION: Absent-file `REQUIREMENTS.md` uses the project-brief template shape consumed by `./scripts/stagegate.sh` (BASELINE_REPORT.md §3 K-2).
- UNRESOLVED: Source template from project-root `REQUIREMENTS.md` or maintain it inside `scripts/from-issue.sh` (implementation decision).
