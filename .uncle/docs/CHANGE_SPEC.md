# Change Spec: Issue 264

Omitted sections: Migration (none); Prototype isolation (not a prototype); Security beyond link lifetime (no change)

## 1. Change type
Bug fix, in the external build-script repo.

## 2. Problem statement
A hosted build lasting more than an hour hands over an expired signed preview link, because the link is requested only once, early.

## 3. Current behavior
See request and baseline B-2 (UNRESOLVED, source absent). Per the request: `announce_preview` prints the link once and sets `sb.announced`; `build` returns early when announced; `sb.link_expires` keeps the first link's expiry.

## 4. Desired behavior
At the end of `build`, after the pull request, always request a fresh signed link, print it as the last `Preview:` line, and set `sb.link_expires` from it. The early link is still printed during the build. Optionally expire the earlier link.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| BH-1 | PRESERVE | Preview appears mid-build | Prints `Preview: <url> (works until <time>)` | Unchanged | build-script test |
| BH-2 | MODIFY | Build ends after PR, link already announced | No new link; early link is last | Fresh link requested; last `Preview:` line is the fresh link | build-script test, mocked clock |
| BH-3 | MODIFY | Same | `sb.link_expires` = first link expiry | `sb.link_expires` = final link expiry; kept-sandbox label and `kept ... until` match | build-script test |
| BH-4 | PRESERVE | No link ever refused | No request over 3600 s | Same | build-script test |
| BH-5 | ADD (optional) | Fresh link issued | Both links live | Earlier link expired via POST .../expire | build-script test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | EXISTING | No signed-link request has expiresInSeconds > 3600 | build.py | link request code | mocked publisher test |
| INV-2 | STRENGTHENED | The last printed link is valid for >= 55 min after build end | build.py | end of `build` | mocked clock test |
| INV-3 | STRENGTHENED | Kept-sandbox label equals the last printed link's expiry | build.py | `sb.link_expires` | test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Setting `sb.link_expires` and label format unchanged.

## 8. Error and failure behavior
If the final link request fails, behavior is UNRESOLVED: keep the early link as the last line and say it may have expired, or fail. Needs decision by the build-script owner.

## 14. Non-goals
autoStopInterval value (#263).

## 15. Assumptions and unresolved questions
- BLOCKING: the code is not in this repository (baseline section 2).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With a mocked publisher and clock, preview appears at 1 min and the build ends at 70 min; the last `Preview:` line's end time is at least 55 minutes after the build ends. | Build-script test (external repo). |
| AC-2 | The kept-sandbox label and the `kept ... until` line equal the last link's expiry. | Build-script test (external repo). |
| AC-3 | A build whose link was never refused makes no signed-preview-url request with expiresInSeconds above 3600. | Mocked publisher assertion (external repo). |
| AC-4 | The early link is still printed while the build runs. | Build-script test (external repo). |

