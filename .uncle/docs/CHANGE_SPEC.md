# Change spec: issue 155

Omitted sections: Performance (no impact); Migration (no data migration; flag/env deprecation covered in Compatibility); Prototype isolation (not a prototype)

## 1. Change type
Behavior change (default flip) plus flag/env deprecation.

## 2. Problem statement
Unattended is the common case but needs `--unattended` everywhere. Make it the default; the exception gets `--attended`.

## 4. Desired behavior and decisions (open questions resolved)
| Question | Decision |
|---|---|
| Deprecation window | `--unattended`, `UNCLE_UNATTENDED`, `WORKFLOW_UNATTENDED`, `UNCLE_HOUSEKEEPING_UNATTENDED` accepted as no-ops with a one-line stderr notice; release notes state removal no earlier than two releases after this one. Not permanent. |
| Environment | `UNCLE_ATTENDED=1` added. Legacy env honored with notice. Attended always wins on conflict with the env or another flag source, except two contradictory CLI flags, which are refused. |
| Upgrade check | Never prompts when unattended (default): if a newer version exists, print one line naming it and the upgrade command. Prompts only when attended and a TTY is present (today's flow). |
| TUI default | Unattended too (already true via `misc.auto_mode`); mode shown in header; Shift-Tab toggles for the session. `--attended` makes the session start attended. |
| PR text | Behavior unchanged. TUI auto-mode help text corrected to state what actually happens (issue runs publish a PR; other runs do not commit/push). |
| No TTY | Default unattended runs need no TTY. `--attended` without a TTY refuses; scripted answers need explicit `UNCLE_ATTENDED_STDIN=1`. Forgetting the flag is not detectable, and that is accepted. |
| Resume | Mode is recorded in `.uncle/workflow/mode`; a resume reuses it unless a flag/env is given; mode printed on resume. |
| Housekeeping | Same resolver; policy gate unchanged; attended keeps the `[y/N]` prompt. |

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| A-1 | MODIFY | `uncle --application T` / `--issue` / `--change-request` / `--housekeeping`, no mode flag | depends on entry point; direct drivers attended | unattended end to end; banner `Mode: unattended (use --attended to review each gate)`; failing tests still stop | launcher test with fake driver per entry point |
| A-2 | ADD | `--attended` | flag unknown | every gate waits for a person; no TTY -> exit nonzero with message, nothing started | pty test + no-TTY test |
| A-3 | MODIFY | `--unattended` | works silently | works as default; one-line deprecation notice on stderr | launcher + driver tests |
| A-4 | ADD | `--attended` and `--unattended` | n/a | refused naming both; nothing starts | tests per entry point |
| A-5 | MODIFY | interactive `uncle`/TUI no flag | auto on | auto on, mode always visible; toggle switches session to attended | `startup-action-test.py`, TUI tests |
| A-6 | MODIFY | `stagegate.sh`, `from-issue.sh`, `change-workflow.sh`, `housekeeping-workflow.sh` direct | attended default | same default and flags as launcher | resolver parity test |
| A-7 | ADD | `UNCLE_ATTENDED=1`; legacy `UNCLE_UNATTENDED=1` | n/a | former = `--attended`; latter honored with notice; both -> attended | resolver test |
| A-8 | PRESERVE | attestation, PR body, final report of delegated run | states nobody reviewed | byte-identical wording and fields | record test vs current fixtures |
| A-9 | MODIFY | upgrade check | prompts unless `--unattended` | per decision table | `upgrade-test.sh` |
| A-10 | ADD | resume without flag | mode not recorded when attended | mode recorded at start; reused; printed on resume | resume test |
| A-11 | MODIFY | `--help` of `uncle`, drivers; TUI help | names `--unattended` | names `--attended`, documents default and deprecation | help-text assertions |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | any gate satisfied without a person is delegated, ledgered and reported unreviewed | run state, attestation, PR body | approval-gates-*.sh, change-pr.sh | record test + defect injection |
| I-2 | NEW | `--attended` never degrades to unattended; unreachable person -> stop | all entry points | mode.sh + drivers | pty/no-TTY test |
| I-3 | STRENGTHENED | mode resolved once by one shared resolver; every stage/subprocess sees same `UNCLE_UNATTENDED` | launcher, drivers, TUI | scripts/lib/mode.sh | parity test |
| I-4 | EXISTING | unattended safety rules and waiver wording unchanged | all libs | untouched libs | existing suites |
| I-5 | NEW | resumed run keeps its recorded mode unless flag/env given; printed on resume | drivers | mode.sh + `.uncle/workflow/mode` | resume test |
| I-6 | EXISTING | housekeeping policy gate runs before any approval or mode decision and is unaffected | housekeeping | housekeeping-workflow.sh:266 | `housekeeping-workflow-test.sh` |

No RELAXED or REMOVED invariants. The default flip changes which mode is picked, not what either mode records.

## 7. Compatibility
Old flag/envs keep working with a notice. Config `misc.auto_mode` unchanged. Release notes must say scripts that relied on the old default to pause now run through.

## 8. Error behavior
Contradictory flags: exit 1, message names both. `--attended` without TTY (and without `UNCLE_ATTENDED_STDIN=1`): exit 1, never unattended. Notices go to stderr only so stdout parsing is unaffected.

## 10. Security
A person who types the shortest command no longer sees gates; banner and ledger/attestation wording make that visible. No new permissions. Housekeeping allowlist unchanged.

## 12. Rollback
Revert the commit; no persisted format changes beyond the additive `.uncle/workflow/mode` file, which old code ignores.

## 14. Non-goals
Changing unattended semantics or waivers; removing gates; per-gate modes; changing approval record format.

## 15. Assumptions
`UNCLE_ATTENDED_STDIN` is a new test/scripting escape and counts as a person being reachable only because the caller explicitly declares it. Tests that mean attended get `--attended` plus that variable when they pipe answers; test edits are authorized by the Verification section of CHANGE_REQUEST.md.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With no mode flag or env, `uncle --application\|--issue\|--change-request\|--housekeeping` start unattended and print `Mode: unattended (use --attended to review each gate)`. | New launcher test with a fake driver capturing args/env for all four entry points. |
| AC-2 | `--attended` is accepted by `uncle`, `stagegate.sh`, `change-workflow.sh`, `from-issue.sh`, `housekeeping-workflow.sh` and forces human gates; the TUI starts attended. | Resolver parity test plus TUI startup test. |
| AC-3 | `--attended` with no TTY (and without UNCLE_ATTENDED_STDIN=1) refuses with a message and exit nonzero, starts nothing, and never runs unattended. | No-TTY test and a pty test. |
| AC-4 | `--unattended` still works, behaves as the default, and prints a one-line deprecation notice on stderr; combined with `--attended` the run is refused naming both flags. | Launcher and driver tests for each entry point. |
| AC-5 | `UNCLE_ATTENDED=1` equals `--attended`; legacy `UNCLE_UNATTENDED`, `WORKFLOW_UNATTENDED`, `UNCLE_HOUSEKEEPING_UNATTENDED` are honored with a notice; attended wins when both are set. | Resolver matrix test over flag/env combinations, run through every driver. |
| AC-6 | Every driver and the launcher resolve identical modes for identical flags/env, including conflicting combinations, via a single shared resolver `scripts/lib/mode.sh`. | Parity test comparing resolved mode from each entry point. |
| AC-7 | A default (unattended) run produces the same delegated-gate ledger entries, attestation fields and PR body wording as a run that passed `--unattended` before the change. | Record test comparing against existing fixtures in attestation-test.py, pr-auto-publish-test.sh, unattended-test.sh; defect injection: remove a gate's `record_unattended_gate` and confirm failure. |
| AC-8 | A resumed run reuses its recorded mode (`.uncle/workflow/mode`) unless a flag/env is passed, and prints the mode on resume. | Resume test starting attended, resuming without flag, then with flag. |
| AC-9 | Upgrade check never prompts when unattended (prints a one-line notice if newer) and prompts only when attended with a TTY. | scripts/tests/upgrade-test.sh additions. |
| AC-10 | Housekeeping: default unattended skips the approval prompt only after the policy gate has passed; policy refusals behave identically in both modes; attended keeps the prompt. | housekeeping-workflow-test.sh both modes, including a disallowed command. |
| AC-11 | `uncle --help`, driver `--help`, TUI help/auto-mode text, README, QUICK_START, GITHUB_INTEGRATION, docs/quickstart.md describe the new default, `--attended`, and the deprecation; examples no longer need `--unattended`; a migration/release-notes document states the behavior change and removal timeline; TUI auto-mode help text states actual PR behavior. | Grep assertions in a docs test plus manual read. |
| AC-12 | Existing suites pass: tests that meant unattended work under the default; tests that meant attended pass `--attended`; `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` show no new failures versus baseline. | Driver verification commands compared with baseline. |

