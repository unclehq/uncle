# Manual checklist

### MC-100
- Exclusive resources: none
- Depends on: none
- Exact action: Request a real hosted build through the hosted chat and, after completion, open the preview link relayed in the response. If hosted access is unavailable, record BLOCKED-HUMAN.
- Expected result: Build output contains `Preview: <url> (works until HH:MM UTC)`, the chat relays the same HTTP(S) link, and opening it displays the built application.
- Actual result: 
- Status: NOT RUN

### MC-102
- Exclusive resources: none
- Depends on: none
- Exact action: Using an isolated hosted test environment with operator-controlled signed-link responses, request one build receiving HTTP 400 and another receiving HTTP 403 from the signed-link service. If controlled live failure responses are unavailable, record BLOCKED-HUMAN.
- Expected result: Each build reports the link-request failure with a reason and emits no `Preview:` line or fabricated preview link.
- Actual result: 
- Status: NOT RUN

### MC-300
- Exclusive resources: none
- Depends on: none
- Exact action: For a dedicated real hosted build that emits a Preview link, let the build finish and observe its sandbox in the hosting service through the advertised link lifetime. Reopen the link shortly before the advertised UTC end time and confirm the application still responds.
- Expected result: The sandbox remains running and is neither stopped nor deleted before the advertised end time; the preview remains usable after build completion. Without hosted-service access or a real Preview link, record BLOCKED-HUMAN rather than PASS.
- Actual result: 
- Status: NOT RUN
