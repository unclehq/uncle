# Defects

## None. Setup needed: the driver must supply a valid passing attestation with a command record and the matching replay environment. Also confirm that `./uncle verify` resolves to the worktree's scripts/uncle-verify.py, which defines --rerun.

- **Status:** BLOCKED-SETUP
- **Evidence:** Terminal output above. Attestation: .uncle/attestation.json, with a failed check '✗ audit result is fail, not pass; NOT_READY'. ./uncle dispatches to $ROOT/scripts/uncle-verify.py (uncle line 303), but the argparse usage it printed had no --rerun. This suggests $ROOT resolved to a different script copy than the worktree's modified one; I did not confirm that.
- **Expected result:** Ordinary verification succeeds without replaying commands. The explicit rerun announces each command before execution, reports per-command matches, and exits zero only when all recorded statuses and output digests match.
- **Actual result:** Ordinary verify printed NOT VERIFIED because the audit result is fail (NOT_READY). The available attestation is therefore not a valid, passing one. `./uncle verify ... --rerun` failed with 'unrecognized arguments: --rerun', although scripts/uncle-verify.py defines --rerun (line 573). Run directly, the script printed NOT VERIFIED for the same audit failure; no command replay output was seen. The exit codes were not captured because of a piped-status mistake in my commands. I did not establish per-command rerun behavior.

## None. Setup needed: the driver must supply a valid attestation with a recorded command environment (TZ=UTC) as ATTESTATION. The ./uncle wrapper must also resolve to this checkout's verifier, not the installed Homebrew build, which lacks --rerun.

- **Status:** BLOCKED-SETUP
- **Evidence:** Terminal output from both runs. The first printed 'uncle verify: error: unrecognized arguments: --rerun'. The second printed '✗ audit result is fail, not pass; NOT_READY' and 'NOT VERIFIED'. A grep of .uncle/attestation.json for command_record matched 0 times. No ATTESTATION path was supplied by the driver.
- **Expected result:** Rerun reports an environment mismatch identifying TZ and exits nonzero before executing any recorded command. It does not claim a full match.
- **Actual result:** The expected behavior could not be observed. First run: the installed verifier rejected --rerun (exit status not captured). Second run, using this checkout's verifier: the output was 'NOT VERIFIED' because the attestation's audit result is fail, not pass (NOT_READY). It contains no command record and no recorded TZ, and it printed no environment-mismatch diagnostic. The exit status was not captured because of a PIPESTATUS shell quirk. This attestation is not the valid one with a recorded environment that the check requires.

## None. Setup action needed: the driver supplies a passing attestation (audit result pass) via ATTESTATION_PATH, then MC-400 is rerun.

- **Status:** BLOCKED-SETUP
- **Evidence:** Terminal output: '✗ audit result is fail, not pass; NOT_READY' followed by 'NOT VERIFIED'; exit=1. $ATTESTATION_PATH was unset. No application defect is claimed: the precondition (a driver-provided valid current-file attestation) was not met.
- **Expected result:** Ordinary verification succeeds with exit status 0, keeps its existing reporting, and replays no recorded commands.
- **Actual result:** The run printed NOT VERIFIED and exited 1. Reason given: 'audit result is fail, not pass; NOT_READY'. The other checks passed: canonical schema, approved artifacts, and head tree matching the release artifact. No commands were replayed, which is as expected. The exit-0 success path was not exercised, because the available attestation is not a valid passing attestation of the kind the check requires.

## None. Setup action: the driver must supply a valid legacy attestation without a command record via LEGACY_ATTESTATION_PATH. The reviewer should also confirm whether --rerun is meant to be accepted by ./uncle verify.

- **Status:** BLOCKED-SETUP
- **Evidence:** env LEGACY_ATTESTATION_PATH empty; `./uncle verify --attestation .uncle/attestation.json` -> 'NOT VERIFIED ... audit result is fail, not pass; NOT_READY'; with --rerun -> 'uncle verify: error: unrecognized arguments: --rerun'. Exit statuses were not captured because of a pipe in my command. Possible product gap: ./uncle verify may not accept --rerun. Not confirmed as a defect without a valid fixture.
- **Expected result:** Ordinary verification exits 0; --rerun reports unavailable (no command record), exits nonzero, and preserves the successful base-verification result.
- **Actual result:** No legacy attestation without a command record was provided. The repo's attestation is not a valid legacy fixture: base verify printed NOT VERIFIED (audit result is fail, NOT_READY). `--rerun` was rejected by the argument parser as 'unrecognized arguments: --rerun' (usage error). The check's precondition could not be established, so the expected behavior was neither confirmed nor refuted.
