# Change specification

Omitted sections: Performance (none); Migration (none); Prototype isolation (not a prototype)

## 1. Change type
Feature.

## 2. Problem statement
Uncle's defaults (its own verification commands, Uncle-style PR, audit text) do not match what upstream maintainers of a project the user does not own will accept. Issue 283.

## 3. Current behavior
See baseline B-1..B-5.

## 4. Desired behavior
`--oss` makes the change run discover and record the project's guidelines (with file and line sources, missing ones listed as unknown), follow them for commits, PR, tests and checks, keep Uncle artifacts out of the PR, refuse publication when the project prohibits AI-assisted contributions, and stop at a human gate on conflicts or unclaimable issues.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| OB-1 | ADD | `uncle ... --oss` | Unknown argument | Flag accepted; run recorded as OSS mode in the journal; `--oss` appears in help and typo hints | AC-1 |
| OB-2 | ADD | Plan stage under `--oss` | No discovery | Plan has a guidelines table: each guideline with source `file:line`, plus an Unknown list for absent guidance | AC-2 |
| OB-3 | ADD | No contributing guidance found | n/a | Plan states none found; conventions from recent merged PRs and CI appear labeled `inferred` | AC-3 |
| OB-4 | ADD | Project policy prohibits AI contributions | PR published | Publication refused before any branch, commit, push or `gh` write; user told why | AC-4 |
| OB-5 | ADD | Project defines verification commands (CI, Makefile, test config) | Uncle commands | Plan's verification commands are the project's own; required checks that cannot run are reported not run, never passed | AC-5 |
| OB-6 | ADD | Project requires DCO and has PR template, commit format | Uncle format | Commits carry `Signed-off-by`; PR body fills the project's PR template; commit/PR title follow the stated format | AC-6 |
| OB-7 | ADD | Guidelines conflict with each other, the issue or Uncle rules; or issue is assigned/labeled not open/needs discussion | n/a | Run stops at a human gate with the conflict or warning listed; no silent choice | AC-7 |
| OB-8 | ADD | `--oss` publish | Uncle files possible | Diff and PR text contain no Uncle-generated files or vocabulary (no-footprint rules apply) | AC-8 |
| OB-9 | PRESERVE | Any run without `--oss` | Existing | Unchanged prompts, journal, PR | AC-9 |
| OB-10 | ADD | README | Undocumented | README documents flag, limits and open-question decisions | AC-10 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | NEW | A run's OSS mode is fixed in the journal at start; resume cannot change it | change-pr | journal `oss` key | AC-1 |
| INV-2 | NEW | A detected AI-prohibition policy blocks PR creation | publish | oss.py check before publish | AC-4 |
| INV-3 | NEW | A check that did not run is never reported as passed | report | existing record rules; plan commands | AC-5 |
| INV-4 | EXISTING | No-footprint invariants (I-1) hold in OSS mode | publish | footprint.scan | AC-8 |
| INV-5 | EXISTING | Human approval gates unchanged | all | stagegate | AC-9 |
| INV-6 | EXISTING | Non-OSS behavior identical | all | env gating | AC-9 |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Additive flag; no change without it.

## 8. Error and failure behavior
No guidance: say so, use labeled inferred conventions. Unbuildable project: report checks not run. AI-prohibited: stop before PR. Unclaimable issue: warn and wait at a human gate.

## 10. Security requirements
PR text and branch scanned by footprint rules; discovery reads only repository files; no network use added beyond existing `gh` use.

## 12. Rollback
Revert the change; journal `oss` key is ignored by older code.

## 14. Non-goals
Automatic forking; fetching wikis or external sites; inferring `--oss` from write access; changing approval gates or merge decision.

## 15. Assumptions and decisions on open questions
| Q | Decision |
|---|---|
| Q1 relation to no-footprint | `--oss` implies `--no-footprint` |
| Q2 fork | Not automated. Uncle publishes to the existing remote logic; if the user cannot push, the run stops with instructions |
| Q3 wiki/external guidance | Listed as unknown; the user may paste it into the change request |
| Q4 infer `--oss` | Not inferred; explicit flag only |

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `--oss` is accepted by the launcher, exports UNCLE_OSS=1 and UNCLE_NO_FOOTPRINT=1, is listed in help and typo hints, and the journal records `oss` at start and keeps it on resume. | scripts/tests/oss-test.py wiring checks over `uncle` and change-pr.sh text and journal creation |
| AC-2 | Under --oss the change-request-bound stage prompts carry instructions to discover guidelines and the plan lists each guideline with file:line source and an Unknown list. Discovery on a fixture repo with CONTRIBUTING.md, PR template, DCO and non-default test command returns each with its source. | oss-test.py runs oss.py discover on a disposable fixture and asserts entries with sources and unknowns |
| AC-3 | With no guidance present, discovery reports none found and the prompt requires inferred conventions labeled `inferred`. | oss-test.py on an empty fixture; prompt text assertion |
| AC-4 | A fixture whose policy prohibits AI contributions makes the publish check fail before any branch, commit, push or gh call; a permissive or silent policy passes. | oss-test.py on prohibiting, disclosure-required and silent fixtures |
| AC-5 | Plan prompt requires the project's own verification commands and requires checks that cannot run to be recorded as not run. | oss-test.py asserts the prompt text; plan review |
| AC-6 | On the fixture, the commit message carries `Signed-off-by` when DCO is required and the PR body is rendered from the project's PR template with the change filled in. | oss-test.py unit tests of oss.py render functions |
| AC-7 | Guideline conflicts, and an issue assigned to someone or labeled not open for contribution, produce a gate-stop with the listed reasons; the default path silent-choice is impossible. | oss-test.py claimability and conflict checks; prompt text requires a Conflicts section |
| AC-8 | The OSS publication diff contains no Uncle files and the body has no Uncle vocabulary (no-footprint rules). | existing no-footprint-test.py plus oss-test.py assertion that OSS implies no_footprint |
| AC-9 | Without --oss, prompts, journal and publication behavior are unchanged and existing suites still pass. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh versus baseline |
| AC-10 | README documents the flag, the decisions on the four open questions, and its limits. | oss-test.py greps README; manual read |

