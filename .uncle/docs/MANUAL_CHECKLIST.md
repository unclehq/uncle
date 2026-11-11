# Manual checklist

### MC-100
- Exclusive resources: none
- Depends on: none
- Exact action: Using the driver's valid attestation and matching replay environment, set ATTESTATION to its supplied path and interactively run `./uncle verify --attestation "$ATTESTATION"`, then `./uncle verify --attestation "$ATTESTATION" --rerun`. Observe the terminal output and exit status of each invocation.
- Expected result: Ordinary verification succeeds without replaying commands; the explicit rerun announces each command before execution and reports per-command matches. Rerun exits zero only when all recorded statuses and output digests match.
- Actual result: 
- Status: NOT RUN

### MC-101
- Exclusive resources: none
- Depends on: none
- Exact action: Using the driver's valid attestation with recorded TZ=UTC, set ATTESTATION to its supplied path and interactively run `TZ=Pacific/Honolulu ./uncle verify --attestation "$ATTESTATION" --rerun`. Observe the diagnostic and exit status.
- Expected result: Rerun reports an environment mismatch identifying TZ and exits nonzero before executing any recorded command. It does not claim a full match.
- Actual result: 
- Status: NOT RUN

### MC-400
- Exclusive resources: none
- Depends on: none
- Exact action: Using the driver's valid current-file attestation, invoke `./uncle verify --attestation "$ATTESTATION_PATH"` without requesting rerun. Observe the terminal interaction through completion.
- Expected result: Ordinary verification succeeds with exit status 0 and retains its existing verification reporting. No recorded commands are replayed or presented as having passed a rerun.
- Actual result: 
- Status: NOT RUN

### MC-401
- Exclusive resources: none
- Depends on: none
- Exact action: Using a driver-provided valid legacy attestation without a command record, invoke `./uncle verify --attestation "$LEGACY_ATTESTATION_PATH"`, then invoke the same CLI with `--rerun`. Observe both results.
- Expected result: Ordinary verification succeeds with exit status 0. The explicit rerun reports unavailable because no command record exists and exits nonzero, while clearly preserving the successful base-verification result.
- Actual result: 
- Status: NOT RUN
