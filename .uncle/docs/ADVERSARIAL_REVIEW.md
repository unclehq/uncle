## AR-001: The scope-cut policy permits dropping tests that AC-2 explicitly requires, allowing completion without required verifica

- Severity: MEDIUM
- References: CHANGE_PLAN.json §21 allows cutting negative cases beyond missing grant/require_approval. CHANGE_SPEC.json AC-2 requires each listed case to assert nonzero exit and reason text, including wrong publisher/method/path, invalid JSON, and missing file.
- Failure: The scope-cut policy permits dropping tests that AC-2 explicitly requires, allowing completion without required verification. Replace it with: “All AC-2 cases remain mandatory; time pressure may defer completion but must not remove their verification.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The preservation check does not specify evidence covering pre-existing changes and untracked files.

- Severity: MEDIUM
- References: CHANGE_PLAN.json traceability AC-4 uses a “git diff check,” and implementation step 3 merely says to confirm no edits outside the table. The binding user instructions require file snapshots including untracked files; Git diff alone cannot establish preservation relative to the starting workspace.
- Failure: The preservation check does not specify evidence covering pre-existing changes and untracked files. Add: “Snapshot protected inputs before changes and protected test paths immediately before checks, using hashes and path inventories including untracked files; compare afterward without refreshing either snapshot.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Malformed JSON has no unambiguous exit code: it can mean invalid grant input or unreadable input.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §8 assigns exit 1 to “grant missing/invalid” and exit 2 to “usage/unreadable,” without assigning JSON parse failures. CHANGE_SPEC.json AC-2 and §8 require only a nonzero result, leaving implementation and tests free to choose different classifications.
- Failure: Malformed JSON has no unambiguous exit code: it can mean invalid grant input or unreadable input. Add: “Malformed JSON exits 2 with a sanitized one-line stderr reason; syntactically valid JSON without a matching grant exits 1.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The regression checks do not define immutable file evidence, so Git diff can miss changes to untracked protected inputs.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §17 specifies pre/post suite comparison, §Implementation sequence step 3 says to confirm no edits outside the table, and CHANGE_SPEC.json AC-4 uses Git diff as preservation evidence. These omit the required snapshot procedure and leave implementation and review free to use different preservation checks; adopt the proposed sentence to make regression evidence reproducible.
- Failure: The regression checks do not define immutable file evidence, so Git diff can miss changes to untracked protected inputs. Add: "Snapshot protected inputs before implementation and protected test paths immediately before checks, using hashes and inventories including untracked files; compare afterward without refreshing either snapshot."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Duplicate JSON keys have no defined handling, so conflicting approval values could pass the checker while another consum

- Severity: MEDIUM
- References: CHANGE_PLAN.json §8 and R-1 specify JSON input and recursive matching but no duplicate-key policy; CHANGE_SPEC.json I-5 requires exact matching. An object containing both require_approval:true and require_approval:false can be accepted or rejected depending on parser precedence, undermining the pre-publish security check.
- Failure: Duplicate JSON keys have no defined handling, so conflicting approval values could pass the checker while another consumer interprets them differently. Add: “Reject duplicate keys in every JSON object with a nonzero exit and a fixed diagnostic that contains no input values.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The planned cases do not distinguish JSON false from Python-equal values such as 0, allowing a checker that violates exa

- Severity: MEDIUM
- References: CHANGE_SPEC.json I-5 requires every field to match exactly; CHANGE_PLAN.json §16 tests require_approval true and absent but no other types. These cases are necessary to detect an implementation using equality with False rather than a boolean identity check.
- Failure: The planned cases do not distinguish JSON false from Python-equal values such as 0, allowing a checker that violates exact matching to pass. Add: “Tests must reject require_approval values 0, null, "false", arrays, and objects; only JSON boolean false qualifies.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The scope-cut rule permits dropping tests explicitly required by AC-2, so completion has conflicting test requirements.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §21 permits cutting negative cases beyond missing grant/require_approval, while CHANGE_SPEC.json AC-2 requires verification of wrong publisher/method/path, invalid JSON, and missing file, with each case asserting nonzero status and reason text. Following the cut rule would remove required defect witnesses.
- Failure: The scope-cut rule permits dropping tests explicitly required by AC-2, so completion has conflicting test requirements. Replace it with: “All AC-1 and AC-2 cases are mandatory and cannot be cut under time pressure.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Invalid JSON has no unambiguous exit-code classification, and nonzero-only assertions cannot enforce the CLI contract.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §8 assigns 1 to missing/invalid grants and 2 to usage/unreadable input without classifying malformed JSON; §12 requires one-line stderr reasons. CHANGE_SPEC.json SB-1 requires OK output, but AC-2 specifies only nonzero status and reason text, leaving incompatible CLI implementations able to satisfy the planned checks.
- Failure: Invalid JSON has no unambiguous exit-code classification, and nonzero-only assertions cannot enforce the CLI contract. Add: “Malformed JSON exits 2; parsed JSON without a qualifying grant exits 1; tests assert exact exit codes, OK on successful stdout, and one-line failure reasons on stderr.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
