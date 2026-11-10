## AR-001: Plan does not say what happens when a command has both an allowlisted basename and an argv-only client.

- Severity: HIGH
- References: CHANGE_PLAN s1: 'print `file` if any basename is ...'; Risks s22 says misclassification loses the prompt.
- Failure: Plan does not say what happens when a command has both an allowlisted basename and an argv-only client. The helper prints `file` if ANY element matches, so a wrapper around an argv client would misclassify and drop the prompt. Decide: match any element, or only client_cmd[0] and the interpreter's first script argument.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Stagegate D1 ORs the retained python3-first rule with the helper, yet AC-1/I3 say the helper alone decides.

- Severity: MEDIUM
- References: CHANGE_SPEC I3 vs CHANGE_PLAN s1 D1; AC-2 says both drivers call the helper.
- Failure: Stagegate D1 ORs the retained python3-first rule with the helper, yet AC-1/I3 say the helper alone decides. Decide: python3 always yields `file` in stagegate, while change-workflow uses only the helper.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Empty or unset client_cmd is unspecified at the call sites.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 lists 'empty' as argv, but the plan does not cover empty-array expansion in either driver.
- Failure: Empty or unset client_cmd is unspecified at the call sites. Decide: `reviewer_prompt_kind` with no arguments, or only empty strings, prints `argv` and returns 0, and an empty `"${client_cmd[@]}"` expansion under bash 3.2 `set -u` must not abort.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The guard boundary (exactly 120000 bytes) and mixed race candidates (wrapper plus argv-only) are unspecified.

- Severity: MEDIUM
- References: CHANGE_SPEC B6 says the race path is unchanged and B3 covers 'candidates 2' only manually; the boundary is not stated in B4/B5.
- Failure: The guard boundary (exactly 120000 bytes) and mixed race candidates (wrapper plus argv-only) are unspecified. Decide: kind is computed per candidate command, and the guard refuses only when the prompt is strictly over 120000 bytes.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The helper scans every element, so an argv-only client with an argument whose basename is self_hosted.py, native_stage.p

- Severity: HIGH
- References: CHANGE_PLAN s1: "loop over elements, strip dirs, and print file if any basename is..."; risk s22 relies only on the exact basename allowlist.
- Failure: The helper scans every element, so an argv-only client with an argument whose basename is self_hosted.py, native_stage.py or reviewer-self-hosted.sh is classified file and loses its prompt. Decide: only element 0, or element 1 when element 0 is an interpreter (python3, bash, sh), counts.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Under D1, stagegate sends a python3 client as file even if the helper says argv, and the plan does not say which wins.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 D1 vs CHANGE_SPEC I3; AC-6 negative tests have no python3 case.
- Failure: Under D1, stagegate sends a python3 client as file even if the helper says argv, and the plan does not say which wins. Decide: the python3 clause wins in stagegate, and I3 is amended to say so.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: B6 calls the race path unchanged, but the plan never says how a wrapper in a two-candidate list is classified.

- Severity: MEDIUM
- References: CHANGE_SPEC B6 "code unchanged; existing candidate test"; CHANGE_PLAN s18 checks candidates 2 only manually.
- Failure: B6 calls the race path unchanged, but the plan never says how a wrapper in a two-candidate list is classified. Decide: it is classified file, and an automated test covers it.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The plan does not say what the helper does with zero arguments, or whether expanding an unset client_cmd array is safe u

- Severity: LOW
- References: CHANGE_SPEC AC-1 "empty"; CHANGE_PLAN R-3 and s1 call form "${client_cmd[@]}".
- Failure: The plan does not say what the helper does with zero arguments, or whether expanding an unset client_cmd array is safe under set -u on bash 3.2. Decide: expand with a guard, and the helper prints argv for zero arguments.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The plan does not say where the --prompt-file is created, its permissions, or when it is deleted.

- Severity: MEDIUM
- References: CHANGE_PLAN s6 says the prompt flows by file path; no file lifecycle or permissions are stated, and the prompt-file code is listed as unchanged.
- Failure: The plan does not say where the --prompt-file is created, its permissions, or when it is deleted. Moving the prompt from argv to a file is a new exposure. Settle it with: 'Prompt files are created mode 0600 in a per-run private directory and removed on exit, including on failure.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The allowlist matches any element of the command.

- Severity: MEDIUM
- References: CHANGE_PLAN s1: 'if any basename is'; AC-1: 'any command element'. The negative tests in s16 cover only codex, claude and reviewer-kimi.sh.
- Failure: The allowlist matches any element of the command. An argv-only client with an argument ending in self_hosted.py, native_stage.py or reviewer-self-hosted.sh would be classed as file and skip the guard. Settle it with: 'Only client_cmd[0], or the script argument after an interpreter, is matched.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The wrapper is trusted by basename alone.

- Severity: LOW
- References: CHANGE_PLAN s1 and AC-1 match by basename after directories are stripped.
- Failure: The wrapper is trusted by basename alone. Another script named reviewer-self-hosted.sh, found via PATH or a configured runner, would receive --prompt-file. Settle it with: 'The wrapper is recognized only when its resolved path is under UNCLE_RUNTIME_ROOT/scripts.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan does not say how 'fails on current tree' is proven for tests 2-4, yet steps 2,3,4 are called parallel-safe.

- Severity: HIGH
- References: CHANGE_PLAN s16 'Failing-before' and Step 4 'written first against current tree' versus 'Steps 2, 3 and 4 are parallel-safe'.
- Failure: Plan does not say how 'fails on current tree' is proven for tests 2-4, yet steps 2,3,4 are called parallel-safe. Say: 'Step 4 records tests 2-4 failing by assertion on the unmodified tree before steps 2-3 land.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: No boundary tests for the 120000-byte limit or an empty command.

- Severity: MEDIUM
- References: CHANGE_PLAN s16 test (5) uses only a 200000-byte prompt; AC-1 lists empty as argv but test (1) does not enumerate it.
- Failure: No boundary tests for the 120000-byte limit or an empty command. Say: 'A 120000-byte argv prompt is allowed, 120001 is refused, and an empty command prints argv.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Test 6 does not name the forbidden patterns, so a reworded case would pass.

- Severity: MEDIUM
- References: CHANGE_PLAN s16 test (6); CHANGE_SPEC AC-2.
- Failure: Test 6 does not name the forbidden patterns, so a reworded case would pass. Say: 'The grep test asserts change-workflow.sh has no case over native_stage.py or self_hosted.py basenames and contains reviewer_prompt_kind.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: A python3-first client with a non-allowlisted script is file in stagegate but argv in change-workflow, contradicting I3

- Severity: MEDIUM
- References: CHANGE_PLAN s1 D1 versus CHANGE_SPEC I3; no test in s16 covers the divergence.
- Failure: A python3-first client with a non-allowlisted script is file in stagegate but argv in change-workflow, contradicting I3 and untested. Say: 'python3-first classifies file in stagegate and argv in change-workflow; the test table pins both.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Hosted test 4 does not say whether it fails or skips when the wrapper is not resolved, or if it needs network.

- Severity: LOW
- References: CHANGE_PLAN s16 test (4); s21 lists AC-5 as the first scope cut.
- Failure: Hosted test 4 does not say whether it fails or skips when the wrapper is not resolved, or if it needs network. Say: 'The hosted test runs offline and fails, not skips, if the wrapper is not resolved.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
