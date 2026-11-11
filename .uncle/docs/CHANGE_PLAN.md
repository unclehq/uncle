# Change plan

Issue 252

Seeded from [unclehq/uncle#252](https://github.com/unclehq/uncle/issues/252).

Omitted sections: Schema/persistence, Concurrency, Migration, Feature flag, Observability (text-only change)

## 1. Selected technical approach
Insert a new rule 1 in `skills/uncle-build/SKILL.md` covering SB-1..SB-3 (offer, PR-path wording, no-repository sandbox build per decision D-1). Renumber old rules 1-6 to 2-7. Update description. Extend the checker.

## 2. Alternatives considered
- Append as rule 7: rejected; request says top and the first rule is what she reads first.
- Separate skill file: rejected; one more thing to load, tests are per-file.
- 3(b) ask for repository first: not selected; D-1 follows the request's recommendation and 'one sentence' listing.

## 3. Why preferred
Smallest change, keeps the existing checker architecture, and is fully testable by file text.

## 4. Decisions
| ID | Decision | Reason |
|---|---|---|
| D-1 | Adopt 3(a) | Recommended in request; matches listing promise |
| D-2 | Renumber rather than append | Request says top |
| D-3 | New rules stay in one rule line each, within 60-line cap | Checker cap |

## 5. Components not to modify
Build script, hosting, `critical-suites.txt` (suite must stay out of default tier, chat-skill-test.py:102), other tests.

## 6. Interface changes

SKILL.md rule list 1-7; description line. New REQUIRED ids: `offer-preview`, `link-with-pr`, `no-repo-build`, and `no-invented-link` (rule 1 applies only when a valid Preview line exists; otherwise never invent or promise a link). The four patterns must be non-overlapping so each clause is detected only by its own id. `link-with-pr` matches wording that always promises a link to try the app and mentions a pull request only when a repository is named and publishing is separately authorized. Wording must avoid FORBIDDEN phrases and real URLs (use no URL at all).

## 7. Error and recovery

Unchanged no-link rules (now 5). Precedence: when a sandbox or hosted build yields no valid Preview line, or a malformed one, the existing no-link and malformed-output rules override the new rule 1; no link is invented and none is promised for that run. Release-instruction edit lives outside this repo; if it cannot be made, the skill alone may not override the release's PR-only statement (risk R-1).

## 8. Rollback plan
Revert SKILL.md and chat-skill-test.py; republish previous release.

## 9. Restrictions
| R-ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | REPOSITORY | chat-skill-test.py:13,35,85 | AC-4,AC-5 | Cap, forbidden phrases, numbering hold | Run suite; keep wording within rules | Existing invariants | CAP-PY | CODING |
| R-2 | USER | CHANGE_REQUEST.md Fix 1,4 | AC-6 | Release instructions match skill | Manual edit and publish of release | Not in repo | CAP-RELEASE | LIVE_VERIFICATION |

Feasibility: `scripts/run-python-tests.sh` exists (checked); selector `-- chat-skill` per test docstring. CAP-RELEASE (release access, grant #251) is unavailable to coding and does not block steps 1-2.

## 10. Automated-test strategy

`bash scripts/run-python-tests.sh -- chat-skill`: add three REQUIRED patterns; update numbering checks to 1-7, warning-page regex to `^7\.`, the minimal good variant (rule 7), and the numbering test. Defect tests for the new rules are per clause, not whole-line: for each of AC-1..AC-3, mutate only that clause of rule 1 (AC-1: the preview offer before a build and the stated one-hour expiry; AC-2: the PR-and-link wording; AC-3: the sandbox no-repository build and the deferred PR offer), keep the other clauses and the 1-7 numbering intact, and assert the checker rejects it with a failure naming the corresponding REQUIRED id (`offer-preview`, `link-with-pr`, `no-repo-build`). Also add a reworded variant (e.g. 'previews are not possible' added) that must be rejected via the new `previews-impossible` forbidden check. These per-clause and previews-impossible tests are mandatory.

Per-clause mutation tests live in `scripts/tests/chat-skill-test.py` and use `str.replace` on one clause only (not whole-line drops), asserting `missing rule: <id>` for that clause's id. Add the `no-invented-link` REQUIRED pattern (rule 1 is conditioned on a valid Preview line; with none, the existing no-link and malformed-output rules take precedence and no link is invented or promised) and a defect test that removes only that condition and must be rejected with `missing rule: no-invented-link`.

## 11. Regression-test strategy
All existing REQUIRED and defect tests must still pass on the renumbered skill; the default `run-python-tests.sh` and shell suite are re-run by the driver against baseline.

## 12. Manual-verification strategy
LIVE: after publishing the release, send the issue's message to a fresh hire; reply must not say previews are impossible; under D-1 the run ends with a clickable `Preview:` link. Prerequisite: release grant #251 (not a coding prerequisite).

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `skills/uncle-build/SKILL.md` | New rule 1, renumber to 7 rules, description update | SB-1..SB-3, SB-6 | Breaks numbering/forbidden checks | chat-skill suite |
| `scripts/tests/chat-skill-test.py` | New REQUIRED patterns, 1-7 numbering, rule-7 regex, defect tests | AC-1..AC-5 | Test becomes weaker | self + defect injection |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | SB-1 | SI-3 | SKILL.md | offer-preview, per-clause mutation: offer clause removed, other clauses kept, rejected naming offer-preview, per-clause mutation: expiry clause removed, rejected, previews-impossible defect variant | live chat check |
| The skill always promises a link to try the app; it mentions a pull request only when a repository is named and publishing is separately authorized, never as an unconditional deliverable. The `link-with-pr` pattern matches this conditional wording. | SB-2 | SI-3 | SKILL.md | link-with-pr, per-clause mutation: PR-and-link wording removed, other clauses kept, rejected naming link-with-pr, previews-impossible defect variant | live chat check |
| AC-3 | SB-3 | SI-3 | SKILL.md | no-repo-build, per-clause mutation: sandbox no-repository clause removed, rejected naming no-repo-build, per-clause mutation: deferred PR offer removed, rejected naming no-repo-build | live: clickable Preview link |
| AC-4 | SB-4, SB-5, SB-6 | SI-1, SI-2, SI-4: with no valid Preview line, existing no-link and malformed-output rules take precedence; no link is invented or promised | both | existing + numbering tests, description-covers-offer-and-report check plus after-only-description defect test, offer-preview-in-rule-1 anchor plus swapped-rules defect test | none |
| AC-5 | all | SI-1 | both | full chat-skill suite | none |
| AC-6 | SB-1, SB-3 | none | release (external) | none | live check |

The offer-preview defect test is the regression test: it fails against the current skill (rule absent) and passes after.

## Implementation sequence

1. Extend the checker first (tests fail against current skill, proving the gap): add patterns `offer-preview`, `link-with-pr`, `no-repo-build`, numbering 1-7, rule-7 warning regex, updated good variant, defect tests. Also: (a) add a `description-covers-offer-and-report` check requiring the front-matter description to mention offering a preview before a build and reporting the link afterward, with a defect test restoring the original after-only description ('How to report the preview link after running the uncle build script in chat.') that must be rejected; (b) add a rule-1 anchor: extract the text of numbered rule 1 and require the `offer-preview` pattern to match within it (fail as `missing rule: offer-preview in rule 1`), with a defect test that swaps the offer rule with another rule while keeping 1-7 numbering that must be rejected. Decisions D-1..D-3.
   Owns: `scripts/tests/chat-skill-test.py`
2. Edit the skill: new rule 1 written as separately mutable clauses, one per behavior, so a per-clause mutation can remove one clause while leaving the others and the matching requirement ID rejects it: (a) offer-preview: a link ends every finished hosted build, valid up to an hour, and never say previews are impossible; (b) link-with-pr: describe the build as providing a link to try the app, and promise a pull request only when a repository is named and the user separately authorizes publishing; (c) no-repo-build: with no repository build in the sandbox, end with the link and offer a pull request once a repository is named. Precedence: if a sandbox or hosted build produces no valid Preview line, the existing no-link and malformed-output rules (now in the renumbered rules) take precedence; never invent a link or promise that this run produced one. Renumber 2-7, update description. Builds on step 1's tests.
   Owns: `skills/uncle-build/SKILL.md`
   Depends on: 1
3. Run `bash scripts/run-python-tests.sh -- chat-skill` and fix wording until green.
   Depends on: 2
4. Live step (not coding): edit and publish release instructions, run live check. Needs CAP-RELEASE.
   Depends on: 3

Step ownership notes: step 1 (owns chat-skill-test.py) also owns the per-clause `replace`-based mutation tests, the `no-invented-link` pattern and its defect test; step 2 must keep each clause of rule 1 a separately mutable sentence.

## Scope cuts under time pressure

Mandatory and never cut under time pressure: SB-1, SB-2 wording, numbering, every test required by AC-1 through AC-5 (including the per-clause defect tests for AC-1..AC-3, each rejected by the matching requirement ID, and the `previews-impossible` forbidden defect test), and the AC-6 note. If time expires, defer completion rather than drop any of these; removing one requires revising and reapproving the specification. Cut first: optional wording polish and any extra non-required variants. Only the live AC-6 release verification step (step 4) may slip, because it depends on external access (CAP-RELEASE); it is reported NOT RUN and never converted to a pass.

## Risks and unresolved questions
| ID | Risk |
|---|---|
| R-1 | Release instructions (outside repo) may still force PR-only behavior, contradicting the skill; fix item 1 requires editing them |
| R-2 | Human may prefer 3(b); change is a one-rule wording swap and pattern `no-repo-build` update |
| R-3 | File-text tests cannot prove the agent follows the skill; only the live check does |

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | A PR cannot be promised for sandbox builds or when publishing is not separately authorized; the link is the only unconditional deliverable. | Step-2 wording now describes the build as providing a link to try the app and promises a PR only when a repository is named and publishing is authorized. |
| AR-002 | Accepted | Cutting SB-2 wording would leave implementation and AC-2 enforcing different scopes. | Section 16 now makes SB-2 wording and all AC-1..AC-5 tests mandatory; defer completion instead of cutting. |
| AR-003 | Accepted | The new link rule must not override preserved no-link and malformed-output handling; precedence must be explicit. | Edit step-2 and s7.1 to state existing no-link/malformed rules take precedence and no link is ever invented or promised. |
| AR-004 | Accepted | Line-drop mutations remove all three behaviors at once; each new REQUIRED id needs an independent clause-level mutation. | Edit step-1 to require per-clause mutation defect tests rejected by the matching ID; AC-1/AC-2/AC-3 text is owned elsewhere, so only step-1 text and s16.1 are touched. |
| AR-005 | Accepted | Cutting SB-2 wording or the previews-impossible test would let implementation and acceptance target different requirements. | Section 16 now makes SB-2 wording and the previews-impossible defect test mandatory; they may not be cut without revising and reapproving the spec. |
| AR-006 | Accepted | Whole-line deletion removes all three new behaviors at once and cannot show each clause is individually protected. | Section 10, step-2 and AC-1..AC-3 require per-clause mutations that keep the other clauses and assert rejection naming the matching requirement ID. |
| AR-007 | Accepted | The checker only tests that the description is nonempty, so the description change was unprotected. | Step 1 and AC-4 add a description check and a defect variant restoring the after-only description. |
| AR-008 | Accepted | Sequential numbering and body-wide patterns do not prove the offer rule sits at rule 1. | Step 1 and AC-4 anchor offer-preview inside numbered rule 1 and add a swap-rules defect variant. |
