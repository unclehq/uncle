## AR-001: Moving row cells out of fields/new leaves their normalization and conflict behavior undefined, risking lost row data.

- Severity: HIGH
- References: CHANGE_PLAN.json D-1 moves cells to a top-level array, while D-3 specifies only pair-to-dict normalization. CHANGE_SPEC.json AC-2 requires equivalent typed operations including rows, and AC-3 preserves dict-form behavior; neither artifact defines how relocated cells reach that contract.
- Failure: Moving row cells out of fields/new leaves their normalization and conflict behavior undefined, risking lost row data. Add: "typed_op maps top-level cells into the operation's fields or new dictionary; conflicting nested and top-level cells are rejected, and existing nested cells remain supported."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The repair requirement covers schema-invalid replies, but the planned guard excludes valid JSON arrays, scalars, and nul

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-5 and B-5 require one targeted repair for relaxed, schema-invalid bounded replies. CHANGE_PLAN.json D-5 retains final.startswith('{') for both exception guards, excluding non-object JSON that fails the artifact schema.
- Failure: The repair requirement covers schema-invalid replies, but the planned guard excludes valid JSON arrays, scalars, and null. Add: "A relaxed bounded reply that parses as JSON but violates the artifact schema receives one repair regardless of its first character; malformed JSON receives repair only when it begins with '{'."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Streaming header handling is optional in the plan although relaxed-response reporting is unconditional in the requiremen

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-4 requires a relaxed mode whenever a Converse/chat response carries the non-empty header. CHANGE_PLAN.json D-6 permits documenting unavailable streaming headers, and Scope cuts permits dropping streaming header capture, without explicitly requiring affected calls to use the covered transport.
- Failure: Streaming header handling is optional in the plan although relaxed-response reporting is unconditional in the requirements. Add: "Every updated-plan completion path must propagate the relaxed header; when streaming cannot expose it, route those completions through the non-streaming transport."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The specification treats every non-empty header as relaxed but also treats malformed headers as enforced, leaving arbitr

- Severity: MEDIUM
- References: CHANGE_SPEC.json section 8 says "Header absent/malformed: treat as enforced," while section 15 and AC-4 say any non-empty x-seren-schema-relaxed value signals relaxed enforcement. CHANGE_PLAN.json section 12 additionally treats blank headers as enforced without defining blank or malformed.
- Failure: The specification treats every non-empty header as relaxed but also treats malformed headers as enforced, leaving arbitrary values ambiguous. Add: "Trim header whitespace; any remaining non-empty value means relaxed, regardless of its contents, and an absent or whitespace-only value leaves the mode unchanged."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Moving row cells to the top level leaves their normalization and precedence unspecified, risking dropped row content.

- Severity: HIGH
- References: CHANGE_PLAN D-1 moves cells out of fields/new, but D-3 specifies only pair-array-to-dict conversion; AC-2 requires equivalent row operations and AC-3 preserves dict behavior. scripts/lib/worker_schemas.py:197-200 currently allows cells inside both fields and new, so relocation needs an explicit consumer mapping and conflicting-input test.
- Failure: Moving row cells to the top level leaves their normalization and precedence unspecified, risking dropped row content. Add: "typed_op maps top-level cells into the operation's row payload; existing nested cells remain supported and take precedence when both forms occur."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The header holder can be read as enabling repair when only x-seren-schema-check is present, changing enforced bounded-wr

- Severity: MEDIUM
- References: CHANGE_PLAN D-4 stores both headers and says "if set" the completion returns a relaxed mode, without identifying which value controls it. CHANGE_SPEC AC-4 requires the mode to remain unchanged without the relaxed header, and AC-6 forbids repair for non-relaxed bounded writers; add a check-header-only regression case.
- Failure: The header holder can be read as enabling repair when only x-seren-schema-check is present, changing enforced bounded-writer behavior. Add: "Only a nonblank x-seren-schema-relaxed value marks a response relaxed; x-seren-schema-check alone never changes the mode or repair eligibility."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Pair arrays leave duplicate-entry counts and string lengths unbounded, allowing oversized model packets to consume valid

- Severity: MEDIUM
- References: CHANGE_PLAN D-1/D-2 specify arrays of {name,value} without maxItems or value-length limits; D-3 accepts duplicate names with last-wins semantics. The supplied worker_schemas.py:181-182,197-200 shows that existing field objects have a finite key set and bounded strings; explicitly retaining equivalent bounds prevents the representation change from removing those protections.
- Failure: Pair arrays leave duplicate-entry counts and string lengths unbounded, allowing oversized model packets to consume validation and normalization resources. Add: “Bound each pair array by its allowed field-name count and preserve the previous per-field string-length limits.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: AC-5 requires repair for schema-invalid relaxed replies, but D-5 excludes replies not beginning with `{`, leaving contra

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-5 and B-5 require targeted repair for relaxed schema-invalid replies; CHANGE_PLAN.json D-5 retains the `final.startswith('{')` condition. A valid JSON array failing the artifact schema therefore has two incompatible expected outcomes; align acceptance criteria and add that negative case.
- Failure: AC-5 requires repair for schema-invalid relaxed replies, but D-5 excludes replies not beginning with `{`, leaving contradictory test expectations. Add: “Repair relaxed bounded replies once only when trimmed output begins with `{`; other invalid output raises without repair.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Row equivalence tests lack a defined mapping from top-level `cells` to the existing nested dict representation.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-1 moves cells to a top-level array, while D-3 specifies only fields/new pair-to-dict normalization; CHANGE_SPEC.json AC-2 requires equivalent typed ops including rows. Without a destination and collision rule, independently written row tests and normalization code can disagree.
- Failure: Row equivalence tests lack a defined mapping from top-level `cells` to the existing nested dict representation. Add: “Before typed-op conversion, move top-level cells into new for insert_row and fields for set_fields; reject simultaneous top-level and nested cells.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Malformed non-empty relaxed headers have contradictory expected results, preventing a definitive header test oracle.

- Severity: MEDIUM
- References: CHANGE_SPEC.json section 8 treats malformed headers as enforced, but section 15 and AC-4 treat any non-empty relaxed header as unenforced. CHANGE_PLAN.json D-4 also captures x-seren-schema-check without specifying its effect; reconcile these rules and test arbitrary non-empty values and check-only responses.
- Failure: Malformed non-empty relaxed headers have contradictory expected results, preventing a definitive header test oracle. Add: “Any non-empty x-seren-schema-relaxed value marks the response relaxed regardless of its contents; absent or empty values do not, and x-seren-schema-check alone never marks it relaxed.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
