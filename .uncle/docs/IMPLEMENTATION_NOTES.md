# Implementation notes

## Step 1

### Unresolved concerns

- The build script that sends expiresInSeconds=7200 is not in this repository (CHANGE_PLAN.md BLOCKING PLANNING DECISION; docs/preview-link-release.md:40-48). No code change was possible here.
- docs/preview-link-release.md:38 already says 'use an expiry of at most 3600 seconds', so option B (documentation line) would be a no-op and was not applied.
- The owner must choose option A (point the workflow at the build-script repo), or option C (transfer or close the issue).

## Driver-recorded scope deviations

### Deviations

- `.gitignore`: Changed outside the plan's change-impact table. Recorded by the driver because this run was unattended and the implementation did not record it; the implementation notes may explain it in prose. Review it in the diff.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | BLOCKED | Not changed. The build script is not in this repo. | No mocked-publisher test could be written. Doc line docs/preview-link-release.md:38 already states <=3600. |
| AC-2 | BLOCKED | Not changed. The build script is not in this repo. | Not run. A mocked publisher needs the build script. |
| AC-3 | BLOCKED | Not changed. The build script is not in this repo. | Not run. The retry path lives in the external build script. |
| AC-4 | BLOCKED | Not changed. The build script is not in this repo. | Preview-line assertion not run. The in-repo suites are left to the driver's green check. |

```plan-blockers
[
  {
    "id": "PB-1",
    "class": "AUTHORITY",
    "requirement_ids": [
      "AC-1",
      "AC-2",
      "AC-3",
      "AC-4"
    ],
    "restriction_ids": [
      "R-1",
      "R-2"
    ],
    "evidence": "grep of docs/preview-link-release.md finds only line 38 (<=3600); the plan states a repo-wide search finds no expiresInSeconds, 7200 or 'works until'.",
    "independent_work": "None possible in-repo; docs/preview-link-release.md already states the <=3600 rule.",
    "question": "Where does the build script live, so the constant and its mocked-publisher test can be changed?",
    "alternatives": [
      "A: point the workflow at the build-script repo or path",
      "C: close or transfer the issue to the build-script repo"
    ]
  }
]
```
