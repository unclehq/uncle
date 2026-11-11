# Verification report

## Findings

### MC-100

- **Action:** Read the checklist row. Did not request a hosted build. This worker has no access to the hosted chat or hosting service, and the driver supplied no hosted URL.
- **Expected result:** Build output contains `Preview: <url> (works until HH:MM UTC)`, the chat relays the same HTTP(S) link, and opening it displays the built application.
- **Actual result:** Not performed. A real hosted build and chat session need a person with hosted-service access.
- **Defects:** None

### MC-102

- **Action:** Read the checklist row. No action was taken against a hosted environment because none was supplied.
- **Expected result:** Each build reports the link-request failure with a reason and emits no `Preview:` line or fabricated preview link.
- **Actual result:** Not performed. The check needs an isolated hosted test environment where an operator controls the signed-link service responses (HTTP 400 and HTTP 403). None was available to this worker.
- **Defects:** None

### MC-300

- **Action:** Read the MC-300 checklist row. Did not run a hosted build, because that needs access to the real hosting service and a real Preview link, and none was supplied in this environment.
- **Expected result:** The sandbox stays running and is not stopped or deleted before the advertised end time. The preview stays usable after the build finishes. Without hosted-service access or a real Preview link, record BLOCKED-HUMAN rather than PASS.
- **Actual result:** Not performed. This check needs a dedicated real hosted build, observation of its sandbox in the hosting service through the advertised link lifetime, and a reopen shortly before the advertised UTC end time. This worker has no hosted-service access and no real Preview link.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | YES | BLOCKED-HUMAN | The checklist row says to record BLOCKED-HUMAN when hosted access is unavailable. No hosted build, chat relay, or preview link was observed. |
| MC-102 | YES | BLOCKED-HUMAN | The checklist row itself says to record BLOCKED-HUMAN when controlled live failure responses are unavailable. No hosted environment or operator was provided to this worker. |
| MC-300 | YES | BLOCKED-HUMAN | The checklist row's own expected result prescribes BLOCKED-HUMAN when hosted-service access or a real Preview link is missing. No hosted-service credentials or Preview link were provided to this worker. |
