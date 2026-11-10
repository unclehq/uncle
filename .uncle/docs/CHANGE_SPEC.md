# Change Specification

Omitted sections: Migration (none), Prototype isolation (n/a), Performance (none beyond no regression), Security (see 10).

## 1. Change type
Bug fix.

## 2. Problem statement
Hosted runs use `scripts/reviewer-self-hosted.sh`, which the prompt-transport decision does not recognize, so prompts over 120000 bytes are refused and the build exits 1 (Issue 232).

## 3. Current behavior
Baseline B3.

## 4. Desired behavior
A reviewer command that runs `self_hosted.py` or `native_stage.py` (directly or via `reviewer-self-hosted.sh`) receives the prompt via `--prompt-file`; the decision is made in one shared helper used by both drivers.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| B1 | PRESERVE | stagegate client `python3 ...` | file | unchanged | existing CallSites tests |
| B2 | PRESERVE | change-workflow client with native_stage.py/self_hosted.py | file | unchanged | existing CallSites tests |
| B3 | MODIFY | client is `reviewer-self-hosted.sh`, prompt 200000 B, stagegate and change-workflow | argv, guard refuses | `--prompt-file PATH`, no argument >120000 B, no guard message | new wrapper-based tests |
| B3b | MODIFY | `UNCLE_HOSTED=1`, no runner config, big prompt | refused | wrapper selected via default runner and file mode used | new hosted test |
| B4 | PRESERVE | argv-only client (codex, claude, reviewer-kimi.sh, reviewer-claude.sh) with prompt >120000 B | guard refuses | unchanged | helper test + Guard tests |
| B5 | PRESERVE | argv client, small prompt | argv | unchanged | helper test |
| B6 | PRESERVE | two self-hosted candidates | race path, file | unchanged | code unchanged; existing candidate test |
| B7 | ADD | `reviewer_prompt_kind CMD...` | none | prints `file` or `argv` | helper unit test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I1 | EXISTING | argv-kind prompt >120000 B is never launched | both drivers | reviewer_prompt_guard | Guard tests |
| I2 | EXISTING | file-kind prompts are not guarded | both drivers | reviewer_prompt_guard | Guard tests |
| I3 | NEW | Prompt transport kind is decided only by `reviewer_prompt_kind` (plus stagegate's retained python3-first rule); an unrecognized command is `argv` | both drivers | reviewer-prompt.sh | helper test, grep of call sites |

No RELAXED or REMOVED invariants.

## 7. Compatibility
`reviewer_prompt_guard` signature and `REVIEWER_PROMPT_ARGV_LIMIT` unchanged. Existing client classification preserved.

## 8. Error behavior
argv-only client over limit still fails with the existing message and status 1.

## 12. Rollback
Revert the commit; no persisted state.

## 14. Non-goals
Changing the 120000 limit or guard message; changing `review_schema_setup`; changing the race path; changing `self_hosted.py`; making CI blocking.

## 15. Assumptions
The wrapper only `exec`s `self_hosted.py reviewer "$@"` (reviewer-self-hosted.sh:8). Linux-only E2BIG behavior is validated by the Linux CI job, not on the macOS dev host.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | A new shared helper `reviewer_prompt_kind CMD...` in scripts/lib/reviewer-prompt.sh prints `file` when any command element's basename is self_hosted.py, native_stage.py or reviewer-self-hosted.sh, and `argv` otherwise (codex, claude, reviewer-kimi.sh, reviewer-claude.sh, empty). | New helper unit tests in scripts/tests/reviewer-prompt-kind-test.py |
| AC-2 | stagegate.sh and change-workflow.sh both call the helper for the file/argv decision; the old change-workflow case patterns are removed. | Grep assertion in the new test plus existing CallSites tests staying green |
| AC-3 | Launching the real scripts/reviewer-self-hosted.sh (UNCLE_RUNTIME_ROOT pointing at a temp root with a recording fake self_hosted.py) with a 200000-byte prompt through the stagegate.sh launch block yields `--prompt-file <path>`, no argument over 120000 bytes, and no `prompt is N bytes` message. | New wrapper test, stagegate case |
| AC-4 | The same holds for the change-workflow.sh launch block. | New wrapper test, change-workflow case |
| AC-5 | With UNCLE_HOSTED=1 and no runner in .uncle/config, the resolved reviewer command is the wrapper and it is classified `file`. | New hosted-mode test using stage-config.sh resolution |
| AC-6 | Argument-only clients over 120000 bytes are still refused by reviewer_prompt_guard with the existing message; existing reviewer-prompt-file tests still pass. | bash scripts/run-python-tests.sh -- reviewer-prompt-file and a helper+guard negative test |
| AC-7 | The Linux CI workflow runs the new suite. | Inspect .github/workflows/linux-tests.yml; CI run on Linux |

