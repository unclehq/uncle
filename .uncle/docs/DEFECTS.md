# Defects

## D-1

- **Status:** BLOCKED-SETUP
- **Evidence:** No release repo or host access. Action: supply both.
- **Expected result:** Publish succeeds with no "must match one publisher operation" refusal.
- **Actual result:** Not performed. Declared `Depends on: MC-100`, which is not in the checklist.

## D-1

- **Status:** BLOCKED-SETUP
- **Evidence:** Depends on MC-102 publish; no hire available.
- **Expected result:** Zero approval prompts on install.
- **Actual result:** Not performed.

## D-1

- **Status:** BLOCKED-SETUP
- **Evidence:** No hosted build environment.
- **Expected result:** No `Preview:` line, exit status 0, refusal reported.
- **Actual result:** Not performed.

## D-1

- **Status:** BLOCKED-SETUP
- **Evidence:** Depends on MC-201 (undefined) and a publish.
- **Expected result:** Zero approval prompts on reinstall of a pre-existing hire.
- **Actual result:** Not performed.

## D-1

- **Status:** BLOCKED-SETUP
- **Evidence:** No release repo or host access.
- **Expected result:** Publish succeeds without the match refusal; otherwise BLOCKED-SETUP naming the access.
- **Actual result:** Not performed.

## D-1

- **Status:** BLOCKED-SETUP
- **Evidence:** Depends on MC-301.
- **Expected result:** Zero Daytona-write approval prompts; install succeeds.
- **Actual result:** Not performed.

## D-1

- **Status:** BLOCKED-SETUP
- **Evidence:** Depends on MC-403 (undefined) and a publish.
- **Expected result:** Zero Daytona-write approval prompts on reinstall.
- **Actual result:** Not performed.
