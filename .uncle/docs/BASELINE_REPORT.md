# Baseline Report

Omitted sections: Reproduction (requires Linux host; covered by Linux CI), Areas outside change folded into section 12.

## 1. Change-request summary
See CHANGE_REQUEST.md (Issue 232). Hosted reviewers launched via `scripts/reviewer-self-hosted.sh` are classified `argv`, so prompts over 120000 bytes are refused by the guard although `self_hosted.py` accepts `--prompt-file`.

## 2. Repository architecture
Bash drivers (`scripts/stagegate.sh`, `scripts/change-workflow.sh`) build a reviewer client command, source `scripts/lib/reviewer-prompt.sh`, and pass the prompt either as `--prompt-file PATH` or as one argv element. Python helpers in `scripts/lib/`. Wrapper `scripts/reviewer-self-hosted.sh:8` does `exec python3 $ROOT/scripts/lib/self_hosted.py reviewer "$@"`.

## 3. Relevant code paths
- `scripts/lib/reviewer-prompt.sh:8-45` limit and `reviewer_prompt_guard NAME KIND FILE`.
- `scripts/stagegate.sh:2255-2270` client_cmd construction; `:2355-2367` kind decision (`client_cmd[0]==python3`) and guard; `:2343-2350` race path (already file).
- `scripts/change-workflow.sh:2501-2508` client_cmd; `:2595-2597` kind decision via two `case` patterns.
- `scripts/lib/stage-config.sh:47-49,241-243` hosted default runner and wrapper selection.
- `scripts/tests/reviewer-prompt-file-test.py:160-248` CallSites tests extract script text between literal markers (`local prompt_kind=argv` ... `        fi\n        # race_self`; `. "$ROOT/scripts/lib/reviewer-prompt.sh"` ... `        wait "$!"`).
- `.github/workflows/linux-tests.yml` runs `bash scripts/run-python-tests.sh -- reviewer-prompt-file`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B1 | Reviewer client `python3 ... ` (stagegate) any size | `--prompt-file` used, no guard | stagegate.sh:2358 | Yes |
| B2 | change-workflow client containing native_stage.py/self_hosted.py | `--prompt-file` | change-workflow.sh:2595-2596 | Yes |
| B3 | Client `reviewer-self-hosted.sh` , prompt >120000 B | kind=argv, guard refuses, exit 1 | issue report; stagegate.sh:2358 | No (bug) |
| B4 | argv-only client (codex, claude, reviewer-kimi.sh, reviewer-claude.sh), prompt >120000 B | guard refuses with message | reviewer-prompt.sh:36-39 | Yes |
| B5 | argv client, prompt <=120000 B | prompt passed as argv | stagegate.sh:2365 | Yes |
| B6 | Multi-candidate self-hosted race | `--prompt-file` via race path | stagegate.sh:2343-2350 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I1 | argv-kind prompt strictly >120000 bytes is never launched | reviewer_prompt_guard | reviewer-prompt-file-test.py Guard | High |
| I2 | file-kind prompts are never guarded | guard `file)` branch | Guard.test_file_capable_never_guarded | High |

## 6. Contracts
`reviewer_prompt_guard NAME KIND FILE` (return 0/1/2) is a fixed contract; unchanged. `self_hosted.py reviewer` accepts `--prompt-file` (self_hosted.py:452-492).

## 7. Existing automated-test coverage
`scripts/tests/reviewer-prompt-file-test.py` (Python unittest, in critical-suites via `reviewer-prompt-file`): guard boundaries, arg parsing, call-site launches using `client_cmd=(python3 fake)`. No test launches through `reviewer-self-hosted.sh`. Parallel group: the shell runner and Python runner use separate temp dirs and bind no shared ports.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh` (Uncle project rules). Not run by this stage; the driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Repository documents that some Python suites already fail on a clean checkout. The Linux workflow is marked continue-on-error.

## 10. Existing failures
None documented specific to this change; unrelated Python suite failures may pre-exist.

## 11. Reproduction
UNRESOLVED on this macOS host: the 131,072-byte per-argument limit is Linux-specific. The classification defect is reproducible by logic: `client_cmd[0]` is the wrapper path, not `python3`.

## 12. Likely change surface
`scripts/lib/reviewer-prompt.sh`, `scripts/stagegate.sh`, `scripts/change-workflow.sh`, new test, `scripts/tests/critical-suites.txt` (if needed), `.github/workflows/linux-tests.yml`.

## 13. Regression-sensitive components
The race path, argv-only clients, and the marker-based extraction in the existing CallSites tests (markers must remain intact).

## 15. Unknowns and assumptions
- `review_schema_setup` at stagegate.sh:2270 also keys on `client_cmd[0]==python3`; assumed unrelated to prompt transport and left alone.
- Linux not available here; actual E2BIG behavior verified only by CI.

## 16. Initial risk assessment
Low: small classification change. Main risk is misclassifying an argv-only client as file (prompt silently lost); mitigated by an exact allowlist.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- reviewer-prompt-file
bash scripts/run-python-tests.sh -- reviewer-prompt-kind
```

## Parallel verification groups

```text
1 2
```

