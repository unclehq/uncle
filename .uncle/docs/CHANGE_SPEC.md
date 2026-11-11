# Change spec — Issue 248

Omitted sections: Performance (negligible), Migration (additive), Prototype isolation (n/a)

## 1. Change type
Feature (security/verifiability).

## 2. Problem statement
A verification result does not show it came from the named command, environment and tree, and review cannot reproduce it. See CHANGE_REQUEST.md gaps 1-5.

## 3-4. Current / desired behavior
See baseline B-1..B-6. Desired: each result carries a record; the attested tree and environment are stated; untrustworthy status is `unavailable`; `uncle verify --rerun` reproduces and compares.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | PRESERVE | green_run | tsv `status\tcommand` | Unchanged format and statuses | existing green-check tests |
| SB-2 | ADD | green_run, any path | no per-command record | `green-check.json` with command, argv, cwd, exit status, pipefail flag, start, duration, timeout, output sha256 | check-record-test.py |
| SB-3 | ADD | attestation build | none | `verification` envelope carries environment block and digests green-check.json as evidence | check-record-test.py, build-attestation-test.py |
| SB-4 | ADD | commands ran in a copy | not stated | Envelope records ran-in-copy, copy tree hash, rewrites; differing hash stated | check-record-test.py |
| SB-5 | MODIFY | status not tied to own process | could be `pass` | `unavailable` with reason | check-record-test.py |
| SB-6 | ADD | `false \| tail`, `false \| tee f` | untested | Fail through every wrapper | check-record-test.py |
| SB-7 | ADD | `uncle verify --rerun` | none | Checks out attested tree, reruns recorded commands, compares status and output digest, reports mismatch incl. env differences | check-record-test.py |
| SB-8 | MODIFY | final audit | reads transcript | Audit input includes the rerun result | tree-attested-final-audit-test.sh |
| SB-9 | PRESERVE | `uncle verify` without `--rerun` | no rerun | Unchanged output and exit codes | attestation tests |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | STRENGTHENED | A stage is never `pass` when a command's status is untrustworthy | verification envelope | build_attestation.green_result | check-record-test.py |
| SI-2 | NEW | Environment capture uses an allow-list; no non-listed variable is ever read into the record | green-check.json, envelope | check_record.py | test with secret-named var |
| SI-3 | NEW | Record output digest equals sha256 of that command's captured output | green-check.json | check_record.py | test mutating output |
| SI-4 | NEW | Every command runs with pipefail | all wrappers | shell_syntax/run_check/parallel_checks | SB-6 tests |
| SI-5 | EXISTING | tsv format unchanged | consumers | green_run | existing tests |

No invariant is RELAXED or REMOVED.

## 7. Compatibility
Attestations without the new fields still verify; `--rerun` on one reports `unavailable (no record)`, not failure of the base verification.

## 8. Error behavior
Missing record/output/status → `unavailable` with reason. Rerun mismatch → nonzero exit with the differing fields. Rerun cannot check out tree → exit with message.

## 10. Security
Allow-listed environment variables only (PATH excluded value? no: record names of Uncle-set variables and values for an explicit list). Rerun runs recorded commands from a signed record: it only runs after the existing verification checks pass, in a temp checkout, with timeout, and states what it is about to run.

## 12. Rollback
Revert the commit; new files are additive, old attestations remain valid.

## 14. Non-goals
Changing signing, running browsers in the rerun, making `--rerun` default for PRs (the question is answered: opt-in; defer).

## 15. Assumptions
A1: allow-list = Uncle-set variables plus WORKFLOW_CHECK_TIMEOUT_SECONDS, CI, LANG, TZ, NODE_ENV, UNCLE_PREVIEW_HOST/PORT. A2: tool versions come from `--version` of node, npm, python3, bash, git, playwright when present.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | green_run (serial and parallel paths) writes green-check.json with one entry per command containing command, argv, cwd, exit status, pipefail setting, start time, duration, timeout and sha256 of its captured output, and green-check.tsv is unchanged in format. | scripts/tests/check-record-test.py; removing any field fails it; existing green-check tests pass |
| AC-2 | The verification envelope includes an environment block (OS, arch, tool versions, allow-listed variables, WORKFLOW_CHECK_TIMEOUT_SECONDS, jobs) and digests green-check.json as evidence. | check-record-test.py and build-attestation-test.py |
| AC-3 | When commands ran in an isolated copy, the record states it with the copy's tree hash and the list of rewrites; a hash differing from inputs.artifact is stated. | check-record-test.py with an isolated_verify fixture |
| AC-4 | If a command's status, output log or status file is missing or its record is inconsistent, the verification stage is unavailable with a reason, never pass. | check-record-test.py negative cases |
| AC-5 | `false \| tail` and `false \| tee file` fail through shell_syntax.py, run_check.py and the parallel runner. | check-record-test.py |
| AC-6 | No environment variable outside the allow-list appears in green-check.json or the envelope, including variables with credential-like names. | check-record-test.py sets SECRET_TOKEN and asserts absence |
| AC-7 | `uncle verify --rerun` checks out the attested tree, reruns the recorded commands under recorded constraints, compares status and output digest, reports mismatches and environment differences with a nonzero exit, and passes only on full match; without --rerun behavior is unchanged. | check-record-test.py match and mismatch cases; attestation tests unchanged |
| AC-8 | The final-audit stage is given the rerun result as input instead of relying on the transcript. | tree-attested-final-audit-test.sh extended |
| AC-9 | The new suite is in scripts/tests/critical-suites.txt and existing shell and Python suites do not regress. | bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh |

