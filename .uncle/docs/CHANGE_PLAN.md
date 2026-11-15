# Change plan: `--oss`

Issue 283

Seeded from [unclehq/uncle#283](https://github.com/unclehq/uncle/issues/283).

Omitted sections: Schema (journal key only, see 9); Migration (none); Concurrency (none new); Feature-flag (the flag itself)

## 1. Selected technical approach

- New pure module `scripts/lib/oss.py`: `discover(root)` returns guideline entries `{kind, text, source file:line}` plus an unknown list. Discovery reads only files whose fully resolved path (symlinks followed) lies inside the resolved repository root; any guidance path whose resolved target lies outside the root is rejected, reported in the unknown list with its path and reason, and its contents are never read or reproduced. Also: `ai_policy(entries)` returns `prohibited|disclose|allowed|unknown`; `dco_required`; `claimable(issue_json)`; `render_pr_body(template, summary, testing)`; `signoff(message, name, email)`; CLI `oss.py check-publish` exits nonzero with a reason on prohibition.
- New prompt appendix `prompts/change/oss-guidelines.md`, appended by `bind_change_request_source` only when `UNCLE_OSS=1`. It tells the stage to read the guidance files, write a guidelines table with `file:line` sources, list unknowns, label inferred conventions `inferred`, use the project's own verification commands (not Uncle's) and a Conflicts section, and states checks that cannot run are recorded not run.
- `uncle` parses `--oss`, exports `UNCLE_OSS=1` and `UNCLE_NO_FOOTPRINT=1`.
- `change-pr.sh` records `oss` in the journal, runs `oss.py check-publish` before any write, signs off commits when DCO is required, and builds the body from the project's PR template when one exists.

## 2. Alternatives considered
* Agent-only prompt change: no deterministic AI-policy refusal. Rejected.
* Separate OSS driver: large duplication. Rejected.
* Auto-fork: needs write access and network; out of scope (decision Q2).

## 3. Why preferred
Reuses the no-footprint machinery and prompt binding, adds a deterministic pure module that is testable offline, and leaves non-OSS paths untouched.

## 4. Components to modify
See change-impact table.

## 5. Components not to modify
`workflow.sh`, `stagegate.sh`, approval-gate scripts, `footprint.py`, attestation, TUI.

## 6. Data-flow
`--oss` -> env -> prompt appendix (plan stage) and journal (publish) -> `oss.py check-publish` -> publish or refuse.

## 8. Interface changes
New flag `--oss`; env `UNCLE_OSS=1`; journal key `oss: true`.

## 9. Persistence
Journal gains optional `oss` boolean; older code ignores it.

## 10. Compatibility
Gated on env/journal key; absent means current behavior.

## 12. Error and recovery
| Condition | Behavior |
|---|---|
| Policy prohibits AI | `check-publish` refuses before any git/gh write; message names source file:line; rerun after the human decision |
| Policy unknown or disclose | Proceed; disclosure already mandatory under no-footprint |
| Guidance missing | Prompt requires inferred-labeled conventions |
| Issue claimed or not open | Plan stage lists a warning; plan approval gate is the human decision |
| Conflicting guidance | Listed in plan Conflicts section; approval gate decides |

## 14. Rollback
Revert the commit. Journals written with `oss` remain readable.

## 16. Automated-test strategy

New `scripts/tests/oss-test.py`, run by `bash scripts/run-python-tests.sh -- oss`; fixtures are disposable git repos with `commit.gpgsign=false` and `tag.gpgsign=false`, using `git -c commit.gpgsign=false -c tag.gpgsign=false` and `--no-gpg-sign`. Cases: discovery with sources and unknowns, empty fixture, AI prohibition vs silent, DCO sign-off, PR template rendering, claimability, wiring greps for AC-1/AC-5/AC-10. Resume-precedence cases (AC-1/INV-1): on resume the journal's OSS value governs prompt binding and publication regardless of the current flag or environment; a missing key means false; assert both mismatch directions (journal oss=true with no flag/env keeps the appendix, policy check and no-footprint; journal oss=false or legacy journal with `--oss`/`UNCLE_OSS=1` stays non-OSS or rejects the conflicting flag) and a legacy journal without the key. Added to `critical-suites.txt`.

## 17. Regression strategy
Full shell and Python default tiers versus baseline; existing `no-footprint-test.py` unchanged.

## 18. Manual verification
Run `uncle --issue` dry flow on a scratch fork with `--oss` and read the plan guideline table; confirm refusal on a prohibiting fixture.

## 19. Observability
Publish refusal message names the policy source; plan table shows sources.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/oss.py` (new) | pure discovery (with resolved-path containment: out-of-root symlink targets reported unknown, unread), policy, template, sign-off, check CLI | deterministic, testable | Low | `oss-test.py` (including a fixture with a guidance symlink pointing outside the repo: asserted unknown and its content absent from output) |
| `prompts/change/oss-guidelines.md` (new) | stage instructions | guideline discovery and recording | Low | prompt assertions |
| `scripts/change-workflow.sh` | append prompt when `UNCLE_OSS=1` in `bind_change_request_source` | inject into stages | Medium | wiring test, full suite |
| `uncle` | parse `--oss`, help, allow-list, typo hints | flag | Medium | wiring test |
| `scripts/lib/change-pr.sh` | journal key, publish check, DCO sign-off, template body | outward action | High | `oss-test.py`, `pr-auto-publish` |
| `scripts/tests/oss-test.py` (new) | suite | coverage | Low | self |
| `scripts/tests/critical-suites.txt` | add `oss` | default tier | Low | runner |
| `README.md` | document flag and limits | AC-10 | Low | grep |

## Traceability

Resume-precedence rule: on resume, the OSS mode stored in the run journal is authoritative over the `--oss` flag and `UNCLE_OSS` environment variable. A journal with oss=true keeps OSS guidance and the no-footprint publication check even when the flag and env are absent. A journal with oss=false, or a legacy journal without an `oss` key, is treated as non-OSS; `UNCLE_OSS=1` does not change it, and a conflicting `--oss` flag is rejected before any stage runs. The journal's mode is restored before prompt binding.

AC-7 verification is behavioral: advisory warnings or prompt text alone do not satisfy it. The gate-stop test must show the workflow halts at the existing human gate with the reasons listed and does not advance until approval is given.

PR body composition rule: `render_pr_body` fills the project's PR template, retains the mandatory AI disclosure, and appends it when the template has no disclosure field. The complete rendered body then passes through the existing no-footprint validation before any publication write. If template requirements conflict with the disclosure or no-footprint rules, publication stops at the existing human gate with the conflict listed.

Resume precedence: the journal's recorded `oss` value is authoritative for prompts and publication. A missing key means false. On resume the driver restores `UNCLE_OSS` and the implied `UNCLE_NO_FOOTPRINT` from the journal before prompt binding or any publication write, and rejects a conflicting `--oss` flag before stage execution. A non-OSS run cannot acquire OSS behavior, and an OSS run cannot lose it.

Resume rule (INV-1): on resume, the journal's `oss` value is authoritative over the current flag or environment, and a missing key means false. Before any prompt binding or publication write, restore both `UNCLE_OSS` and the implied `UNCLE_NO_FOOTPRINT` from the journal. A conflicting `--oss` flag is rejected before stage execution. A resumed non-OSS run cannot acquire OSS behavior.

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 (including resume: the journal's stored OSS mode is authoritative over env and flag) | OB-1 | INV-1 | uncle, change-pr.sh, change-workflow.sh (resume restoration before prompt binding) | `oss-test.py` wiring, resume cases: journal oss=true with flag/env absent keeps OSS prompts, guidelines table, no-footprint and publication check, journal oss=false with UNCLE_OSS=1 stays non-OSS, legacy journal without `oss` key means false (env UNCLE_OSS=1 does not enable OSS), conflicting --oss flag on resume rejected before any stage runs | flag in help, resume an OSS run without --oss and confirm the guidelines table and publish check still apply |
| AC-2, AC-3 | OB-2, OB-3 | INV-3 | oss.py, prompt | discovery tests | read plan table |
| AC-4: any detected AI prohibition takes precedence over permissive or conflicting guidance and cannot be waived by plan approval; `check-publish` refuses before any publication write. | OB-4 | INV-2 | oss.py, change-pr.sh | policy tests, fixture with both a prohibition and permissive guidance asserting `prohibited` and refusal regardless of plan approval, entry-point test: run the publication entry point in `change-pr.sh` against a prohibiting fixture with recording git/gh shims on PATH, asserting nonzero exit, the policy source file:line in the message, and zero branch, commit, push or gh invocations recorded | prohibiting fixture |
| AC-5 | OB-5 | INV-3 | prompt | prompt assertion | plan commands |
| AC-6 | OB-6 | INV-4: the final body, after template rendering, always contains the AI disclosure and passes no-footprint validation. | oss.py, change-pr.sh | render tests, `render_pr_body` tests: template without a disclosure field gets the disclosure appended, template with one keeps it, and the rendered body is validated by no-footprint checks after rendering, `render_pr_body` and `signoff` unit tests, title/commit-format tests: explicit formats discovered from guidance are applied to the commit message and PR title, DCO trailer preserved, incompatible requirements listed for the existing human gate, integration test in `oss-test.py`: for a disposable DCO-required fixture with a PR template, run the real publish entry point of `change-pr.sh` with recording git/gh shims and assert that the actual commit message passed to git contains the required `Signed-off-by` trailer and that the PR body submitted to gh contains the populated project template content | PR body read, commit message trailer read |
| AC-7 | OB-7 | INV-5 | oss.py, prompt | ["claimability tests", "gate-stop test: run conflicting guidance and an unclaimable issue (claimed or not open) through the workflow with approval withheld, assert the listed reasons appear, no stage advances, and no default choice is silently selected even when one is available"] | gate view |
| AC-8 | OB-8 | INV-4 | change-pr.sh | ["footprint + oss tests", "template rendering: a template without a disclosure field gets the disclosure appended", "template containing forbidden Uncle vocabulary or an incompatible requirement is not altered: the rendered body fails the existing no-footprint validation and publication stops at the human gate with the conflict listed", "complete rendered body passes existing no-footprint validation"] | diff read |
| AC-9 | OB-9 | INV-6 | all | full suites, resumed non-OSS and legacy journals show no OSS prompt appendix or publish check | none |
| AC-10 | OB-10 | none | README.md | README grep | read |

Resume precedence (AR-008): on resume, the journal's stored OSS mode overrides the environment and the --oss flag. A missing `oss` key means false. Before any prompt binding or publication write, the stored mode restores both UNCLE_OSS and the implied UNCLE_NO_FOOTPRINT, so the policy check and no-footprint enforcement always run for an OSS run. A resumed non-OSS run cannot acquire OSS behavior from the environment. A --oss flag that conflicts with the stored mode is rejected before stage execution.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Desired behavior | AC-4 | PR not created when AI prohibited | `oss.py check-publish` before publish write | deterministic, offline | CAP-GIT-FIXTURE | `change-pr.sh:1710-1717, 2147` inspected; entry-point test with recording git/gh shims asserts zero write calls on refusal | CODING |
| R-2 | USER | CHANGE_REQUEST | AC-8 | no Uncle artifacts | imply no-footprint; when filling a project PR template, `render_pr_body` preserves the mandatory AI disclosure (appending it if the template has no disclosure field) and never silently alters or omits template content; the complete template-rendered PR body then passes existing no-footprint validation after rendering and before publication; if template requirements conflict with disclosure or no-footprint rules (e.g. forbidden vocabulary), the run stops at the existing human gate with the conflict listed | reuse | CAP-NONE | `uncle:351` inspected | CODING |
| R-3 | USER | CHANGE_REQUEST | AC-9 | unchanged without flag; mode fixed at start | journal-authoritative gating: recorded `oss` governs prompts and publication on resume; missing means false; conflicting `--oss` rejected before stage execution | safe | CAP-NONE | `change-workflow.sh:2097-2120` inspected | CODING |
| R-4 | PLATFORM | CLAUDE.md signing rules | AC-6 | fixtures disable signing | explicit git flags | no user key use | CAP-GIT-FIXTURE | stated in strategy | CODING |
| R-5 | DESIGN | plan | AC-4 | keyword heuristic for policy | revisable pattern list in `oss.py` | agent cannot be sole gate | CAP-NONE | none needed | CODING |

Live verification (CAP-GH-LIVE, LIVE_VERIFICATION phase): requires `gh` authentication and a scratch fork; not a coding prerequisite. No checks are approved for live auto-run; manual check only.

## Implementation sequence

Steps are mostly independent files.

1. Pure module `oss.py` (discover with resolved-path containment, ai_policy, dco, claimable, render, signoff, commit-message and PR-title format discovery, check CLI). Reqs AC-2..AC-7.
   Owns: `scripts/lib/oss.py`
2. Prompt appendix. The stage records discovered commit-message and PR-title formats in the plan guidelines table and lists incompatible formatting requirements in the Conflicts section. Reqs AC-2, AC-3, AC-5, AC-6, AC-7.
   Owns: `prompts/change/oss-guidelines.md`
3. Tests `oss-test.py` and add `oss` to critical tier. Reqs all. Builds on the API of step 1 and the prompt file name of step 2 (no code dependency).
   Owns: `scripts/tests/oss-test.py`, `scripts/tests/critical-suites.txt`
4. Launcher flag and prompt-binding hook. On resume, read the journal's `oss` value (missing means false) and use it, not the current flag or environment, to decide `UNCLE_OSS`/`UNCLE_NO_FOOTPRINT` exports and appendix binding before any stage runs; reject a conflicting `--oss` flag. The prompt appendix also instructs the stage to list, in the Conflicts section, any PR-template requirement that conflicts with mandatory AI disclosure or no-footprint rules, so the existing human gate decides. Reqs AC-1, AC-9.
   Owns: `uncle`, `scripts/change-workflow.sh`
   Depends on: 2, 5
5. Publish wiring: journal key (authoritative on resume; missing means false), check, sign-off, template body. Publication reads the journal value, never the environment, to decide the policy check and no-footprint enforcement. The `oss.py check-publish` call must run first in the publication entry point and its failure must abort. Discover explicit commit-message and PR-title formats, apply them to publication output, preserve required DCO trailers, and send incompatible formatting requirements to the existing human gate. The commit message and PR body actually submitted to git/gh must be the outputs of `signoff` and `render_pr_body`, not the pre-existing message or body, so shim-based integration tests can observe them. Add entry-point tests in `oss-test.py` with recording git/gh shims: on a prohibiting fixture assert failure, policy source, and zero branch/commit/push/gh invocations; on a DCO fixture with a PR template assert the recorded commit message and PR body. Reqs AC-1, AC-4, AC-6, AC-8.
   Owns: `scripts/lib/change-pr.sh`
   Depends on: 1
6. README. Reqs AC-10.
   Owns: `README.md`
   Depends on: 4, 5

Completion rule (binding; overrides the scope-cut section): PR template rendering, required DCO sign-off, and claimability checks (AC-6, AC-7) remain required for completion; deferral requires an explicitly approved specification change. The scope-cut section may not be used to drop them or to substitute a README limit. Only items not required by an acceptance criterion may be cut under time pressure.

## 21. Scope cuts under time pressure

Never cut: AI-policy refusal, flag gating, resume precedence, PR template rendering, required DCO sign-off, claimability checks, and any behavior or test listed in the traceability table; the AC-6 and AC-7 tests stay in critical-suites.txt and must pass. Deferral of any of these requires an explicitly approved specification change. Only items not required by an acceptance criterion (for example README wording polish) may be cut under time pressure.

## 22. Risks and unresolved questions
* Keyword AI-policy detection is heuristic (R-5); documented in README as a safety net, with the plan-stage agent also required to flag policy.
* Fork flow is manual (decision Q2); no blocking questions remain.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The scope-cut list contradicts mandatory AC-6 and AC-7; those behaviors cannot be deferred by documentation alone. | Adds a binding completion rule to the Implementation sequence that overrides the scope-cut section: template rendering, DCO sign-off and claimability remain required. |
| AR-002 | Accepted | INV-1 fixes OSS mode at start, and the plan left env and journal competing on resume; making the journal authoritative closes that gap. | Added a resume-precedence rule to the traceability section and extended the AC-1 row's components, tests and manual checks to cover resume. |
| AR-003 | Accepted | OB-6 requires commit and PR title formats; the plan only covered DCO sign-off and body templates. | Extend AC-6 traceability, R-4 restriction and step-5 with commit-message/PR-title format discovery, application, DCO preservation and human-gate on conflict. |
| AR-004 | Accepted | Template rendering had no rule for templates omitting required disclosure or containing forbidden vocabulary; a silent omission or edit would break AC-8 and OB-7. | Adds a template-rendering rule to AC-8 and R-2, a step-5 text clause in the Implementation sequence, and a traceability test for AC-8. |
| AR-005 | Accepted | Prompts used the environment while publication used the journal, so a resumed run could change mode; the journal must be the single authority. | Added a resume-precedence rule to s17 and extended AC-1, AC-9 and R-3 to require journal-governed mode and tests for both mismatch directions and legacy journals. |
| AR-006 | Accepted | Template rendering could bypass the mandatory disclosure and no-footprint validation; composition and validation order must be explicit. | Added a rendering-order rule to s17 and extended AC-6/AC-8 behaviors, invariants and tests; R-2 mechanism now covers validating the final body. |
| AR-007 | Accepted | Plan §12 let the approval gate decide conflicting guidance without excluding AI prohibitions, which could override the mandatory publication block (INV-2). | AC-4 traceability row now states that any detected AI prohibition takes precedence over permissive guidance, cannot be waived by plan approval, and is tested with a conflicting-guidance fixture. |
| AR-008 | Accepted | Plan left env vs journal precedence undefined, so a resume without --oss could drop the policy check and no-footprint enforcement. | Add a resume-precedence rule block to s17 and extend AC-1 requirement and tests to cover mismatch directions and legacy journals. |
| AR-009 | Accepted | Real gap: discover(root) had no symlink containment rule, so an untrusted checkout could surface external file contents. | Section 1 discover() item and the oss.py change-impact row now require resolved-path containment, with out-of-root guidance reported as unknown unread, plus a test. |
| AR-010 | Accepted | Helper unit tests cannot show the publish entry point refuses before side effects; an entry-point test with recording shims is needed. | Extend AC-4 tests, R-1 evidence and step-5 with an entry-point test using recording git/gh shims asserting failure, policy source and zero write calls. |
| AR-011 | Accepted | Warnings and prompt assertions alone cannot prove a gate-stop; a behavioral test with approval withheld is needed for AC-7. | AC-7 row now requires a workflow-level gate-stop test (approval withheld, reasons listed, no stage advancement, default choice available); Traceability section notes it. |
| AR-012 | Accepted | Resume precedence between env and journal was unspecified; a testable rule is needed to satisfy INV-1. | Add resume-precedence rule and mismatch/legacy tests to s12.1 (tests), AC-1 traceability row, and steps 4 and 5. |
| AR-013 | Accepted | Unit tests of render/sign-off helpers cannot detect a publish caller that still uses the original message or body, so an integration assertion is needed. | AC-6 tests now require running the publish entry point with recording git/gh shims on a DCO fixture with a PR template; step-5 wires the helper outputs into the real commit and PR body. |
