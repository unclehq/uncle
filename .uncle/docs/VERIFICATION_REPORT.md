# Verification report

## Findings

### MC-100

- **Action:** Read skills/uncle-build/SKILL.md; rules 1-5 at lines 12-16, rule 6 at line 17. Chat-skill suite (driver, exit 0) pins the `warning-page` pattern.
- **Expected result:** Rule 6 follows rule 5, conditional, Preview-link only, no quoted button.
- **Actual result:** Rule 6 (line 17, one line): "If the host shows a warning page before a relayed Preview link loads, tell the person it is expected and that they should continue past it; this applies only to the Preview link from the build output, never to any other URL." Conditional, scoped, no button name. Judged by the agent from the text; no human reading occurred and none is required by a cited source.
- **Defects:** None

### MC-104

- **Action:** Driver ran `bash scripts/run-python-tests.sh` (results.tsv: exit 1).
- **Expected result:** All previously passing suites still pass, no new failures.
- **Actual result:** 49 passed, 1 failed: supervisor-test.py `SigningAuditTests.test_every_fixture_commit_and_tag_disables_signing`. green-check.md marks this command PREEXISTING (failed before the change); supervisor-test.py is not in the change diff. No new failure. Command exit is nonzero.
- **Defects:** D-1

### MC-201

- **Action:** Ran `UNCLE_PREVIEW_HOST=0.0.0.0 python3 scripts/lib/host_preview.py serve <scratch>` (exit 0) with a python http.server launch.json; grepped output and preview.json for 0.0.0.0.
- **Expected result:** host 0.0.0.0, status running, url host 127.0.0.1, 0.0.0.0 nowhere else.
- **Actual result:** stdout `UNCLE_PREVIEW_PORT=62009`; record host `0.0.0.0`, status running, url `http://127.0.0.1:<port>/`; the only 0.0.0.0 match was the host field (preview.json line 5).
- **Defects:** None

### MC-202

- **Action:** With the server running, curl http://192.168.1.27:62009/ and http://127.0.0.1:62009/ (-m5), cmp bodies, killed the pid, `ps -p`.
- **Expected result:** Both 200 with identical bodies; process gone.
- **Actual result:** 200 and 200, bodies identical, process gone.
- **Defects:** None

### MC-302

- **Action:** Same as MC-202 (non-loopback address 192.168.1.27 from a UDP-connect probe). Its declared dependency MC-301 is not in the checklist; the action does not need MC-301's output, so it was run independently.
- **Expected result:** 200 with loopback-identical body, or SKIP; process gone.
- **Actual result:** 200, identical, process gone afterwards (first run also showed no listener left via lsof).
- **Defects:** None

### MC-402

- **Action:** Read rule 6 (SKILL.md:17) against the three criteria.
- **Expected result:** Conditional, Preview-link only, no button label, no tab promise.
- **Actual result:** Scoped to "a relayed Preview link ... never to any other URL"; no button label; no tab promise. Judged by the agent from the text.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-100 | NO | PASS | SKILL.md:17 read; chat-skill driver exit 0 |
| MC-104 | NO | PASS | driver exit 1 from preexisting supervisor-test failure only (D-1) |
| MC-201 | YES | PASS | serve exit 0; preview.json host 0.0.0.0, url 127.0.0.1 |
| MC-202 | YES | PASS | curl 200/200 identical; process gone |
| MC-302 | NO | PASS | curl 200 on 192.168.1.27 identical to loopback; process gone |
| MC-402 | YES | PASS | rule 6 text conditional, scoped, no button |
