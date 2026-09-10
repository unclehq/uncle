## AR-001: New-application races lack the claimed driver guard

| Field | Finding |
|---|---|
| Severity | Medium |
| References | CHANGE_REQUEST.md:13–18; CHANGE_SPEC.md:I-3; CHANGE_PLAN.md:P11,P3,T1,T2; scripts/stagegate.sh:1096,1264; scripts/lib/early-prerequisites.py:13; scripts/change-workflow.sh:1523 |
| Failure | If REQUIREMENTS.md disappears after the planned stat, the new-application driver can launch an agent without it; mocked launches miss this, and inspection widened to scripts/stagegate.sh and scripts/lib/early-prerequisites.py disproves P11’s fallback claim. |
| Fix | Explicitly accept selection-time checking with this residual risk, or authorize a driver guard. |
| Verify | Inject deletion between stat and launch; assert the chosen driver outcome. |

## Blocking findings
AR-001: resolve before approval.

## Regression risks
AR-001.

## Recommended simplifications
AR-001: retain selection-time scope.

## Required test additions
AR-001.

## Overall assessment
Revise AR-001.