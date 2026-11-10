# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| baseline: unattended-test.sh and early-branch-test.py on clean HEAD (throwaway worktree) | FAIL | Pre-existing failures reproduced: unattended stagegate-help/change-workflow-help FAIL; early-branch 4 failures + 1 error; gates group 5 FAIL. | AC-1, AC-2, AC-4, AC-8 |
| bash scripts/tests/unattended-test.sh | PASS | exit 0; 76 checks passed | AC-1, AC-2 |
| python3 -B scripts/tests/early-branch-test.py | PASS | Ran 12 tests, OK | AC-4 |
| python3 -B scripts/tests/attestation-statement-test.py (host .gitignore dirty, then restored to HEAD, then original restored) | PASS | 13 tests OK in both runs; .gitignore sha256 identical after restore | AC-5 |
| python3 -B scripts/tests/supervisor-test.py | PASS | OK; signing audit passes | AC-6 |
| python3 -B scripts/tests/build-attestation-test.py; bash scripts/tests/tree-attested-final-audit-test.sh; python3 -B scripts/tests/handoff-export-test.py | PASS | 4 tests OK; all ok lines; 2 tests OK | AC-6 |
| python3 -B scripts/tests/home-actions-test.py | PASS | Ran 39 tests, OK | AC-7 |
| UNCLE_TEST_ALLOW_NESTED=1 bash scripts/tests/worktree-run-test.sh (UNCLE_*/STAGEGATE_*/WORKFLOW_* unset) | PASS | 402 checks passed (before fix: 226 of 402 failed, exit 127) | AC-7 |
| bash scripts/tests/gates-test.sh (full, env scrubbed, nested allowed) | FAIL | gates-verification-integrity, -2, -3, -4 PASS. Remaining red: gates-repair (group 5) and gates-application-review (fixed afterwards, see next row). | AC-7, AC-8 |
| bash scripts/tests/gates-test.sh --group 4 (env scrubbed) | PASS | gates group 4: 26 checks, 0 failures | AC-8 |
| bash scripts/tests/gates-test.sh --group 5 (env scrubbed) | FAIL | sg-test-failure-repairs-and-regates: expected state 'WAIT_IMPLEMENT_APPROVAL', got 'COMPLETE' (+6 related); same 7 failures on clean HEAD with WORKFLOW_TESTS=0 | AC-8 |
| UNCLE_TEST_ALLOW_NESTED=1 bash scripts/tests/run-policy-test.sh | PASS | 104 checks, 0 failed | AC-3 |
| bash scripts/tests/verification-integrity-test.sh | PASS | 51 checks passed | AC-7 |
| bash scripts/run-all-tests.sh | DRIVER PENDING | Driver owns the full regression run; not run here. | AC-8 |
| formatter / type checker / lint / frontend build / migration / rollback / performance / security checks | N/A | No such tooling applies to these shell/python script and fixture changes. | None stated |

## Coverage gaps

- gates-repair group 5 (sg-test-failure-repairs-and-regates) still red; reproduces on clean HEAD; not in the issue's failing list.
- No new automated test for side-effect freedom of --help/-h/--version or mixed-argument cases (--version --unattended, build --help); only existing unattended-test.sh checks cover the early exit.
- No 'missing prerequisite: <tool>' check: triage found no missing tool behind exit 127.
- gates-compaction-2, gates-application-review-2, gates-document-budgets failed in an earlier gates-test.sh run and were not re-run individually afterwards.
- Several suites were run with UNCLE_*/STAGEGATE_*/WORKFLOW_* unset and UNCLE_TEST_ALLOW_NESTED=1 because this session runs inside a live uncle build.

## Next action

Driver runs bash scripts/run-all-tests.sh; if gates-repair is still red, triage sg-test-failure-repairs-and-regates (post-repair flow ends at TEST_REVIEW with 'Approved implementation inputs changed' and the test expects WAIT_IMPLEMENT_APPROVAL) in a repair pass.
