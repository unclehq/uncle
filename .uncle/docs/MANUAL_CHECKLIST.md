# Manual checklist

## Structural counting edge cases

### MC-901
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Import scripts/lib/change_class.py using importlib.util. In a disposable temporary directory, create .uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json with sections.required_functionality equal to "- First\n - Second\n  - Nested\n    continuation" and sections.definition_of_done equal to "| Criterion |\n| --- |\n| Result appears |". Call interpretation_counts with that temporary directory and record the returned tuple. No repository initialization is needed.
- Expected result: The returned tuple is (2, 1): zero-space and one-space top-level bullets count; the two-space nested bullet and continuation do not. This follows CHANGE_PLAN.json decision D-2 and decision D-3.
- Evidence to capture: Exact input JSON and returned tuple.
- Actual result: 
- Status: NOT RUN
