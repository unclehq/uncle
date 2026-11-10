# Change spec (Issue 233)

Omitted sections: Performance (none), Security beyond below (none), Migration (none), Prototype isolation (not a prototype).

## 1. Change type
Bug fix.

## 2. Problem statement
A host-published hand-off PR lacks `.uncle/attestation.json`/`.sig`, so `uncle verify <pr>` cannot verify it.

## 3. Current behavior
Baseline B-1.

## 4. Desired behavior
Hand-off runs the same attestation step as normal publish before exporting; `handoff.json` `tree` is the attested tree, `changes` include the attestation files, `audited_tree` is added, and the PR body and Statement come from the same sealed state.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | MODIFY | Hand-off, envelopes present | no attestation files in `changes` | `.uncle/attestation.json` listed `add` (or `modify`), content byte-identical to the Statement `attest` wrote; `tree` equals journal attested `commit_tree` | python test |
| SB-2 | MODIFY | Same, signer configured | n/a | `.uncle/attestation.sig` listed | python test |
| SB-3 | MODIFY | Same, no signer | n/a | no `.sig` listed, no stale `.sig` listed | python test |
| SB-4 | ADD | Hand-off | no field | `audited_tree` present = bind-time tree | python test |
| SB-5 | MODIFY | Hand-off, envelopes, `NOT READY` override | handoff written | hand-off fails (`handoff-failed`), message `Attestation blocked`, no `handoff.json` written | python test |
| SB-6 | PRESERVE | Hand-off, run predates envelopes | summary-only hand-off | unchanged; no `audited_tree` requirement | existing + new python test |
| SB-7 | PRESERVE | Tracked `.uncle/allowed_signers` in base | not deleted | not deleted; new untracked one listed `add` | python test |
| SB-8 | ADD | Hand-off applied to base copy, committed, `uncle verify --tree` | fails `no attestation` | reaches integrity checks | python e2e test |
| SB-9 | MODIFY | PR body | summary from bind seal | summary rendered from the Statement (same sealed state) | python test |
| SB-10 | PRESERVE | Normal publish | attest at consent | unchanged | existing suites |
| SB-11 | MODIFY | Docs | says verify not covered | GITHUB_INTEGRATION.md says attestation included; drop verify from not-covered | review |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | EXISTING | Applying `changes` to `base_commit` gives exactly `tree` | handoff.json | handoff_export.changes | existing + new test |
| SI-2 | STRENGTHENED | `tree` equals the journal's attested `commit_tree` when envelopes exist | hand-off | handoff_export.main | new test |
| SI-3 | EXISTING | Blocking policy refuses before any hand-off file is written | hand-off | attest() | new test |
| SI-4 | NEW | Hand-off Statement and PR-body summary derive from one sealed state | hand-off | sealed_attestation | new test |
| SI-5 | NEW | Re-running hand-off does not overwrite `audited_tree` with an attested tree | journal | new driver action | new test |
| SI-6 | EXISTING | Hand-off performs no push/remote/gh call | hand-off | n/a | existing |
No RELAXED or REMOVED invariants.

## 7. Compatibility
`handoff.json` gains one field (`audited_tree`); other keys unchanged. Summary-only journals unchanged.

## 8. Failure behavior
Attestation refusal: stderr/stdout `PR pending: Attestation blocked: <reason>`, `CHANGE_PR_EXTRAS_REASON=handoff-failed`, return 1, no `handoff.json`.

## 10. Security
No secrets in handoff.json beyond what attest already writes (filter_strings applies). Signing uses existing select_signer; no new key handling.

## 12. Rollback
Revert the commit; hand-off reverts to attestation-less behavior. Working-tree `.uncle/attestation.*` files written by a run are harmless.

## 14. Non-goals
New-project (stagegate.sh) hand-off; changing uncle-verify; changing normal publish; hand-off mode for runs without journal.

## 15. Assumptions
A-1: publication approval entry for hand-off may use a distinct non-human `approved_by` string; implementer confirms envelope/verify accept it (plan step 1).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With envelopes, hand-off `changes` lists `.uncle/attestation.json` with content byte-identical to the file `attest(j)` wrote; applying `changes` to `base_commit` yields `tree`, and `tree` equals the journal's attested `commit_tree`. | New python test in scripts/tests/handoff-export-test.py |
| AC-2 | With a signer, `.uncle/attestation.sig` is listed; without one it is not listed and no stale `.sig` appears. | New python tests (signed/unsigned) |
| AC-3 | `handoff.json` includes `audited_tree` equal to the bind-time tree; rerunning the hand-off keeps it unchanged. | New python test |
| AC-4 | A tracked `.uncle/allowed_signers` in the base is not deleted by the hand-off; a new untracked one is listed `add`. | New python test |
| AC-5 | End to end: hand-off applied to a copy of the base in a scratch repo and committed lets `uncle verify --tree <commit>` reach integrity checks rather than 'no attestation'. | New python test running scripts/uncle-verify.py |
| AC-6 | An overridden NOT READY run with envelopes fails the hand-off with the attestation-blocked message, exits non-zero, and writes no handoff.json. | New python test via the driver action |
| AC-7 | A run without envelopes still produces a summary-only hand-off, as before. | Existing handoff-export tests unchanged and passing |
| AC-8 | PR body attestation block is rendered from the same sealed state as the committed Statement. | New python test comparing body block to Statement fields |
| AC-9 | GITHUB_INTEGRATION.md states the hand-off includes the attestation files and no longer lists `uncle verify` against the host-opened PR as not covered. | Grep review of GITHUB_INTEGRATION.md hand-off section |
| AC-10 | Shell and Python default suites show no new regressions versus baseline. | bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh |

