# Manual checklist

## Coverage

### MC-102
- Required for acceptance: YES
- Exclusive resources: release:publish
- Depends on: MC-100
- Exact action: Publish the new release from the release repository and record the publish output (redacting any credentials).
- Expected result: Publish succeeds with no 'must match one publisher operation' refusal. If it is refused, report the error without guessing an operation_id; if there is no host access, BLOCKED-SETUP.
- Evidence to capture: The publish command output and exit status.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-102
- Exact action: Using a recorded pre-existing hire created before the publish, reinstall or update it on the hosted host with the new release, counting approval prompts.
- Expected result: The hire installs with zero approval prompts, including no Daytona-write approval prompt.
- Evidence to capture: The hire id and creation date, the install output, and the prompt count.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-102
- Exact action: Run a hosted build where the host refuses the signed-link request or returns no link, then note the exit status and look for a `Preview:` line.
- Expected result: No `Preview:` line is printed (and no over-limit or partial link), the build exits normally with status 0, and the refusal is reported in the build output.
- Evidence to capture: The exit status and the build output showing the absence of a `Preview:` line.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-204
- Required for acceptance: YES
- Exclusive resources: hosted-hire:existing
- Depends on: MC-201
- Exact action: Record a pre-existing hire (identifier and creation date before the publish), then reinstall or update it on the hosted host after the new release is published, counting approval prompts.
- Expected result: The hire installs with zero approval prompts, including no Daytona-write approval prompt.
- Evidence to capture: Hire identifier and creation date, the prompt count of zero, and a transcript or screenshot of the install.
- Actual result: 
- Status: NOT RUN

### MC-301
- Exclusive resources: release:publish
- Depends on: none
- Exact action: With operator-supplied release repo access, publish the new release containing the signed-preview-url grant, and save the publish output with any token redacted.
- Expected result: Publish succeeds without the "must match one publisher operation" refusal. If no release repo or host access exists, record BLOCKED-SETUP naming the access needed.
- Actual result: 
- Status: NOT RUN

### MC-303
- Exclusive resources: none
- Depends on: MC-301
- Exact action: Record a pre-existing hire (id and creation date earlier than the publish), install or update it to the new release on the host, and count approval prompts.
- Expected result: Zero Daytona-write approval prompts appear and the install succeeds.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-404
- Required for acceptance: YES
- Exclusive resources: account:existing-hire
- Depends on: MC-403
- Exact action: Record the pre-existing hire's name/id and creation date, which must predate the publish. After MC-403, reinstall or update that hire on the host and count approval prompts.
- Expected result: The hire installs with zero Daytona-write approval prompts. This guards existing hires against a compatibility regression.
- Evidence to capture: Hire id and creation date, install output, and the prompt count.
- Actual result: 
- Status: NOT RUN
