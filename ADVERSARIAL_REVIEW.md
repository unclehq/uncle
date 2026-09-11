## AR-001: Creation check does not prevent concurrent overwrite

| Field | Finding |
|---|---|
| Severity | High |
| References | CHANGE_REQUEST.md §Motivation; CHANGE_SPEC.md I-4, §Compatibility requirements; CHANGE_PLAN.md P-1/P-8/P-9/P-17, C-1, T-2; scripts/from-issue.sh:508–514 |
| Failure | The planned separate absence check and write can overwrite a concurrently created markerless file or follow a substituted symlink; T-2 tests only targets present before invocation. |
| Fix | Require exclusive creation in the absent-target branch; refuse collisions without truncation. |
| Verify | Pause after checking absence, insert a file or symlink, resume; assert nonzero exit and unchanged target bytes. |

## Blocking findings
AR-001

## Regression risks
AR-001

## Recommended simplifications
AR-001: exclusive creation; no workflow-wide lock.

## Required test additions
AR-001: deterministic collision tests.

## Overall assessment
Reject pending AR-001.