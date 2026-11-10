# Verification report

## Findings

### MC-102

- **Action:** None. Release repo and host publish access are absent.
- **Expected result:** Publish succeeds with no "must match one publisher operation" refusal.
- **Actual result:** Not performed. Declared `Depends on: MC-100`, which is not in the checklist.
- **Defects:** D-1

### MC-104

- **Action:** None. Needs MC-102 published and a pre-existing hire.
- **Expected result:** Zero approval prompts on install.
- **Actual result:** Not performed.
- **Defects:** D-1

### MC-105

- **Action:** None. Needs a hosted build with the host refusing the signed-link request.
- **Expected result:** No `Preview:` line, exit status 0, refusal reported.
- **Actual result:** Not performed.
- **Defects:** D-1

### MC-204

- **Action:** None. Depends on MC-201, which is absent from the checklist.
- **Expected result:** Zero approval prompts on reinstall of a pre-existing hire.
- **Actual result:** Not performed.
- **Defects:** D-1

### MC-301

- **Action:** None. Same prerequisite as MC-102.
- **Expected result:** Publish succeeds without the match refusal; otherwise BLOCKED-SETUP naming the access.
- **Actual result:** Not performed.
- **Defects:** D-1

### MC-303

- **Action:** None. Depends on MC-301.
- **Expected result:** Zero Daytona-write approval prompts; install succeeds.
- **Actual result:** Not performed.
- **Defects:** D-1

### MC-404

- **Action:** None. Depends on MC-403, which is absent from the checklist.
- **Expected result:** Zero Daytona-write approval prompts on reinstall.
- **Actual result:** Not performed.
- **Defects:** D-1

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-102 | YES | BLOCKED-SETUP | No release repo or host access. Action: supply both. |
| MC-104 | YES | BLOCKED-SETUP | Depends on MC-102 publish; no hire available. |
| MC-105 | YES | BLOCKED-SETUP | No hosted build environment. |
| MC-204 | YES | BLOCKED-SETUP | Depends on MC-201 (undefined) and a publish. |
| MC-301 | NO | BLOCKED-SETUP | No release repo or host access. |
| MC-303 | NO | BLOCKED-SETUP | Depends on MC-301. |
| MC-404 | YES | BLOCKED-SETUP | Depends on MC-403 (undefined) and a publish. |
