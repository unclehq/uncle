# Test evidence handoff

This is a documentation reconciliation stage, not a repair stage. Do not edit application source, tests, dependencies, configuration, or the approved plan.

Read canonical test-review JSON, canonical updated-plan JSON, driver green-check evidence, and relevant existing tests. Re-run only targeted verification commands when needed. Update `.uncle/docs/AUTOMATED_TEST_REPORT.md` with actual commands, statuses, meaningful output, and requirement/test mappings grounded in evidence.

For planned negative checks, record actual fail-then-pass evidence from a disposable copy, or NOT RUN and why. Do not infer coverage from an exit code. Replace the fallback placeholder; do not claim a check ran unless evidence says it did. Update implementation notes only if it contains the same fallback statement. Write reports, not a summary.
