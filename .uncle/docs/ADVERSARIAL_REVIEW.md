## AR-001: AC-4 requires the comment to 'accurately describe the current default', but the test only checks that one phrase is abse

- Severity: MEDIUM
- References: CHANGE_SPEC AC-4 verification; CHANGE_PLAN D-2 describes comment content that no test asserts.
- Failure: AC-4 requires the comment to 'accurately describe the current default', but the test only checks that one phrase is absent. Settle it: 'test_comment asserts the comment above DEFAULT_MODEL_FOR_RUNNER contains claude-sonnet-5-5 and not the old tier-alias phrase'.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The plan does not say how the picker treats a stored model id that is not in the new 12-entry catalog (e.g.

- Severity: MEDIUM
- References: CHANGE_SPEC section 7 says stored values are not migrated or rejected, with no display rule; AC-1 requires exactly 12 entries.
- Failure: The plan does not say how the picker treats a stored model id that is not in the new 12-entry catalog (e.g. old claude-sonnet-5). Settle it: 'A stored id absent from the catalog is kept and displayed verbatim; the picker still lists exactly 12 entries and highlights none.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: SI-4 is traced to AC-5 and the baseline commands, but the spec admits no existing coverage.

- Severity: LOW
- References: CHANGE_SPEC invariant SI-4 'none found' versus CHANGE_PLAN traceability row AC-5 -> SI-4.
- Failure: SI-4 is traced to AC-5 and the baseline commands, but the spec admits no existing coverage. Settle it: 'SI-4 has no automated enforcement; AC-5 only checks that Codex/Kimi lists are unchanged. Add a test or drop SI-4.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: SB-2 expects the default row label 'Claude Sonnet 5.5', but AC-2's test only checks id equality and membership.

- Severity: LOW
- References: CHANGE_SPEC SB-2 versus AC-2 verification.
- Failure: SB-2 expects the default row label 'Claude Sonnet 5.5', but AC-2's test only checks id equality and membership. Settle it: 'test_defaults_agree asserts the catalog entry for the default id has label Claude Sonnet 5.5'.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Invariant SI-4 (Codex ids not in blanked-tier set) is cited as covering AC-5, but the spec admits no existing coverage a

- Severity: MEDIUM
- References: CHANGE_SPEC.json SI-4 'Existing coverage (none found)'; CHANGE_PLAN traceability AC-5 lists only 'Both baseline commands'.
- Failure: Invariant SI-4 (Codex ids not in blanked-tier set) is cited as covering AC-5, but the spec admits no existing coverage and the plan adds no test. Required sentence: 'AC-5 is verified only by the two baseline commands; SI-4 is not enforced by any new test, and Codex/Kimi catalogs and defaults are asserted unchanged by an added test comparing them to their pre-change literals.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Existing tests may hard-code the old Claude catalog (3 entries) or default 'claude-sonnet-5'; the plan doesn't say wheth

- Severity: MEDIUM
- References: CHANGE_PLAN 'Components to modify' lists no existing tests; Regression-test strategy only says compare to baseline, and picker length changes from 3 to 12.
- Failure: Existing tests may hard-code the old Claude catalog (3 entries) or default 'claude-sonnet-5'; the plan doesn't say whether such tests are updated. Required sentence: 'Any existing test asserting the old Claude catalog length or default id is updated to the new values, and each such edit is listed in IMPLEMENTATION_NOTES.md.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Behavior for a stored model id not in the new catalog (e.g.

- Severity: LOW
- References: CHANGE_SPEC §7 says stored values are not migrated or rejected but never describes picker display of them.
- Failure: Behavior for a stored model id not in the new catalog (e.g. old 'claude-sonnet-5') in the picker is unspecified: whether it is preselected, shown as custom, or falls to the first row. Required sentence: 'A stored id absent from the catalog is kept as the effective model and the picker opens with the default row highlighted without rewriting the stored value.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The allowlist is a loose prefix glob, and stored or overridden ids are never validated against the catalog.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3 and section 7: old stored ids and overrides are accepted without catalog validation; the allowlist is unchanged.
- Failure: The allowlist is a loose prefix glob, and stored or overridden ids are never validated against the catalog. The plan should say: 'Model ids are passed to the CLI as a single quoted argument, never interpolated into a shell string; the allowlist is a prefix filter, not an authorization control.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The AC-3 test runs a pattern extracted from reviewer-claude.sh through bash `case`, but the plan does not say how the pa

- Severity: LOW
- References: CHANGE_PLAN section 16: 'bash `case` run for allowlist with each id'; R-3 extracts the pattern from the script.
- Failure: The AC-3 test runs a pattern extracted from reviewer-claude.sh through bash `case`, but the plan does not say how the pattern and ids are passed in. Shell-string interpolation would be an injection risk. The plan should say: 'The test passes ids and pattern as positional arguments, never via string interpolation.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: AC-3 allowlist test is ambiguous: fnmatch semantics differ from bash case, and the plan does not say how the pattern is

- Severity: HIGH
- References: CHANGE_SPEC AC-3 verification: 'matches each id (fnmatch), also running the script's pattern via bash case'; CHANGE_PLAN R-3 cites lines 89-96 only.
- Failure: AC-3 allowlist test is ambiguous: fnmatch semantics differ from bash case, and the plan does not say how the pattern is extracted or what happens if the script's pattern cannot be found. Plan should say: 'The test fails (not skips) if the case pattern cannot be extracted from reviewer-claude.sh, and bash case is the sole authority; fnmatch is only a cross-check.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: AC-1 requires exact ordered (label,id) pairs but the plan does not say whether the test compares the flattened catalog a

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 'flattened catalog'; CHANGE_PLAN D-1 'keep one group named Claude'.
- Failure: AC-1 requires exact ordered (label,id) pairs but the plan does not say whether the test compares the flattened catalog across groups or per-group structure, nor whether duplicate ids or extra groups count. Plan should say: 'test_catalog_exact asserts the Claude catalog has exactly one group named Claude and its entries equal the 12 pairs in order, with no duplicate ids.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: AC-4 comment test is underspecified: it only forbids the string "opus" tier alias wording, while the positive requiremen

- Severity: MEDIUM
- References: CHANGE_SPEC AC-4 verification vs CHANGE_PLAN D-2; Scope cuts list the comment assertion as first cut.
- Failure: AC-4 comment test is underspecified: it only forbids the string "opus" tier alias wording, while the positive requirement ('describes the actual default') is untestable. Plan should say: 'test_comment asserts the comment block above DEFAULT_MODEL_FOR_RUNNER contains the literal claude-sonnet-5-5 and not the phrase "opus" is the tier alias.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: SI-4 is classified EXISTING with 'no coverage found', and AC-5/SB-5 claim Codex/Kimi catalogs unchanged, yet no test ass

- Severity: MEDIUM
- References: CHANGE_SPEC SI-4 'Existing coverage (none found)'; CHANGE_PLAN traceability AC-5 lists only baseline commands.
- Failure: SI-4 is classified EXISTING with 'no coverage found', and AC-5/SB-5 claim Codex/Kimi catalogs unchanged, yet no test asserts that. Plan should say: 'the new test also snapshots the Codex and Kimi catalogs and defaults and asserts they equal current values, or SI-4/SB-5 are marked verified-by-diff-inspection only.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Default-agreement test extracts DEFAULT_MODEL from shell scripts by regex, but the plan does not state the expected form

- Severity: LOW
- References: CHANGE_PLAN section 16 'regex on the two scripts'; edits at stagegate.sh:282 and reviewer-claude.sh:37.
- Failure: Default-agreement test extracts DEFAULT_MODEL from shell scripts by regex, but the plan does not state the expected form (e.g. ${VAR:-default}) or failure behavior if the line is not matched. Plan should say: 'the test fails if exactly one DEFAULT_MODEL assignment is not found in each script, and a pre-set env override must not affect parsing.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
