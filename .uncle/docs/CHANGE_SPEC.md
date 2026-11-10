# Change Spec

Omitted sections: Performance (none); Migration (none); Prototype isolation (n/a)

## 1. Change type
Bug fix / feature (hosted preview), in-repo portion only.

## 2. Problem
Person sees Daytona's warning page unprepared; the 0.0.0.0 fallback for the app address is untested at the record level. Other parts of the issue (signed-link grants, 3600s lifetime, autoStopInterval/autoDeleteInterval, real-Daytona address check) belong to the external build script and release and are out of this repo.

## 3/4. Current and desired behavior
Current: chat relays the link with no warning-page note. Desired: chat tells the person Daytona shows a warning page first and to continue past it, without naming a button.

## 5. Observable behavior
| ID | Class | Trigger | Current | Expected | Verification |
|---|---|---|---|---|---|
| B-1 | PRESERVE | Preview line in build output | Rules 1-5 | Unchanged | chat-skill suite |
| B-4 | ADD | Chat relays a Preview link | No warning note | Reply says Daytona shows a warning page first; continue past it; no button name | chat-skill REQUIRED pattern `warning-page` |
| B-2 | MODIFY (test only) | serve with UNCLE_PREVIEW_HOST=0.0.0.0 | Url loopback checked | Also record `host` is `0.0.0.0`; app answers on non-loopback address when one exists | host-preview suite |
| B-3 | PRESERVE | Default host | Loopback | Unchanged | host-preview suite |

## 6. Invariants
| ID | Status | Invariant | Scope | Enforcement | Verification |
|---|---|---|---|---|---|
| I-1 | STRENGTHENED | Skill carries the warning-page rule, stays <= 60 lines | SKILL.md | chat-skill-test REQUIRED | chat-skill suite |
| I-2 | EXISTING | Invalid hosts rejected | host_preview.py | valid_host | host-preview suite |
| I-3 | EXISTING | Wildcard host reports loopback url | host_preview.py | urls_for | host-preview suite |

No RELAXED or REMOVED invariants.

## 7. Compatibility
No change to `.uncle/preview.json` schema or serve output.

## 8. Failure behavior
Unchanged: serve exits 0; failures recorded.

## 10. Security
Skill text must not weaken the bearer-credential and untrusted-output rules.

## 12. Rollback
Revert the three files.

## 14. Non-goals
Build script, #236 release, sandbox auto-stop/auto-delete, signed-link lifetime, changing `host_preview.py` defaults, removing Daytona's warning page.

## 15. Assumptions
- Out-of-repo items (issue Fix 1-4, Checks 1-5) are tracked as manual/live checks, not met by this change. UNRESOLVED: who owns them.
- Default host stays 127.0.0.1; switching to 0.0.0.0 is the build script's decision after a live test.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | skills/uncle-build/SKILL.md contains a rule saying Daytona shows a warning page the first time the link is opened and the person should continue past it, without quoting a button name, and the body stays at or under 60 lines. | bash scripts/run-python-tests.sh -- chat-skill |
| AC-2 | chat-skill-test.py has a `warning-page` REQUIRED pattern and a removal case in test_defect_missing_rules proving a skill without the rule is rejected as 'missing rule: warning-page'. | bash scripts/run-python-tests.sh -- chat-skill |
| AC-3 | A host-preview test with UNCLE_PREVIEW_HOST=0.0.0.0 asserts .uncle/preview.json records host 0.0.0.0, status running, url on 127.0.0.1, and the app answers on a non-loopback local address when one is available. | bash scripts/run-python-tests.sh -- host-preview |
| AC-4 | All previously passing suites in the default python tier still pass and existing skill rules 1-5 remain. | bash scripts/run-python-tests.sh |
| AC-5 | No file outside the planned change surface is modified; host_preview.py and the drivers are unchanged. | git diff --name-only against change-impact table |

