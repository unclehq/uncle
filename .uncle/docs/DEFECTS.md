# Defects

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** The checklist row says to record BLOCKED-HUMAN when hosted access is unavailable. No hosted build, chat relay, or preview link was observed.
- **Expected result:** Build output contains `Preview: <url> (works until HH:MM UTC)`, the chat relays the same HTTP(S) link, and opening it displays the built application.
- **Actual result:** Not performed. A real hosted build and chat session need a person with hosted-service access.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** The checklist row itself says to record BLOCKED-HUMAN when controlled live failure responses are unavailable. No hosted environment or operator was provided to this worker.
- **Expected result:** Each build reports the link-request failure with a reason and emits no `Preview:` line or fabricated preview link.
- **Actual result:** Not performed. The check needs an isolated hosted test environment where an operator controls the signed-link service responses (HTTP 400 and HTTP 403). None was available to this worker.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** The checklist row's own expected result prescribes BLOCKED-HUMAN when hosted-service access or a real Preview link is missing. No hosted-service credentials or Preview link were provided to this worker.
- **Expected result:** The sandbox stays running and is not stopped or deleted before the advertised end time. The preview stays usable after the build finishes. Without hosted-service access or a real Preview link, record BLOCKED-HUMAN rather than PASS.
- **Actual result:** Not performed. This check needs a dedicated real hosted build, observation of its sandbox in the hosting service through the advertised link lifetime, and a reopen shortly before the advertised UTC end time. This worker has no hosted-service access and no real Preview link.
