# Implementation notes

### Files changed

- `scripts/lib/change-pr.sh` — attest-handoff driver action; hand-off route runs it before the exporter; consent_entry delegation in handoff mode; handoff-attested phase and re-publish refusal; D-1, D-2, D-3, D-6, D-7, D-8; Hand-off writes and lists the attestation; failure yields handoff-failed with no handoff.json
- `scripts/lib/handoff_export.py` — Emit audited_tree; use journal attestation and banners as sealed; D-4; handoff.json audited_tree stable across reruns
- `scripts/tests/handoff-export-test.py` — Unit and end-to-end tests including uncle verify --tree on the applied copy and body/Statement match; Tests; AC-1..AC-8
- `GITHUB_INTEGRATION.md` — Hand-off section states attestation files are included and verify is covered; D-5; AC-9

### Deviations

- `scripts/lib/change-pr.sh`: Assumption A-1 was false: envelope.py rejects approver_kind/human keys and uncle-verify check_7 ignores delegated_by. consent_entry uses approved_by '' with delegated_by 'handoff' instead of the D-3 marker fields; verify therefore reports 'no human approval' for the publication gate, which the e2e test asserts.

### Unresolved concerns

- gates-repair group 5 (sg-test-failure-repairs-and-regates) is red on clean HEAD too and is outside this change.
- Full suites are left to the driver.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | change-pr.sh attest_handoff; handoff_export.py | python3 -B scripts/tests/handoff-export-test.py: 25 tests OK (test_attestation_is_listed_byte_identical_and_applies_to_the_attested_tree) |
| AC-2 | IMPLEMENTED | attest_handoff with prior-file restore | same run: signed and unsigned/stale-sig tests OK |
| AC-3 | IMPLEMENTED | handoff_export.py audited_tree; attest_handoff rerun determinism | same run: test_rerun_keeps_audited_tree_and_attested_tree OK |
| AC-4 | IMPLEMENTED | exporter tracked-file handling | same run: test_tracked_allowed_signers_is_not_deleted OK |
| AC-5 | IMPLEMENTED | hand-off route plus e2e fixture | same run: verify --tree reaches integrity checks and head tree matches |
| AC-6 | IMPLEMENTED | route returns handoff-failed when attest-handoff fails | same run: empty-envelopes and failure-after-attest tests OK, no handoff.json |
| AC-7 | IMPLEMENTED | attest_handoff returns early without envelopes | same run: pre-existing Handoff tests OK unchanged |
| AC-8 | IMPLEMENTED | handoff_export.py uses sealed attestation and banners | same run: test_pr_body_block_matches_the_committed_statement OK |
| AC-9 | IMPLEMENTED | GITHUB_INTEGRATION.md hand-off paragraph | grep: 'Not yet covered' now lists only planning without a git remote |
| AC-10 | IMPLEMENTED | no change to other suites | bash scripts/tests/unattended-test.sh: 76 checks passed; full suites DRIVER PENDING |
