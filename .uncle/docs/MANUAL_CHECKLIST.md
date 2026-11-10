# Manual checklist

### MC-100
- Exclusive resources: none
- Depends on: none
- Exact action: Open skills/uncle-build/SKILL.md for human reading and check the new rule 6 wording against the rules 1-5 that precede it.
- Expected result: Rule 6 follows rule 5 as one or two lines and is conditional: if Daytona shows a warning page, continue past it. It applies only to the Preview link from the build output, names no button in quotes, and does not advise continuing past warnings for any other URL.
- Evidence to capture: Quote rule 6 and the line numbers of rules 1-6.
- Actual result: 
- Status: NOT RUN

### MC-104
- Exclusive resources: none
- Depends on: none
- Exact action: Run `bash scripts/run-python-tests.sh` for the default tier and review the summary for failures or warnings.
- Expected result: All previously passing suites still pass, with no new failures.
- Evidence to capture: Summary output and exit status.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `UNCLE_PREVIEW_HOST=0.0.0.0 python3 scripts/lib/host_preview.py serve <scratch project dir>` for a trivial local app, then open `<scratch project dir>/.uncle/preview.json` and the serve stdout (which prints UNCLE_PREVIEW_PORT=<n>) and look at every place 0.0.0.0 appears.
- Expected result: The `host` field is `0.0.0.0`, status is running, the `url` host is exactly 127.0.0.1, and 0.0.0.0 appears nowhere else in the record or output.
- Evidence to capture: Contents of preview.json and serve stdout showing the host and url values.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With the same wildcard-host server running, fetch http://<first non-loopback, non-link-local IPv4 of this machine>:<port>/ and http://127.0.0.1:<port>/, then stop the server.
- Expected result: If such an address exists, both return HTTP 200 with identical bodies within 5 seconds; if none exists, record it as SKIP, not as passed. The server process is gone after stopping.
- Evidence to capture: Status codes, body comparison, chosen address (or SKIP note), and a check that no server process remains.
- Actual result: 
- Status: NOT RUN

### MC-302
- Exclusive resources: dir:.uncle/preview.json
- Depends on: MC-301
- Exact action: While the wildcard-host app from MC-301 runs, find the first non-loopback, non-link-local IPv4 address of a local interface and GET http://<address>:<port>/ with a 5s timeout; then stop the server.
- Expected result: If such an address exists, the GET returns HTTP 200 with the same body as loopback; if none exists, record SKIP (not PASS). The server process is gone afterward.
- Evidence to capture: Chosen address, HTTP status, body comparison result or SKIP note, and process list after shutdown.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Read rule 6 and judge its wording: it must be conditional (if Daytona shows a warning page, continue past it), limited to the Preview link from the build output, and quote no button name.
- Expected result: Rule 6 does not tell the person to bypass warnings for any other URL, names no button label, and does not promise a tab will open.
- Evidence to capture: The rule 6 text and a note on each of the three wording criteria.
- Actual result: 
- Status: NOT RUN
