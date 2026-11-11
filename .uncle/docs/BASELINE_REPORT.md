# Baseline report — Issue 248

Omitted sections: Reproduction result (not a bug; a feature gap)

## 1. Change-request summary
See CHANGE_REQUEST.md (Issue 248): record per-command command/env/output evidence in `green-check.json`, an environment block in the `verification` envelope, the tree that ran, `unavailable` for untrustworthy status, and `uncle verify --rerun`.

## 2. Repository architecture
Bash drivers (`scripts/stagegate.sh`, `scripts/change-workflow.sh`) source `scripts/lib/green-check.sh` and call `green_run`. Python helpers in `scripts/lib/` run commands, build the attestation envelopes and the standalone verifier `scripts/uncle-verify.py` (dispatched by `uncle verify`, `uncle` line 303).

## 3. Relevant code paths
- `scripts/lib/green-check.sh:260-342` `green_run`: serial loop; wraps `bash -o pipefail -c` → `shell_syntax.py --command-file` (line 321) → `run_check.py` (326); appends `<status>\t<cmd>` to the tsv (331).
- `scripts/lib/green-check.sh:278-300`: parallel path delegating to `scripts/lib/parallel_checks.py` (`record` at 209, results.tsv write at 365).
- `scripts/lib/shell_syntax.py:49-60`: the only place `-o pipefail` is applied (execv).
- `scripts/lib/run_check.py:1-66`: timeout (`check_timeout`), output spool copied to stdout.
- `scripts/lib/build_attestation.py:42-84`: `green_result` reads only the tsv; `write_stages` writes the `verification` envelope with evidence tsv + AUTOMATED_TEST_REPORT.md.
- `scripts/lib/envelope.py:343-390`: `write_envelope(..., inputs, evidence, extra)`.
- `scripts/lib/isolated_verify.py:64-139`: `prepare` copies project to a private dir and rewrites the port; used by `scripts/lib/background-verify.sh:175`.
- `scripts/uncle-verify.py:~590-680`: `main` runs checks 1-9 on an attestation; no command rerun.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | green_run command | tsv row `status\tcommand`; log has output | green-check.sh:331 | Yes |
| B-2 | piped command failing | pipefail applied via shell_syntax.py | shell_syntax.py:57 | Yes |
| B-3 | no tsv | verification `unavailable` | build_attestation.py:48 | Yes |
| B-4 | tsv present | summary string `N commands: X pass...` | build_attestation.py:52-56 | Yes |
| B-5 | `uncle verify` | checks signature/hashes, no rerun | uncle-verify.py main | Yes |
| B-6 | timeout | status 124 and log line | run_check.py | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Missing record is `unavailable`, never `pass` | build_attestation.green_result | build-attestation-test.py | High |
| I-2 | Only REGRESSION fails the check | green_result | build-attestation-test.py | Medium |
| I-3 | Attestation bytes canonical and signed | uncle-verify.py check_1/2 | attestation-test.py | High |
| I-4 | Commands run with pipefail | shell_syntax.py | None through wrappers | Low |

## 6. Interface contracts
`green-check.tsv` (`status\tcommand`) is consumed by classification, baseline comparison and attestation: format must not change. Envelope `evidence` entries are digests of listed files; `extra` merges extra keys into the body. `uncle verify [<pr>] [--attestation PATH] [--tree SHA]`.

## 7. Existing automated-test coverage
Shell: green-check, green-check-vacuous, green-defer-mutation, tree-attested-final-audit. Python: build-attestation, attestation, attestation-statement, revalidate-attestation, host-preview. The shell and Python suites use separate temp dirs and share no ports, so they run as one parallel group. `scripts/tests/critical-suites.txt` selects the default tier.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (the documented runners). Not run here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites are known to fail on a clean checkout.

## 10. Existing failures
None established by this stage; see the driver baseline.

## 12. Likely change surface
`green-check.sh`, `run_check.py`, `parallel_checks.py`, `build_attestation.py`, `uncle-verify.py`, `isolated_verify.py`/`background-verify.sh` (tree-ran note), new `scripts/lib/check_record.py`, new tests, `scripts/tests/critical-suites.txt`, `scripts/README.md`.

## 13. Regression-sensitive components
The tsv format and exit semantics, parallel_checks performance, canonical attestation bytes (new evidence changes the digest set), uncle-verify exit codes (0/1/2/3).

## 14. Outside the change
Signing, approval gates, tsv classification, check selection, PR creation flow.

## 15. Unknowns and assumptions
- Assumption: green-check.json goes in the same state dir as the tsv, next to `green-check.tsv`.
- Whether `isolated_verify.py` is used for the main green check is UNRESOLVED from reading: it is only called from background-verify.sh:175; the record must capture whichever applies.

## 16. Initial risk assessment
Medium: touches the central check runner (both serial and parallel paths); a bug could mask failures. Secret leakage via environment capture is the main security risk.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

