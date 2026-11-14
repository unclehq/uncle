# Defects

## Observed: interpretation_counts returns (1, 1) instead of (2, 1) for one-space bullets (decision D-2/D-3 mismatch); not yet logged in DEFECTS.md

- **Status:** FAIL
- **Evidence:** Input JSON: {"sections": {"required_functionality": "- First\n - Second\n  - Nested\n    continuation", "definition_of_done": "| Criterion |\n| --- |\n| Result appears |"}}. Returned tuple: (1, 1).
- **Expected result:** Returned tuple is (2, 1): zero-space and one-space top-level bullets count; two-space nested bullet and continuation do not.
- **Actual result:** Returned (1, 1). The required_functionality count is 1, not 2, so the one-space top-level bullet ' - Second' was not counted.
