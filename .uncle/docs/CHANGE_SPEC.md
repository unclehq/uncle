# Change spec

Omitted sections: Performance (none); Migration (none); Prototype isolation (not a prototype)

## 1. Change type
Bug fix (agent instructions).

## 2. Problem statement
See Issue 252 / B-1: the hosted chat agent denies previews and does not say a build ends with a link.

## 3. Current behavior
B-1, B-2, B-3 in the baseline.

## 4. Desired behavior
Skill states a finished hosted build ends with a link to the running app, valid up to an hour; when asked for a preview she says a build gives that link and never says previews are impossible; when describing what a build delivers she says "a pull request and a link to try the app". With no repository she builds in the sandbox, ends with the link, and offers a pull request once a repository is named (decision 3(a), the request's recommendation).

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | ADD | Person asks to see the app running / for a preview link | Says previews are impossible | Says a build ends with a link; never says previews are impossible | Checker pattern `offer-preview`; live chat check |
| SB-2 | ADD | Agent describes what a build delivers | PR only | Says "a pull request and a link to try the app" | Checker pattern `link-with-pr` |
| SB-3 | ADD | Preview requested with no repository | Asks for a repository, refuses | Starts a sandbox build, ends with link, offers PR when a repository is named | Checker pattern `no-repo-build`; live check |
| SB-4 | PRESERVE | Build output with/without `Preview:` line | Rules B-2 | Unchanged relay rules | Existing REQUIRED patterns |
| SB-5 | PRESERVE | Warning page | B-3 | Unchanged, now rule 7 | `warning-page` pattern |
| SB-6 | MODIFY | Skill description | Says "after" a build only | Also covers offering the link before a build | Front-matter test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | EXISTING | I-1, I-2, I-3 hold | SKILL.md | `check()` | chat-skill suite |
| SI-2 | STRENGTHENED | Rules numbered 1-7 in order; new offer-preview rule is rule 1; warning page is rule 7 | SKILL.md | `check()` numbering | chat-skill suite |
| SI-3 | NEW | The skill never states previews are unavailable and promises no behavior beyond a link (no auto-open) | SKILL.md | `offer-preview` + FORBIDDEN | chat-skill suite |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Rules 2-6 text unchanged apart from numbering; relay behavior preserved.

## 8. Failure behavior
If no link is produced by a build, existing no-link rule applies unchanged.

## 10. Security
No real URLs added; link remains a bearer credential shared only with the requester.

## 12. Rollback
Revert the two files; republish prior release.

## 14. Non-goals
Build script, release grant, hosting, warning-page handling, editing release instructions inside this repo.

## 15. Assumptions and unresolved questions
- Decision 3(a) assumed (request recommends it); 3(b) is a wording swap only.
- Release-instruction edit and publish (fix items 1 and 4) are outside this repo; handled as a manual/live step. The chat-level check needs the published release and grant #251.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | SKILL.md has a new rule 1 stating a finished hosted build ends with a link to the running app valid up to an hour, that she tells a person asking for a preview that a build gives that link, and never says previews are impossible. | chat-skill-test `offer-preview` pattern passes on the real skill; fails on a variant with the rule removed. |
| AC-2 | SKILL.md says that when describing what a build delivers she says a pull request and a link to try the app. | chat-skill-test `link-with-pr` pattern passes; removal variant is rejected. |
| AC-3 | SKILL.md says that with no repository she builds in the sandbox, ends with the link, and offers a pull request once a repository is named. | chat-skill-test `no-repo-build` pattern passes; removal variant is rejected. |
| AC-4 | Existing relay rules (formerly 1-6) keep their content; rules are numbered 1-7 with the warning-page rule as rule 7; description no longer says only 'after'. | Updated numbering/warning-page checks and all existing REQUIRED patterns and defect tests pass. |
| AC-5 | No forbidden promise phrase, real URL, or quoted button label is introduced; body stays within 60 lines. | `bash scripts/run-python-tests.sh -- chat-skill` exits 0. |
| AC-6 | Release instructions get the matching edit and a release is published; a fresh hire asked for a preview link with no repository does not say previews are impossible and a build ends with a clickable Preview: link. | Manual/live check after publish (outside repo; needs grant #251). |

