# Implementation notes

## Step 1

### Files changed

- `.uncle/docs/IMPLEMENTATION_NOTES.md` — Hand-off record: required grant, blocker, AC-5 lists not recorded; Section 4 (in-repo deliverable); SI-3, AC-5 baseline recording

### Unresolved concerns

- Release definition and build script are outside this repo; operator must supply the release repo path and host access.
- AC-5 pre/post grant lists not recorded.
- LV-1..LV-4 live checks BLOCKED-SETUP; nothing was run.

## Driver-recorded scope deviations

### Deviations

- `.gitignore`: Changed outside the plan's change-impact table. Recorded by the driver because this run was unattended and the implementation did not record it; the implementation notes may explain it in prose. Review it in the diff.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | BLOCKED | No grant added; release definition not in repo. | None; release repo path needed. |
| AC-2 | BLOCKED | Not published. | None; host access needed. |
| AC-3 | BLOCKED | No hosted build run. | None; host access needed. |
| AC-4 | BLOCKED | No install run. | None; host access needed. |
| AC-5 | BLOCKED | Grant lists not recorded. | None; release repo needed. |
| AC-6 | BLOCKED | Build script not accessible. | None; script needed. |

```plan-blockers
[
  {
    "id": "PB-1",
    "class": "LIVE_VERIFICATION",
    "requirement_ids": [
      "AC-1",
      "AC-2",
      "AC-3",
      "AC-4",
      "AC-5",
      "AC-6"
    ],
    "restriction_ids": [],
    "evidence": "grep for signed-preview-url outside .uncle and .git found no matches; the plan states the release definition is external.",
    "independent_work": "Wrote the hand-off record in IMPLEMENTATION_NOTES.md."
  }
]
```
