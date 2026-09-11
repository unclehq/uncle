# Change Specification
<<<<<<< HEAD

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
=======
Omitted sections: Performance requirements (no impact); Security requirements (no impact); Migration requirements (no impact); Rollback expectations (no rollback needed); Prototype-isolation requirements (not applicable).

## 1. Change type
Documentation display correction: capitalize the product name in `README.md` display copy only.

## 2. Problem statement
`README.md` uses lowercase `uncle` in the title and callout while prose uses `Uncle` (`BASELINE_REPORT.md:19,B-1;B-2`). This inconsistency weakens brand identity.

## 3. Current behavior
- Title/heading at `README.md:4` and callout at `README.md:28` read `uncle`.
- Prose at `README.md:10,13,36` already uses `Uncle`.
- CLI examples, paths, repository URLs, and package names remain lowercase (`BASELINE_REPORT.md:21-23,B-3;B-4`).

## 4. Desired behavior
Display copy (heading and callout) uses `Uncle`. Command, path, URL, filename, and package casing remain unchanged.

## 5. Acceptance criteria
| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `README.md` heading reads `Uncle` | Read `README.md:4` |
| AC-2 | `README.md` callout reads `Uncle` | Read `README.md:28` |
| AC-3 | CLI examples still use lowercase `uncle` | Grep `README.md` code blocks for lowercase `uncle` |
| AC-4 | `scripts/tests/install-test.py` passes | Run `PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/tests/install-test.py -q` |

## 6. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| B-1 | MODIFY | Read README heading | Lowercase `uncle` (`BASELINE_REPORT.md:19`) | `Uncle` | Read `README.md:4` |
| B-2 | MODIFY | Read README callout | Lowercase `uncle` (`BASELINE_REPORT.md:19`) | `Uncle` | Read `README.md:28` |
| B-3 | PRESERVE | Read README prose | Already `Uncle` (`BASELINE_REPORT.md:20`) | Remains `Uncle` | Read `README.md:10,13,36` |
| B-4 | PRESERVE | Follow CLI examples | Lowercase command `uncle` (`BASELINE_REPORT.md:21`) | Remains lowercase | Read `README.md:38,60` |
| B-5 | PRESERVE | Resolve image/install references | Lowercase paths/URLs (`BASELINE_REPORT.md:22`) | Remain lowercase | Read `README.md:2,47,54` |
| B-6 | PRESERVE | Build package | Archive/Debian builds pass (`BASELINE_REPORT.md:23`) | Still pass | Run AC-4 |

## 7. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | Installed command stays lowercase | Binaries, formula, installer | `uncle:51`; `Formula/uncle.rb:26` | `scripts/tests/install-test.py:107` |
| I-2 | EXISTING | Payload excludes state; rejects symlinks | Package builder | `scripts/install/build-package.py:14,40` | `scripts/tests/install-test.py:92,174` |
| I-3 | STRENGTHENED | README display capitalization is consistent | `README.md` display copy | `README.md` review | Read `README.md:4,28` |

No RELAXED or REMOVED invariants.

## 8. Compatibility requirements
- CLI name, package name, formula, installer URLs, and repository paths remain lowercase (`I-1`, `B-4`, `B-5`).
- Existing tests `C-3` and `C-4` continue to pass (`BASELINE_REPORT.md:48-54`).

## 9. Error and failure behavior
No change. Invalid arguments, missing dependencies, and package extraction errors remain as observed in `BASELINE_REPORT.md:48-57`.

## 15. Explicit non-goals
- Rename the repository, command, package, formula, or any source file.
- Change source code outside `README.md`.
- Modify install scripts, build scripts, or tests.
- Replace every `uncle` with `Uncle` globally.

## 16. Assumptions and unresolved questions
- ASSUMPTION: The request targets display copy only; commands and paths stay lowercase (`BASELINE_REPORT.md:72,U-1`). Broader scope requires revisiting `AC-3`, `B-4`, `B-5`, and `I-1`.
- UNRESOLVED: Remote download and browser rendering of `README.md` images/links are unverified (`BASELINE_REPORT.md:73,U-2`). Settled by manual render check or CI preview.
>>>>>>> b449b41 (changes uncle to Uncle)
