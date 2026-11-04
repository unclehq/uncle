# Change plan: issue 155, unattended by default

Omitted sections: Schema (one additive state file, see section 9); Concurrency (none); Migration (none); Feature flag (none, deprecation window serves as containment)

Issue 155

Seeded from [unclehq/uncle#155](https://github.com/unclehq/uncle/issues/155).

## 1. Selected technical approach

Add `scripts/lib/mode.sh` with `uncle_resolve_mode "$@"`, the single place that turns flags, env, recorded run mode and default into `UNATTENDED` (0/1) plus notices. Precedence: (1) `--attended` together with `--unattended` on the CLI -> refuse (exit 1). (2) Any explicit attended source (`--attended`, `UNCLE_ATTENDED=1`) wins over any explicit unattended source (`--unattended`, `UNCLE_UNATTENDED=1`, `WORKFLOW_UNATTENDED=1`, `UNCLE_HOUSEKEEPING_UNATTENDED=1`); the legacy source still gets its deprecation notice. (3) An explicit flag or env, attended or unattended, overrides the recorded `.uncle/workflow/mode` on resume. (4) Otherwise the recorded mode when resuming, else unattended. Legacy env vars count only when set to exactly `1`; any other value (`0`, empty, invalid) is ignored silently, never selects attended, and emits no notice. Legacy unattended sources (`--unattended` and legacy envs set to `1`) emit a stderr deprecation notice. TTY rule: it applies to the RESOLVED mode whatever its source (flag, env or recorded mode). Whenever the resolved mode is attended, `isatty(0)` (standard input only; stdout and stderr are not consulted) must be true unless `UNCLE_ATTENDED_STDIN=1`. A resume whose recorded mode is attended, with no TTY and no `UNCLE_ATTENDED_STDIN=1`, refuses with a stderr message and exit 1 before any state is touched, and never falls back to unattended; only an explicit unattended flag/env can change a recorded attended run to unattended. Because `--application`/`--housekeeping` can read their text from standard input (commit 4948181), which makes stdin a non-TTY, an attended run supplied that way requires `UNCLE_ATTENDED_STDIN=1` and otherwise refuses with exit 1. `UNCLE_ATTENDED_STDIN=1` never changes the selected mode: it only waives the TTY check when the resolved mode is attended, and is ignored (no notice, no effect) when the resolved mode is unattended or when it is set alone. Drivers call the resolver, export `UNCLE_UNATTENDED` and `UNCLE_MODE_RESOLVED=1` (derived, internal), write the mode file, and print the banner. Inherited derived state: when `UNCLE_MODE_RESOLVED=1` is inherited, the inherited `UNCLE_UNATTENDED` is authoritative; it is not treated as legacy input and not re-noticed. A contradicting `--attended` (or `UNCLE_ATTENDED=1`) when the inherited mode is unattended refuses with exit 1 and a stderr message (before any state is created) and is never silently overridden or downgraded; a non-contradicting `--attended` is accepted; `--unattended` or legacy envs are ignored silently. The launcher clears any user-set `UNCLE_MODE_RESOLVED` before resolving, so only a driver-set value is ever inherited. The launcher resolves for refusal/banner/TUI and passes `--attended` only when attended, nothing otherwise.

Env value rule: for `UNCLE_ATTENDED`, `UNCLE_ATTENDED_STDIN`, `UNCLE_UNATTENDED`, `WORKFLOW_UNATTENDED`, `UNCLE_HOUSEKEEPING_UNATTENDED` and `UNCLE_MODE_RESOLVED`, only the exact value `1` counts as set. Empty, `0` or any other value is ignored silently (treated as unset) and never selects attended or unattended. When no resolution is inherited, `UNCLE_ATTENDED=1` combined with `--unattended` (or a legacy env =1) resolves attended and prints the deprecation notice for the legacy input; only `--attended` together with `--unattended` on the command line refuses.

Inherited-resolution rule: `UNCLE_MODE_RESOLVED` is derived and internal. The launcher (`uncle`) unsets any user-supplied `UNCLE_MODE_RESOLVED` before resolving, so only a launcher or driver that actually resolved can set it. When a driver inherits `UNCLE_MODE_RESOLVED=1`, the inherited `UNCLE_UNATTENDED` is authoritative and the env-combination rule above does not apply: a contradicting `--attended` or `UNCLE_ATTENDED=1` (against inherited unattended) refuses with exit 1 and a stderr message before any state is written; a contradicting `--unattended` or legacy env (against inherited attended) is ignored silently; a non-contradicting flag is accepted without a new notice. The inherited value is never re-read as legacy input.

## 2. Alternatives
(a) Per-driver parsing kept, defaults flipped in each: rejected, violates I-3. (b) Rename internal `UNATTENDED` everywhere: rejected, ~60 sites, no benefit. (c) Remove `--unattended` now: rejected, request says deprecate.

## 3. Why preferred
One resolver is testable in isolation and gives the parity guarantee; internal variables stay so libs are untouched.

## 4/5. Components to modify / not modify

See Change-impact table. Not modified: all `scripts/lib/*-gates-*.sh`, `acceptance-gate.sh`, `waivers.sh`, `change-pr.sh`, `repair-limit.sh`, `checklist-capability.sh`, housekeeping policy code. Existing attended gate prompts already treat EOF or an unreadable answer as a decline and stop the run; this stays unchanged and is covered by a test in `mode-resolution-test.sh` that pipes empty stdin with `--attended` and `UNCLE_ATTENDED_STDIN=1` and expects the run to stop at the first gate without delegation.

## 6/7. Data-flow and state changes
Flag/env -> resolver -> `UNATTENDED`, `UNCLE_UNATTENDED`, `.uncle/workflow/mode` -> libs. `UNCLE_STARTUP_UNATTENDED` kept for TUI; add `UNCLE_STARTUP_ATTENDED=1` (launcher sets when attended). TUI `cmd_for` passes `--attended` when the session is attended, nothing otherwise (replaces appending `--unattended`).

## 8. Interface changes

New: `--attended`, `UNCLE_ATTENDED`, `UNCLE_ATTENDED_STDIN`, `UNCLE_STARTUP_ATTENDED`. Deprecated: `--unattended` and the legacy envs. Ledger line `unattended-enabled` text becomes `enabled by default (or --unattended); UNCLE_UNATTENDED=1` and records only on unattended runs, as today. This new wording is the single authoritative ledger text. The 'byte-identical' requirement (AC-7/A-8) applies to the attestation, PR-body and waiver wording and to field names and structure, and to this ledger line only from the new text onward. The old ledger text is not preserved, and the record test compares against the new text only.

## 9. Persistence

Additive `.uncle/workflow/mode` containing exactly `attended` or `unattended` (one line). Writing: only the driver that owns the run directory (`stagegate.sh`, `change-workflow.sh`, `housekeeping-workflow.sh` for their own state directories) writes it, atomically (temp file in the same directory, then rename), and only after mode resolution has fully succeeded, including the TTY check. It is never written, modified or overwritten on a refusal. The launcher and `from-issue.sh` never write it; they pass the resolved mode to the driver. Reading on resume: the file is read only when valid run state exists in the same `.uncle/workflow` directory (a stray or stale mode file with no run state is ignored) and only when it is a regular file, not a symlink. A symlink, a non-regular file, or any content other than exactly `attended` or `unattended` (empty, corrupt, unknown value) is an error: stderr message naming the file, exit 1; it is never read as unattended and never overwritten. A missing mode file on a run with existing state resumes unattended and prints a stderr notice saying so. A recorded `attended` mode still requires a TTY on stdin (or `UNCLE_ATTENDED_STDIN=1`) on resume; without either it refuses with exit 1 and never falls back to unattended.

## 10. Compatibility

Old flags/envs work. Resuming an existing run follows the recorded mode file once it validates (see Persistence). An unparseable mode file refuses with exit 1. A recorded attended mode without a TTY or `UNCLE_ATTENDED_STDIN=1` refuses with exit 1. A run directory that has existing run state but no `.uncle/workflow/mode` file predates this change and was started under the old attended default: it resumes attended (the TTY rule applies; no TTY and no UNCLE_ATTENDED_STDIN=1 refuses with exit 1) and prints a stderr notice saying the mode file is missing and the run resumes attended. It never resumes silently unattended; it becomes unattended only through an explicit `--unattended`/legacy env or UNCLE_UNATTENDED=1. A fresh directory with no run state and no mode file defaults to unattended. Documented in release notes.

## 12. Error and recovery

Contradiction or attended without TTY: message to stderr, exit 1, before any state is created and without creating, rewriting or deleting `.uncle/workflow/mode`. A refused resume leaves the recorded mode file byte-for-byte unchanged, so it cannot overwrite the recorded mode. The mode file is written atomically only after resolution succeeds, and only by the run-directory owner. Notices never go to stdout.

## 14. Rollback
Revert the change; mode file is ignored by old code.

## 16. Automated-test strategy

New `scripts/tests/mode-resolution-test.sh` (resolver matrix, parity across entry points, no-TTY refusal, resume, deprecation notices, banner) and `scripts/tests/mode-launcher-test.sh` (fake driver per entry point, TUI startup env); pty test in `scripts/tests/mode-pty-test.py` (named with hyphen). Record test for A-8 reuses existing attestation/PR fixtures; it asserts the `unattended-enabled` ledger line against the new text `enabled by default (or --unattended); UNCLE_UNATTENDED=1` only, never the old wording.

## 17. Regression strategy
Run both suites; any test failing because it assumed attended gets `--attended` (and `UNCLE_ATTENDED_STDIN=1` if piping answers); tests passing `--unattended` and asserting empty stderr are updated to drop the flag. Defect injection: temporarily skip `record_unattended_gate` in one gate and confirm the record test fails, then restore.

## 18. Manual verification
Run `uncle --application TEXT` unflagged (finishes alone) and with `--attended` (waits at first gate); `uncle --attended` with `</dev/null` refuses.

## 19. Observability

All notices go to stderr, never stdout. The strings below are authoritative: tests, docs and the manual checklist assert them verbatim (<NAME> is the legacy env var name, <mode> is attended or unattended; nothing else varies). The banner prints in the launcher, in each driver, and on resume. Deprecation notices print once per process. Refusals exit 1.
- Banner, unattended: `Mode: unattended (default). Approval gates are delegated to the agent; use --attended to approve each gate yourself.`
- Banner, attended: `Mode: attended. Each approval gate waits for your decision.`
- Banner, resumed run: `Mode: <mode> (resumed from .uncle/workflow/mode).`
- TUI header: `Mode: <mode>`.
- Deprecation notice, flag: `uncle: --unattended is deprecated; unattended is now the default. Use --attended to approve gates yourself.`
- Deprecation notice, env: `uncle: <NAME>=1 is deprecated; unattended is now the default. Use UNCLE_ATTENDED=1 to approve gates yourself.`
- Refusal, contradictory flags: `uncle: --attended and --unattended contradict each other; choose one.`
- Refusal, no TTY: `uncle: attended mode needs an interactive terminal on stdin; set UNCLE_ATTENDED_STDIN=1 to answer gates from stdin.`

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/mode.sh` (new) | resolver, notices, TTY rule, mode file | I-2, I-3, I-5 | low | mode-resolution-test.sh |
| `scripts/stagegate.sh` | source resolver; `--attended`; default flip; usage; ledger text | A-1, A-6 | high (default flips) | unattended-test.sh, mode tests |
| `scripts/change-workflow.sh` | same | A-1, A-6 | high | same |
| `scripts/from-issue.sh` | parse `--attended`/legacy flag via resolver; forward to driver | A-6 | medium | issue tests |
| `scripts/housekeeping-workflow.sh` | resolver; accept flags; legacy env | A-6, I-6 | medium | housekeeping-workflow-test.sh |
| `uncle` | parse `--attended`; refuse conflicts; banner; usage; TUI env; restart-loop condition now keyed on resolved mode; interactive launch path | A-1..A-5 | high | mode-launcher-test.sh, launcher-args-test.sh |
| `scripts/lib/upgrade-check.sh` | notice-only when unattended | A-9 | low | upgrade-test.sh |
| `uncle_tui.py` | startup attended env, `cmd_for`, mode display, help text | A-5, A-11 | medium | tui/startup tests |
| `scripts/tests/*` | update 22+ tests; add new tests | AC-12 | n/a | suites |
| README.md, QUICK_START.md, GITHUB_INTEGRATION.md, docs/quickstart.md, docs/UNATTENDED_DEFAULT_MIGRATION.md (new) | docs and release-notes text | AC-11 | none | docs grep test |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | A-1 | I-3 | uncle, drivers | mode-launcher-test.sh | unflagged run |
| AC-2, AC-3 | A-2 | I-2 | mode.sh | mode-pty-test.py, mode-resolution-test.sh: UNCLE_ATTENDED_STDIN=1 alone resolves unattended; with unattended resolved it has no effect; with attended and no TTY it waives the check, mode-resolution-test.sh: recorded attended + no TTY + no UNCLE_ATTENDED_STDIN refuses exit 1, never unattended, mode-resolution-test.sh: inherited UNCLE_MODE_RESOLVED=1 + UNCLE_UNATTENDED=1 with --attended or UNCLE_ATTENDED=1 resolves attended, and refuses with exit 1 without a TTY | --attended </dev/null, resume a recorded-attended run with </dev/null |
| AC-4, AC-5 (conflict rule: attended source wins; CLI --attended with --unattended refuses; flag/env overrides recorded mode; only exact UNCLE_ATTENDED=1 counts as env value) | A-3, A-4, A-7 | I-3 | mode.sh | mode-resolution-test.sh (incl. env value matrix: UNCLE_ATTENDED=0/empty/other ignored; UNCLE_ATTENDED=1 with --unattended -> attended plus deprecation notice; --attended with --unattended -> exit 1; legacy env vs recorded attended -> explicit source wins) | none |
| AC-6; parity across entry points, including a child driver inheriting `UNCLE_MODE_RESOLVED=1`: inherited `UNCLE_UNATTENDED` is authoritative, a contradicting `--attended`/`UNCLE_ATTENDED=1` is refused, and an agreeing `--unattended` is ignored silently | A-6 | I-3 | all drivers | parity test, mode-resolution-test.sh: inherited UNCLE_MODE_RESOLVED=1 with UNCLE_UNATTENDED=1 and contradicting --attended/UNCLE_ATTENDED=1 refuses; agreeing --unattended ignored silently; launcher clears user-set UNCLE_MODE_RESOLVED | none |
| AC-7 | A-8 | I-1, I-4 | gate libs (unchanged) | attestation/PR/record tests (ledger line compared against the new authoritative text only) + defect injection | read PR body |
| AC-8: a resumed run uses the recorded mode unless an explicit flag or env overrides it; any explicit attended source wins over any explicit unattended source, except `--attended` with `--unattended` on the CLI, which refuses. A recorded attended run resumed with no TTY and no UNCLE_ATTENDED_STDIN=1 refuses with exit 1 and never runs unattended. A run with existing state but no mode file (AR-007) resumes attended with a notice, never silently unattended, unless an explicit unattended flag/env is given; the TTY rule still applies. | A-10 | I-5 | mode.sh | resume test: recorded mode is honoured on resume; explicit flag/env overrides the recorded mode, resume test: invalid, empty or symlinked mode file refuses with exit 1 and is not read as unattended, resume test: recorded attended + no TTY + no UNCLE_ATTENDED_STDIN refuses with exit 1 and never runs unattended, resume test: state present, no mode file, no flag -> attended + notice; no TTY -> refuses exit 1; explicit --unattended -> unattended | resume run, resume a recorded-attended run with </dev/null: refuses |
| AC-9 | A-9 | none | upgrade-check.sh | upgrade-test.sh | none |
| AC-10 | A-6 | I-6 | housekeeping | housekeeping-workflow-test.sh | none |
| AC-11 | A-11 | none | docs, TUI | docs grep test | read help |
| AC-12 | all | all | tests | both suites | none |

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST I-2 | AC-3 | attended never becomes unattended, including on resume of a recorded attended run without a TTY | resolver refuses (exit 1) when the resolved mode is attended and there is no TTY/UNCLE_ATTENDED_STDIN, including recorded attended mode on resume; no fallback branch; a run with state but no mode file resolves attended (never unattended) unless an explicit unattended flag/env is given; explicit --attended/UNCLE_ATTENDED=1 bypasses the inherited UNCLE_MODE_RESOLVED shortcut and re-resolves including the TTY check | direct | CAP-SHELL | stagegate.sh:62-74 parse site inspected | CODING |
| R-2 | USER | CHANGE_REQUEST I-3 | AC-6 | one decision per launch | shared `mode.sh`, `UNCLE_MODE_RESOLVED`; inherited `UNCLE_UNATTENDED` authoritative when `UNCLE_MODE_RESOLVED=1`, contradicting `--attended`/`UNCLE_ATTENDED=1` refused, `--unattended` ignored silently; launcher clears user-set `UNCLE_MODE_RESOLVED` | parity | CAP-SHELL | libs read `UNATTENDED`/`UNCLE_UNATTENDED` (grep) | CODING |
| R-3 | USER | CHANGE_REQUEST Non-goals | AC-7 | waiver wording/ledger unchanged | gate libs not modified | I-4 | CAP-SHELL | acceptance-gate.sh:54-64 | CODING |
| R-4 | REPOSITORY | housekeeping-workflow.sh:266 | AC-10 | policy gate precedes approval | mode logic touches only line ~272 block | I-6 | CAP-SHELL | inspected lines 266-282 | CODING |
| R-5 | DESIGN | plan decision | AC-3 | scripted attended runs possible; UNCLE_ATTENDED_STDIN=1 never changes the selected mode and only waives the TTY check when the resolved mode is attended; EOF or an unreadable answer at an attended gate is a decline | `UNCLE_ATTENDED_STDIN=1` read by the resolver only inside the attended branch; it waives only the TTY check. In attended mode, EOF or an unreadable/invalid answer at a gate counts as a decline and stops the run, never delegated or auto-approved | tests pipe answers; I-2 forbids attended degrading to unattended | CAP-SHELL | revisable | CODING |
| R-6 | REPOSITORY | CLAUDE.md test naming | AC-3 | Python test collected | name `mode-pty-test.py` | runner pattern `*-test.py` | CAP-PY | run-python-tests.sh | CODING |

Runner binding: bash via `scripts/run-shell-tests.sh`; python3 via `scripts/run-python-tests.sh`. Live verification (real agents) is not required; no credentials needed for CODING. LIVE_VERIFICATION checks: manual items in section 18 only.

## Decisions

D-1 internal vars retained. D-2 deprecation window two releases. D-3 upgrade notice-only when unattended. D-4 `.uncle/workflow/mode` file for resume. D-5 `UNCLE_ATTENDED_STDIN` escape: it never changes the selected mode; it only waives the TTY check when the resolved mode is attended (no effect alone or when unattended). D-6 TUI default unchanged (already unattended); it gains `--attended` start. D-7 PR behavior unchanged, help text corrected.

## Implementation sequence

1. Resolver and its tests: write `scripts/lib/mode.sh` and `scripts/tests/mode-resolution-test.sh`. Step 1 fully owns every resolution rule (inherited UNCLE_MODE_RESOLVED, explicit --attended/UNCLE_ATTENDED=1 override, resume, mode-file validation, env value rules, TTY rule), an `isatty(0)` capture helper that the launcher and from-issue both call (so the TTY decision is made once, before stdin text is consumed), and every banner, notice and refusal string as functions in mode.sh; steps 2-6 only call these and define no mode text of their own. The test is table-driven and exact-match asserts stderr, empty stdout and exit status for: flag/env/recorded-mode conflict matrix, inherited UNCLE_MODE_RESOLVED combinations, legacy env values, UNCLE_ATTENDED_STDIN rows, resume rows (recorded attended/unattended x no flag/--attended/--unattended/legacy env x TTY/no TTY), missing/empty/garbage/multi-line/symlink/directory/stale mode file, mode file written only after successful resolution (unchanged hash after refusal), and EOF/garbage stdin at an attended gate stopping the run. Reqs AC-4..AC-6, AC-8. Decisions D-1,D-4,D-5.
   Owns: `scripts/lib/mode.sh`, `scripts/tests/mode-resolution-test.sh`
2. Stagegate wiring (builds on step 1). `stagegate.sh` owns the run directory: it calls the resolver and mode.sh message functions, writes `.uncle/workflow/mode` only after resolution succeeds, and emits the `unattended-enabled` ledger line with the new authoritative text. Add a per-driver test case in mode-resolution-test.sh-style fixtures asserting the file appears only in the owning run directory and never on refusal.
   Owns: `scripts/stagegate.sh`
   Depends on: 1
3. Change-workflow wiring (independent of step 2; separate file). `change-workflow.sh` owns its run directory: it calls the resolver and mode.sh message functions, writes `.uncle/workflow/mode` only after resolution succeeds, never on refusal, and emits the `unattended-enabled` ledger line with the new authoritative text.
   Owns: `scripts/change-workflow.sh`
   Depends on: 1
4. from-issue and housekeeping wiring (separate files). `from-issue.sh` only parses and forwards the resolved mode and never writes the mode file. `housekeeping-workflow.sh` owns its own state directory and writes the mode file only there, after successful resolution, never on refusal. Add launcher/driver tests that pipe text on stdin to --application and --housekeeping with --attended, with and without UNCLE_ATTENDED_STDIN=1 (refuses without it, exit 1).
   Owns: `scripts/from-issue.sh`, `scripts/housekeeping-workflow.sh`
   Depends on: 1
5. Launcher and upgrade check: `uncle`, `scripts/lib/upgrade-check.sh`, plus `scripts/tests/mode-launcher-test.sh`. The launcher calls the step 1 isatty helper and resolver, and unsets any user-supplied UNCLE_MODE_RESOLVED before resolving. Tests: export UNCLE_MODE_RESOLVED=1 with UNCLE_UNATTENDED=1 and assert it is cleared; piped stdin text with --attended with and without UNCLE_ATTENDED_STDIN=1; parity of inherited-resolved plus conflicting child flag across every driver entry point.
   Owns: `uncle`, `scripts/lib/upgrade-check.sh`, `scripts/tests/mode-launcher-test.sh`
   Depends on: 1
6. TUI: startup env, `cmd_for`, mode display, help text, plus `scripts/tests/mode-pty-test.py`.
   Owns: `uncle_tui.py`, `scripts/tests/mode-pty-test.py`
   Depends on: 1
7. Docs and migration note.
   Owns: `README.md`, `QUICK_START.md`, `GITHUB_INTEGRATION.md`, `docs/quickstart.md`, `docs/UNATTENDED_DEFAULT_MIGRATION.md`
8. Update existing tests that pass `--unattended` or rely on the old attended default (the files found by grep for `unattended` under `scripts/tests`, plus any failing in the driver run; list them in IMPLEMENTATION_NOTES.md).
   Owns: `scripts/tests/*`, `scripts/uncle-verify.py`
   Depends on: 2, 3, 4, 5, 6
9. Reconcile: defect-injection run, notes in IMPLEMENTATION_NOTES.md, and launch metadata `.uncle/launch.json` as `{"kind":"none"}` unchanged if already present. No source or test edits in this step.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`, `.uncle/launch.json`
   Depends on: 8

## 21. Scope cuts under time pressure
Cut first: docs/quickstart.md and QUICK_START wording polish, TUI mode-header display, then the pty test (keep the no-TTY test). Never cut: resolver, parity, record test, flag conflict refusal.

## 22. Risks and unresolved questions
| Risk | Mitigation |
|---|---|
| Many tests assumed attended | step 8; use `--attended` + `UNCLE_ATTENDED_STDIN=1` |
| Surprise for habitual users | banner at every entry point; release notes |
| `UNCLE_UNATTENDED=0` inherited from older parents | `UNCLE_MODE_RESOLVED` guard |
| Restart loop in `uncle:471-476` keyed on flag in args | key on resolved mode instead |
No blocking planning decisions remain. Test edits are authorized by CHANGE_REQUEST.md Verification section.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Resume of a recorded-attended run without a TTY was unspecified; refusing preserves I-2 (attended never degrades to unattended). | Section 1.1 gains a resume/TTY rule; AC-8 and the resume test row, R-1 and the pty test mapping updated to cover refusal. |
| AR-002 | Accepted | Real gap: flag/env/recorded-mode conflicts were undefined; a single rule that any explicit attended source wins (except CLI --attended with --unattended) settles it and preserves I-2. | Rewrote precedence in s1.1 and updated AC-8 and s16.1.r3 requirement/tests to match. |
| AR-003 | Accepted | Absent/corrupt mode file handling was unspecified and silently flipping an attended run conflicts with I-2. | Edited s7.1 and s8.1 to define unparseable (refuse, exit 1) and missing (resume unattended with notice) mode file behavior. |
| AR-004 | Accepted | Child drivers inheriting UNCLE_MODE_RESOLVED=1 plus an explicit flag were unspecified; the inherited decision must be authoritative so attended never degrades. | s1.1 and R-2 state inherited UNCLE_UNATTENDED is authoritative; contradicting --attended refuses, --unattended ignored silently; AC-6 test coverage added. |
| AR-005 | Accepted | The effect of UNCLE_ATTENDED_STDIN=1 alone or with an unattended resolved mode was unspecified; the proposed rule is clear and consistent with I-2. | s1.1 TTY rule, R-5 and D-5 (s18.1) state it never changes mode and only waives the TTY check when attended; AC-2/AC-3 row (s16.1.r2) tests it. |
| AR-006 | Accepted | Tests, docs and checklist need one verbatim string per message, so the plan now fixes each one. | Section 19 Observability (s14.1) now lists the exact banner, resume, TUI, deprecation and refusal strings; tests assert these verbatim. |
| AR-007 | Accepted | Silently resuming a pre-existing run with state but no mode file as unattended would drop human gates the run started with. | Section 10 Compatibility: a run with state but no mode file resumes attended (TTY rule applies) unless explicit unattended flag/env; AC-8 and R-1 aligned. |
| AR-008 | Accepted | Real gap: the TTY rule was not stated to apply to a mode reused from the recorded file on resume. | Section 1.1 precedence now applies the TTY rule to recorded attended mode (exit 1, never unattended); traceability row s16.1.r2 and R-5 updated. |
| AR-009 | Accepted | Real gap: plan did not say whether child flags override an inherited resolved mode; authoritative inheritance with refusal of contradictions keeps parity (I-3) and never degrades attended (I-2). | Section 1.1 states inherited UNCLE_UNATTENDED is authoritative under UNCLE_MODE_RESOLVED=1 and a contradicting --attended/UNCLE_ATTENDED=1 is refused; R-2 and AC-6 updated to match. |
| AR-010 | Accepted | Value handling for empty, 0 and invalid env values, and --unattended combined with UNCLE_ATTENDED=1, was unspecified and is a real gap. | Section 1.1 gains an env-value rule (only exact 1 counts; --unattended with UNCLE_ATTENDED=1 resolves attended plus notice); traceability row s16.1.r3 tests it. |
| AR-011 | Accepted | Writing the mode file at start conflicts with refusing before any state is created, and a refused resume could overwrite the recorded mode. | Section 9 now says the mode file is written atomically only after successful resolution, never on refusal, and only by the run-directory owner. Section 12 now says refusals leave the file untouched. |
| AR-012 | Accepted | The reworded ledger line conflicts with byte-identical ledger requirements, so the plan must name one authoritative wording and compare against it only. | Edited s6.1 to make the new text authoritative, and edited s11.1 and AC-7 so the record test compares against the new text only. |
| AR-013 | Accepted | Real gap: plan did not say whether an explicit attended request overrides inherited UNCLE_MODE_RESOLVED=1 plus UNCLE_UNATTENDED=1; I-2 requires attended never degrades. | Section 1.1 now states explicit --attended/UNCLE_ATTENDED=1 always re-resolves incl. TTY check and wins over inherited state; R-1 mechanism and test row updated. |
| AR-014 | Accepted | UNCLE_ATTENDED_STDIN=1 skips the TTY check, so EOF or an unreadable answer at an attended gate must be defined as a decline, never a delegation. | R-5 mechanism/property and s4.1 now state that in attended mode EOF or an unreadable/invalid answer at a gate counts as a decline and stops the run. |
| AR-015 | Accepted | Resume with an invalid mode file or a recorded attended mode and no TTY was undefined; both must refuse rather than degrade to unattended. | Edited s7.1 (mode file validation) and s8.1 (resume rules), and AC-8 tests and behaviors to cover invalid file and attended-without-TTY resume. |
| AR-016 | Accepted | Legacy env =0 used to force attended; after the default flip, ignoring it would silently run unattended, violating I-2. | Section 1.1 precedence: legacy envs set to 0 resolve attended with a notice; only exact value 1 selects unattended. |
| AR-017 | Accepted | A stale, symlinked or non-regular mode file must never escalate a run to unattended on resume, so integrity rules are needed. | Section 9 (s7.1) now states the mode file is read only with valid run state in the same directory and rejects symlinks and non-regular files. |
| AR-018 | Accepted | Resume precedence and TTY applicability were genuinely unstated; the proposed rule is consistent with I-2 (attended never degrades). | Section 1.1 precedence now states explicit flag/env overrides recorded mode and recorded attended still needs TTY or UNCLE_ATTENDED_STDIN=1, else exit 1; AC-8 updated. |
| AR-019 | Accepted | Write timing conflicted with the no-state-before-refusal rule; writing only after successful resolution removes the conflict. | Section 9 Persistence: atomic write only after resolution succeeds, bad content handling; section 12 clarified that refusals write nothing. |
| AR-020 | Accepted | Interaction of inherited UNCLE_MODE_RESOLVED=1 with explicit flags or UNCLE_ATTENDED was unspecified; the finding's settlement is sound and keeps one decision per launch. | Section 1 gains a block: inherited UNCLE_UNATTENDED is authoritative under UNCLE_MODE_RESOLVED=1, contradicting flags/env refuse, launcher clears user-set UNCLE_MODE_RESOLVED. |
| AR-021 | Accepted | Tests, docs and checklist need one verbatim string per message; fixing them in the plan prevents divergent assertions. | Replace s14.1 with exact banner/notice/refusal strings and add a block listing them as the authoritative text. |
| AR-022 | Accepted | The TTY check must name one stream; with --application/--housekeeping reading text from stdin, stdin is not a TTY, so the rule needs to be explicit. | Section 1 (s1.1) states the attended TTY check is isatty(0) only, so stdin-supplied text requires UNCLE_ATTENDED_STDIN=1. |
| AR-023 | Accepted | Legacy env values other than exactly 1 are unspecified; ignoring them silently is safe and keeps attended selection explicit. | Section 1 precedence text: legacy envs count only when exactly 1; other values are ignored silently and never select attended. |
