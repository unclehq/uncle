# Manual checklist

## Relaxed response integration

### MC-902
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a disposable harness with mocked network responses and no live credentials, drive a bounded updated-plan completion through its transport and final-answer validation. Return a schema-invalid object with a nonblank x-seren-schema-relaxed header, then repeat with whitespace-only, absent, and check-only headers. For the relaxed case, exercise both successful repair and repair that remains invalid.
- Expected result: Only the nonblank relaxed header enables exactly one targeted repair. Successful repair returns a valid packet and preserves the relaxed mode in constraint_mode; unsuccessful repair raises the existing validation error without another repair. Blank, absent, and check-only headers leave the bounded writer on its no-repair failure path.
- Evidence to capture: Mock response headers, transport mode, repair invocation counts, returned packets or errors, and constraint_mode for each case.
- Actual result: 
- Status: NOT RUN
