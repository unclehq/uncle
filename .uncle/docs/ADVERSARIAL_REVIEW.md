## AR-001: The plan sets gate_publication to HANDOFF after attest() has built the Statement, and changes consent_entry separately,

- Severity: HIGH
- References: CHANGE_PLAN D-1/D-3; handoff_export.py:97 overwrites sealed['gate_publication'] unconditionally.
- Failure: The plan sets gate_publication to HANDOFF after attest() has built the Statement, and changes consent_entry separately, so 'same sealed state' (SB-9/SI-4) is ambiguous. Decision: the Statement approvals entry and sealed gate_publication must both read 'handoff (published by the host)', and a test asserts it.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The plan does not say whether the hand-off body gets the override/waiver banners the normal path adds.

- Severity: HIGH
- References: handoff_export.py:100-106 vs change-pr.sh:1741-1752.
- Failure: The plan does not say whether the hand-off body gets the override/waiver banners the normal path adds. Decision: state which banners the hand-off pr_body must carry, since AC-8 only compares the attestation block.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: When release_skipped matches the blocking reason, attest() publishes anyway, yet SB-5/AC-6 say a NOT READY override fail

- Severity: MEDIUM
- References: change-pr.sh:646-651 vs SB-5.
- Failure: When release_skipped matches the blocking reason, attest() publishes anyway, yet SB-5/AC-6 say a NOT READY override fails the hand-off. Decision: say whether that case produces a hand-off with a failed-release Statement or fails.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: attest() writes attestation files before the journal is saved, so a failure after that leaves stale .uncle/attestation.*

- Severity: MEDIUM
- References: change-pr.sh:677-681; CHANGE_PLAN D-1/D-2 and section 12.
- Failure: attest() writes attestation files before the journal is saved, so a failure after that leaves stale .uncle/attestation.*. Decision: the action saves the journal only on success, removes files it wrote on failure, and any non-AttestationError exits 1 with handoff-failed.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: A rerun re-attests, so the Statement and signature may differ from the first run, but SI-5/AC-3 cover only audited_tree.

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 'idempotent rerun'; AC-3.
- Failure: A rerun re-attests, so the Statement and signature may differ from the first run, but SI-5/AC-3 cover only audited_tree. Decision: state that reruns may change Statement run fields and signature, and tests assert only audited_tree and tree stability.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: A-1's fallback 'nearest accepted shape' is undefined, so code and tests could choose differently.

- Severity: LOW
- References: CHANGE_PLAN D-3 and R-A; CHANGE_SPEC A-1.
- Failure: A-1's fallback 'nearest accepted shape' is undefined, so code and tests could choose differently. Decision: if free-form approved_by is rejected, use approved_by 'operator' with delegated_by 'handoff'.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The plan changes the shared consent_entry for hand-off mode but never says the non-handoff output is unchanged or which

- Severity: HIGH
- References: CHANGE_PLAN D-3 and the change-impact table (Medium: shared consent_entry); SB-10 is verified only by 'existing suites'. change-pr.sh:635 builds approvals via consent_entry.
- Failure: The plan changes the shared consent_entry for hand-off mode but never says the non-handoff output is unchanged or which test proves it. Add: with UNCLE_PUBLISH_MODE unset, consent_entry returns exactly what it returns today, and a test asserts it.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The rerun is idempotent only for hand-off.

- Severity: HIGH
- References: change-pr.sh:680-681 sets audited_tree=commit_tree, then commit_tree=snapshot(attestation=True). D-1 never sets journal phase, so the phase=='prepared' branch at :1772 is undefined for it.
- Failure: The rerun is idempotent only for hand-off. attest() sets audited_tree from commit_tree, and attest-handoff overwrites attestation and gate_publication, but the plan does not say what a normal publish does after a hand-off or the reverse. Add: after attest-handoff the journal is marked handoff-attested and a later normal publish refuses.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Two writers stamp gate_publication on the hand-off attestation.

- Severity: MEDIUM
- References: handoff_export.py:94-97 copies journal['attestation'] and overwrites gate_publication; D-1 sets the same field and D-4 says only 'use journal attestation'.
- Failure: Two writers stamp gate_publication on the hand-off attestation. The plan says neither which one is authoritative nor whether the export keeps re-stamping. Add: the export uses the journal attestation as-is and does not re-stamp the field.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: If the base tracks a stale .uncle/attestation.sig and this run is unsigned, write_attestation_files unlinks it, but the

- Severity: MEDIUM
- References: change-pr.sh:690-693 unlinks the sig. SB-3 says no stale .sig is listed, and SB-7 covers only allowed_signers; changes() emits delete rows at handoff_export.py:73.
- Failure: If the base tracks a stale .uncle/attestation.sig and this run is unsigned, write_attestation_files unlinks it, but the plan never says how changes expresses that. Add: a tracked .sig that is removed is listed as delete.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Failure ordering is unspecified when attest-handoff writes the working-tree files and then save(j) or the exporter fails

- Severity: MEDIUM
- References: D-1 and D-2 order attest, save, then export, and handoff-failed covers only a non-zero attest-handoff exit. Tests cover only the AttestationError case (SB-5).
- Failure: Failure ordering is unspecified when attest-handoff writes the working-tree files and then save(j) or the exporter fails. Add: the journal is saved before the exporter runs, and a failed export leaves a state that rerunning repairs.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The plan uses a free-form approved_by string for the publication gate, which uncle-verify may read as a human approval.

- Severity: HIGH
- References: CHANGE_PLAN D-3/A-1 leave open whether approved_by is accepted. verify and envelope are 'Not to modify', yet R-A allows a fallback to 'the nearest accepted shape', which could look human.
- Failure: The plan uses a free-form approved_by string for the publication gate, which uncle-verify may read as a human approval. Decide: the entry carries an explicit non-human marker that verify reports as 'not human-approved'.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: The plan does not say how an override-published NOT READY run is handled in a hand-off.

- Severity: HIGH
- References: change-pr.sh:646-653 branches on j.get('release_skipped') == reason. D-1 calls attest(j) without addressing that field, and the SB-5 trigger 'NOT READY override' is ambiguous.
- Failure: The plan does not say how an override-published NOT READY run is handled in a hand-off. attest() raises only when j.release_skipped differs from the reason, and hand-off may never set it. Decide: hand-off always refuses on a blocking reason, or records the override as normal publish does.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: handoff.json carries the sealed attestation and a full changes list, but the plan never says how the host detects a tamp

- Severity: MEDIUM
- References: D-4 and SB-1 only require tree to equal commit_tree. CHANGE_SPEC section 10 (Security) is silent on the integrity of the hand-off transport.
- Failure: handoff.json carries the sealed attestation and a full changes list, but the plan never says how the host detects a tampered tree or changes list. Decide: uncle verify --tree on the applied commit is the stated detector, and the host must not trust handoff.json fields alone.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The plan does not cover a stale or hostile .uncle/attestation.* in the working tree, for example a symlink.

- Severity: MEDIUM
- References: change-pr.sh:685-697 uses Path.write_bytes and unlink with no symlink check. Plan section 14 calls leftover files harmless without considering a symlink pointing outside the repo.
- Failure: The plan does not cover a stale or hostile .uncle/attestation.* in the working tree, for example a symlink. Decide: attest-handoff refuses if either path is a symlink, and removes a stale .sig when unsigned.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Rerun after a partial attest-handoff is unspecified.

- Severity: MEDIUM
- References: D-1 orders: set commit_tree, attest(j), then save(j). attest sets audited_tree at change-pr.sh:680 before any save.
- Failure: Rerun after a partial attest-handoff is unspecified. attest() mutates j['audited_tree'] before save(), so a crash between attest and save leaves new files with an old journal. Decide: files are rewritten from audited_tree on every rerun and the journal is saved only after both files are written.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: SB-5/AC-6 say any NOT READY override fails the hand-off, but attest() publishes anyway when release_skipped equals the r

- Severity: HIGH
- References: change-pr.sh:646-653 versus CHANGE_SPEC SB-5.
- Failure: SB-5/AC-6 say any NOT READY override fails the hand-off, but attest() publishes anyway when release_skipped equals the reason. Decision: the hand-off fails only when attest() raises AttestationError; when release_skipped matches, it proceeds and records the failed release envelope.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: D-3's handoff approval entry is unverified (A-1) and no AC or SB row tests the approvals content.

- Severity: HIGH
- References: CHANGE_PLAN D-3 and R-A; AC-5 only checks that verify 'reaches integrity checks'.
- Failure: D-3's handoff approval entry is unverified (A-1) and no AC or SB row tests the approvals content. Decision: a test asserts the Statement approvals hold exactly one publication entry with approved_by 'handoff (published by the host)', and that uncle verify accepts it.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: AC-5 'reaches integrity checks rather than no attestation' is not a pass/fail oracle.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-5 / SB-8 wording; plan M-1 'expect integrity checks'.
- Failure: AC-5 'reaches integrity checks rather than no attestation' is not a pass/fail oracle. Decision: the test asserts uncle-verify exits 0 on the signed fixture, and a stated exit code and finding on the unsigned fixture.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The plan does not say what a rerun does after a failed or partial attest-handoff.

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 versus change-pr.sh:680.
- Failure: The plan does not say what a rerun does after a failed or partial attest-handoff. attest() overwrites audited_tree from commit_tree, so a rerun after a failed save could record the wrong tree. Decision: the test covers success, rerun, and rerun after an induced failure, asserting audited_tree is unchanged and commit_tree is the attested tree each time.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: SB-9/AC-8/SI-4 do not say which fields the body block and the Statement are compared on.

- Severity: MEDIUM
- References: handoff_export.py:94-97; CHANGE_SPEC SB-9.
- Failure: SB-9/AC-8/SI-4 do not say which fields the body block and the Statement are compared on. gate_publication is overridden after sealing, so a literal comparison cannot hold. Decision: compare every field except gate_publication, which must read 'HANDOFF (published by the host)'.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: The plan does not define envelopes_enabled() or the case where the envelopes directory exists but is empty or unreadable

- Severity: LOW
- References: change-pr.sh:621-622; D-1 'if envelopes_enabled()'.
- Failure: The plan does not define envelopes_enabled() or the case where the envelopes directory exists but is empty or unreadable. Decision: add a test row for an empty envelopes directory, expecting the attestation-blocked failure and no handoff.json.
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
