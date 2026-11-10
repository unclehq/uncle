# Change Plan

Source seed: https://github.com/unclehq/uncle/issues/232

Issue 232

Omitted sections: Schema/persistence, Migration, Concurrency, Feature flag, State transitions, Observability (none affected)

## 1. Selected technical approach

Add `reviewer_prompt_kind CMD...` to `scripts/lib/reviewer-prompt.sh`. Matching rule (AR-005): positional, not a scan of all elements. Only element 0 counts, or element 1 when the basename of element 0 is an interpreter (`python3`, `python`, `bash`, `sh`). The basename of that one element is compared with `self_hosted.py`, `native_stage.py` and `reviewer-self-hosted.sh`; a match prints `file`, otherwise `argv` (including zero arguments or only empty strings); the helper always returns 0. Later elements are never inspected, so an argv-only client whose later arguments are named like an allowlisted script stays `argv` and keeps its guard. The wrapper basename `reviewer-self-hosted.sh` counts only when the element's resolved path is under `${UNCLE_RUNTIME_ROOT}/scripts`; another script of that name found via PATH or a configured runner is `argv`. Both drivers call it with `"${client_cmd[@]}"`. Decision D1 (AR-006): stagegate keeps its existing `client_cmd[0]==python3` clause OR'd with the helper (preserving B1), so in stagegate a python3-first client is always `file` even when the helper alone says `argv`; this is a deliberate, documented stagegate-only divergence, and invariant I3 is amended to read 'the helper alone decides the allowlist everywhere; stagegate additionally treats a python3-first command as file'. Decision D2: change-workflow's two `case` lines are replaced by the helper alone, so there a python3-first client whose script is not allowlisted is `argv`. The test table pins both outcomes (stagegate and change-workflow), plus negative look-alike cases (later-argument look-alike, wrapper outside the runtime scripts dir). Bash 3.2 compatible, no associative arrays.

Decision D3 (AR-008): `reviewer_prompt_kind` with zero arguments, or only empty-string arguments, prints `argv` and returns 0. Call sites expand the array with the bash 3.2 `set -u`-safe form `${client_cmd[@]+"${client_cmd[@]}"}` so an empty or unset `client_cmd` neither aborts nor errors. Decision D4 (AR-007): kind is computed per candidate command, including in the `self-hosted.candidates 2` race path (race code itself unchanged); a wrapper candidate is classified `file` and an argv-only candidate in the same list stays `argv`. An automated test in `reviewer-prompt-kind-test.py` covers a two-candidate list (wrapper plus argv-only) in each driver.

## 2. Alternatives
(a) Add the wrapper name to each driver's check: rejected, drifts again. (b) Make the wrapper the python3 client: rejected, changes launch semantics. (c) Raise the limit: impossible (OS limit).

## 3. Why preferred
One decision point, exact allowlist, minimal diff.

## 4. Components to modify
See change-impact table.

## 5. Not to modify

`self_hosted.py`, `reviewer-self-hosted.sh`, `stage-config.sh`, guard logic and message, race path, `review_schema_setup`, and the retained `client_cmd[0]==python3` clause in stagegate (it must keep winning over the helper).

## 6. Data flow

Prompt for wrapper reviewers now flows by file path rather than argv. File lifecycle (existing prompt-file mechanism, not modified by this change): the prompt file is created mode 0600 in a per-run private directory and removed on exit, including on failure. The implementer confirms this by reading the existing code and the new test asserts it; any gap is recorded in IMPLEMENTATION_NOTES.md rather than silently patched.

## 8. Interface changes
Additive function `reviewer_prompt_kind`. Existing contract unchanged.

## 10. Compatibility
Existing classifications preserved; only the wrapper changes from argv to file.

## 12. Error and recovery
Unrecognized commands fall back to `argv`, still guarded.

## 14. Rollback plan
Revert the commit. No state or schema to restore.

## 16. Automated-test strategy

New `scripts/tests/reviewer-prompt-kind-test.py` (hyphenated name): (1) helper table test, including: zero arguments and an empty-string-only command, both printing `argv` with exit 0; element 0 allowlisted basename -> `file`; `python3`/`bash`/`sh` followed by an allowlisted script -> `file` (e.g. `python3 .../self_hosted.py`, `python3 .../native_stage.py`, `bash .../reviewer-self-hosted.sh`); `codex`, `claude`, `reviewer-kimi.sh` -> `argv`; allowlisted basename only in a later argument of an argv-only client (e.g. `codex --config self_hosted.py`, `claude reviewer-self-hosted.sh`, `codex exec reviewer-self-hosted.sh`, `python3 other.py native_stage.py`) -> `argv`; an interpreter-first command with a non-allowlisted script (`python3 other.py`) -> `argv` in the helper; (2) stagegate launch block extracted by the same markers as the CallSites tests but with `client_cmd` set from the real wrapper path and `UNCLE_RUNTIME_ROOT` at a temp root containing a copy of the real `scripts/reviewer-self-hosted.sh` and a fake `scripts/lib/self_hosted.py` recording argv; asserts `--prompt-file`, max arg length <=120000, no guard message, with a 200000-byte prompt, and that the prompt file is mode 0600, lives in a private per-run directory, and is gone after exit both on success and when the fake reviewer fails; also asserts the stagegate/change-workflow divergence: a `python3 other.py` client is sent as `file` by stagegate; (3) same for change-workflow block, where `python3 other.py` stays `argv` and is guarded; (4) hosted-mode: source `scripts/lib/stage-config.sh` with `UNCLE_HOSTED=1` and an empty config, resolve the reviewer command, assert it ends in `reviewer-self-hosted.sh` and the helper says `file`; (5) negative: `codex`, `claude`, `reviewer-kimi.sh` classify `argv`; a 200000-byte prompt makes the guard return 1; boundary: an argv-kind prompt of exactly 120000 bytes is allowed (guard returns 0) and 120001 bytes is refused (guard returns 1); (6) grep assertion that change-workflow.sh contains `reviewer_prompt_kind` and contains no `case` pattern over the basenames `native_stage.py` or `self_hosted.py` (so a reworded case over those names also fails); (7) a script named `reviewer-self-hosted.sh` located outside `UNCLE_RUNTIME_ROOT/scripts` classifies `argv`. Failing-before proof: step 4 runs tests 2-4 by assertion on the unmodified tree and records them failing (assertion failures, not errors) before steps 2-3 land; steps 2-3 then make them pass.

Added tests (AR-003, AR-004): (7) helper with no arguments and with only empty strings prints argv, exit 0; both drivers' launch blocks run with an empty client_cmd under bash set -u without aborting. (8) Guard boundary: an argv-kind client with a 120000-byte prompt is allowed, 120001 bytes returns 1 with the guard message. (9) Race path: a two-candidate list of the wrapper plus an argv-only client is classified per candidate, the wrapper as file and the other as argv, and the test asserts both launch forms in one run.

## 17. Regression strategy
Run existing `reviewer-prompt-file` suite plus the full shell and Python runners.

## 18. Manual verification

On Linux (CI or host): hosted run with prompts >128 KB shows `Launching reviewer (.../reviewer-self-hosted.sh)` and no `prompt is N bytes` line; repeat with `self-hosted.candidates 2`. Not performable on this macOS host.

The mixed-candidate race case (wrapper plus an argv-only client in self-hosted.candidates 2) is covered by automated test (9), so the Linux manual run only confirms it live.

## Change-impact table
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/reviewer-prompt.sh` | add `reviewer_prompt_kind` | single decision point | Low | new helper test |
| `scripts/stagegate.sh` | use helper at ~:2358, keep marker text | fix B3 | Low | wrapper test, CallSites |
| `scripts/change-workflow.sh` | replace two case lines at ~:2595-2597 with helper | fix B3, no drift | Low | wrapper test, CallSites |
| `scripts/tests/reviewer-prompt-kind-test.py` | new | AC-1..6 | None | itself |
| `scripts/tests/critical-suites.txt` | add `reviewer-prompt-kind` | run in default tier | Low | runner |
| `.github/workflows/linux-tests.yml` | add suite to named-suites command | AC-7 | Low | CI |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1: `reviewer_prompt_kind` prints `file` only when element 0's basename, or element 1's basename after an interpreter (python3, bash, sh) in element 0, is `self_hosted.py`, `native_stage.py` or `reviewer-self-hosted.sh`; every other command prints `argv`. Allowlisted names in later arguments are never matched. Zero arguments, or only empty-string arguments, print `argv` and return 0; call sites expand the array with the ${client_cmd[@]+"${client_cmd[@]}"} form so an empty or unset array does not abort under bash 3.2 set -u. Kind is computed per candidate command (race path included), so a wrapper and an argv-only candidate in a two-candidate list each get their own kind. The argv guard refuses only when the prompt is strictly over 120000 bytes (120000 allowed, 120001 refused). | B7 | I3 | reviewer-prompt.sh | helper test (table incl. positional cases: wrapper-named later argument => argv; empty and empty-string args => argv, exit 0), two-candidate mixed wrapper/argv test, prompt-size boundary test (120000 allowed, 120001 refused) | n/a |
| AC-2: both drivers classify via `reviewer_prompt_kind`; stagegate additionally keeps the python3-first clause (python3-first => file there), change-workflow uses the helper alone (python3-first with non-allowlisted script => argv). | B3 | I3 | stagegate.sh, change-workflow.sh | grep test, helper/driver table pinning the python3-first divergence | n/a |
| AC-3 | B3 | I2 | stagegate.sh | wrapper test | Linux hosted run |
| AC-4 | B3 | I2 | change-workflow.sh | wrapper test | Linux hosted run |
| AC-5 | B3b | I3 | stage-config.sh (read-only) | hosted test (runs offline, no network; fails, not skips, if the wrapper is not resolved) | Linux hosted run |
| AC-6: argv-only clients stay `argv` and guarded, including clients whose later arguments carry an allowlisted basename; stagegate's python3-first clause wins over the helper (python3-first is `file` in stagegate, `argv` in change-workflow unless the script is allowlisted). | B4, B5 | I1 | reviewer-prompt.sh | negative + existing Guard, later-argument allowlisted basename stays argv, python3-first divergence pinned in stagegate and change-workflow tests | n/a |
| AC-7 | B3 | n/a | linux-tests.yml | CI | CI run |

Restrictions:

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Fix 2 | AC-6 | guard unchanged for argv clients; python3-first precedence in stagegate preserved | no edit to guard function; stagegate's python3-first clause is retained and wins over the helper | explicit request | CAP-bash | CODING |
| R-2 | USER | CHANGE_REQUEST Fix 5 | AC-7 | Linux CI runs tests | edit linux-tests.yml | explicit request | CAP-ci | CODING; live on Linux CI in LIVE_VERIFICATION |
| R-3 | PLATFORM | bash 3.2 on macOS | AC-1 | portable helper; empty/unset client_cmd does not abort under bash 3.2 set -u | indexed loops only; positional (element 0/1) matching; call sites expand client_cmd with the set -u-safe form ${client_cmd[@]+"${client_cmd[@]}"} so an empty array does not abort under bash 3.2 | macOS default shell | CAP-bash | CODING |

Feasibility: `scripts/lib/reviewer-prompt.sh`, `stagegate.sh:2355-2367`, `change-workflow.sh:2595-2597` inspected; wrapper at `scripts/reviewer-self-hosted.sh:3-8` honors `UNCLE_RUNTIME_ROOT`. Live Linux check needs no credentials beyond CI. The element-0 / post-interpreter-element-1 matching rule needs only indexed array access, available in bash 3.2.

## Implementation sequence

1. Add helper `reviewer_prompt_kind` and document it in the header comment (decision D1/D2).
   Owns: `scripts/lib/reviewer-prompt.sh`
2. Wire stagegate.sh to the helper, preserving the `local prompt_kind=argv` and `        fi\n        # race_self` marker text.
   Owns: `scripts/stagegate.sh`
   Depends on: 1, 4
3. Wire change-workflow.sh to the helper, preserving the `. "$ROOT/scripts/lib/reviewer-prompt.sh"` and `        wait "$!"` markers.
   Owns: `scripts/change-workflow.sh`
   Depends on: 1, 4
4. Write the new test suite and run it on the unmodified tree, recording tests 2-4 failing by assertion (saved output) before steps 2-3 land; re-run after steps 2-3 to show them passing. Independent file, no code dependency beyond the helper name. The helper table test (1) must include a row pinning the divergence: a python3-first command with a non-allowlisted script classifies `argv` from the helper, `file` through the stagegate launch block (python3 clause OR'd) and `argv` through the change-workflow launch block. The hosted test (4) runs offline (no network, no credentials) and FAILS, not skips, if the wrapper path is not resolved; the wrapper basename counts only when its resolved path is under UNCLE_RUNTIME_ROOT/scripts, with a negative test for a same-named wrapper elsewhere.
   Owns: `scripts/tests/reviewer-prompt-kind-test.py`
5. Register suite and CI.
   
   Step 4 must record its failing-before run before steps 2 and 3 begin; steps 2 and 3 are then parallel-safe with each other (disjoint files).
   Owns: `scripts/tests/critical-suites.txt`, `.github/workflows/linux-tests.yml`
   Depends on: 4

## 21. Scope cuts under time pressure

Cut first: hosted-mode test (AC-5; it runs offline and fails rather than skips if the wrapper is unresolved, so cutting it is an explicit decision, never a silent skip), then CI edit; never cut helper and call-site wiring or the wrapper launch tests.

## 22. Risks

- Misclassifying an argv-only client as file would lose the prompt; mitigated by positional matching (element 0, or element 1 after python3/bash/sh) against the exact basename allowlist, with negative tests including an argv client carrying a wrapper-named later argument.
- Extraction-marker tests break if markers move; steps 2-3 keep marker text.
- Mixed race candidates (wrapper plus argv-only) must be classified per candidate; covered by an automated two-candidate test, not only the manual `self-hosted.candidates 2` run.
- Linux E2BIG behavior cannot be reproduced on macOS; CI covers it (continue-on-error, so a human must read the result).
- Unresolved: none blocking.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Scanning every element lets an argv-only client with a wrapper-named argument lose its prompt; the match must be positional. | s1.1 and s18.1.i1: helper matches only element 0, or element 1 when element 0 is python3/bash/sh; AC-1 updated. |
| AR-002 | Accepted | D1 ORing a python3 clause contradicts 'helper alone decides'; the divergence must be explicit and tested. | s1.1 D1 states python3-first is file in stagegate only (change-workflow uses helper alone); AC-2 and R-3 note it and tests pin both. |
| AR-003 | Accepted | Empty or unset client_cmd was unspecified; zero args or only empty strings must print argv with status 0 and not abort under bash 3.2 set -u. | Added empty-command behavior to AC-1 and R-3, and empty-command cases to s11 tests. |
| AR-004 | Accepted | Kind must be per candidate command and the guard boundary exact, so mixed race candidates and 120000 vs 120001 are pinned. | Added per-candidate classification and strict >120000 guard to AC-1, plus boundary and mixed-candidate tests in s11 and s13. |
| AR-005 | Accepted | Scanning every element lets an argv-only client with a matching argument lose its prompt; restricting to element 0 or the script after an interpreter removes that. | s1.1 helper rule narrowed to element 0 or the script argument after an interpreter; s11.1, AC-6 and s15.4 gain matching tests. |
| AR-006 | Accepted | The plan left unstated which rule wins in stagegate; the retained python3 clause must win and the divergence must be pinned. | s1.1 states the python3 clause wins in stagegate only; R-1, AC-6 and s11.1 pin the stagegate/change-workflow divergence. |
| AR-007 | Accepted | Race path code stays unchanged, but a wrapper in a two-candidate list must be pinned as classified per candidate. | Add s1 block stating per-candidate kind (wrapper => file) and add AC-1 note plus risk item requiring an automated two-candidate test. |
| AR-008 | Accepted | Zero-argument and unset-array behavior must be defined so bash 3.2 set -u cannot abort. | Add s1 block: helper prints argv and returns 0 for zero args; call sites expand with ${client_cmd[@]+"${client_cmd[@]}"}; update R-3 and AC-1. |
| AR-009 | Accepted | Moving the prompt from argv to a file is a new exposure, so the lifecycle must be stated and tested even though the existing prompt-file code is not modified. | Section 6 states the 0600 private-dir, removed-on-exit lifecycle; section 16 test (2) asserts mode and cleanup, including on failure. |
| AR-010 | Accepted | Matching any element lets an argv-only client with a look-alike argument skip the guard and lose its prompt. | Section 1 and AC-1 restrict matching to element 0, or element 1 when element 0 is python3/bash/sh; section 16 adds negative look-alike cases. |
| AR-011 | Accepted | Basename-only trust lets an unrelated script named reviewer-self-hosted.sh receive --prompt-file; restricting the wrapper to the runtime root closes that. | s1.1 and test strategy s11.1: the wrapper basename counts only when its resolved path is under UNCLE_RUNTIME_ROOT/scripts; negative test added. |
| AR-012 | Accepted | Failing-before proof must be ordered and recorded; steps 2-3 therefore depend on step 4 rather than being parallel. | Step 4 records tests 2-4 failing by assertion on the unmodified tree; steps 2 and 3 depend on step 4; parallel-safe note in step 5 corrected; s11.1 updated. |
| AR-013 | Accepted | Boundary and empty-command cases are real gaps in the test table and cheap to add. | s11.1 test (1) enumerates empty/zero-arg as argv; test (5) adds 120000-byte allowed and 120001-byte refused cases. |
| AR-014 | Accepted | An unnamed grep pattern would let a reworded case pass; naming the forbidden patterns pins it. | s11.1 test (6) now asserts no case over native_stage.py/self_hosted.py basenames and presence of reviewer_prompt_kind. |
| AR-015 | Accepted | The D1 divergence (python3-first is file in stagegate, argv in change-workflow) is real and untested; I3 must state it and tests must pin both. | Edit s1.1 to state the divergence and amend I3; add a test-table row pinning python3-first in both drivers. |
| AR-016 | Accepted | The hosted test's offline behavior and fail-vs-skip semantics are unspecified. | Edit AC-5 and s17.1 so the hosted test runs offline and fails, not skips, if the wrapper is not resolved. |
