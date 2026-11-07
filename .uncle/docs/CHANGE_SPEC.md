# Change Spec

Omitted sections: Performance, Security, Migration, Prototype isolation (not applicable)

## 1. Change type
Behavior change (TUI runner selection).

## 2. Problem statement
With no runner CLI on PATH the runner choices are empty and the default runner is "". Self hosted needs no local CLI and should always be selectable.

## 3. Current behavior
Baseline B2.

## 4. Desired behavior
When discovery finds no runner, options and default are exactly `self-hosted` (shown "Self hosted"). Otherwise unchanged.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| C1 | MODIFY | No runner binary on PATH; open runner picker for any stage | empty list | only self-hosted | new Python test |
| C2 | MODIFY | No runner on PATH, no configured runner or DEFAULT_RUNNER | stage_runner returns "" | returns self-hosted | new Python test |
| C3 | PRESERVE | One or more runners installed | installed list in fixed order | identical list | new Python test with fake binaries |
| C4 | PRESERVE | Configured runner or DEFAULT_RUNNER set | that value | unchanged | existing suites |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| V1 | NEW | Runner list is never empty | runners_for | runners_for | new test |
| V2 | EXISTING | Installed runners yield unchanged order and content | runners_for | PATH scan | new test C3 |

No RELAXED or REMOVED invariants.

## 7. Compatibility
No change when any runner is detected.

## 8. Error and failure behavior
PATH diagnostics on stderr remain as today; unreadable PATH entries still count as not found, so fallback applies.

## 11. Rollback
Revert the one-line fallback.

## 14. Non-goals
Self-hosted config flow, other runners, unrelated cleanup, supervision runner semantics.

## 15. Assumptions
Supervision picker keeps its SUPPORTED_RUNNERS filter; it is unaffected beyond what that filter yields.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With no runner binaries on PATH, runners_for returns exactly ["self-hosted"] for both agent and reviewer sides, so the runner picker lists only self-hosted (displayed "Self hosted"). | New scripts/tests/runners-none-installed-test.py with an empty PATH directory. |
| AC-2 | With no runners installed and no configured runner or DEFAULT_RUNNER, stage_runner returns "self-hosted". | Same new test, calling stage_runner on a TUI instance. |
| AC-3 | With one or more runner binaries on PATH, runners_for output is unchanged (installed list, fixed order, opencode mapped to self-hosted, no extra entries). | Same new test with fake executables on PATH. |
| AC-4 | Existing shell and Python suites show no new failures versus baseline. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh compared to baseline. |

