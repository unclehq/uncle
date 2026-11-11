## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| ASSERTIONS | YES | NOT RUN | [assertions] `.uncle/workflow/green-check.md` confirms the revalidate suite was FIXED and revalidate-integration passed. Neither supplied report establishes assertion adequacy, and no usable assertion-level investigation was provided; passing suite results alone cannot establish this row. |
| COVERAGE | YES | FAIL | [coverage] .uncle/workflow/green-check.md confirms the revalidate checks were FIXED and revalidate-integration passed, with full-runner failures classified PREEXISTING. However, .uncle/docs/CHANGE_TEST_REPORT.md limits real-driver integration to PLAN/WAIT_PLAN_APPROVAL and explicitly leaves default-runner resume through a model stage unexercised. The reported coverage therefore does not establish AC-1's every-stage recording or AC-4/AC-9's resumed-stage execution and pre-write protection requirements. |
| INTEGRITY | YES | PASS | Driver green-check recorded 8 passing verification command(s); see .uncle/workflow/green-check.tsv. |
| NEGATIVE | YES | NOT RUN | [oracle] CHANGE_TEST_REPORT.md names defect-injection coverage but reports no representative injected defect causing a critical test to fail. Its earlier fixture failures and green-check.md FIXED results do not establish that negative-control check. |
| ORACLE | YES | NOT RUN | [oracle] CHANGE_TEST_REPORT.md and green-check.md report suite outcomes but provide no audit showing expected values are independently grounded. Passing revalidate-integration and FIXED revalidate results do not establish oracle independence. |
| RESULTS | YES | PASS | Driver green-check recorded 8 passing verification command(s); see .uncle/workflow/green-check.tsv. |
