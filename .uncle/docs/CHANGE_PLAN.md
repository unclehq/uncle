# Change Plan: Housekeeping capability

Omitted sections: Schema or persistence (one new optional config key, covered in section 8); Migration (none); Concurrency (reuses driver.lock, no new concurrency); Feature flag (new flag is opt-in by construction)

Issue 148

Seeded from [unclehq/uncle#148](https://github.com/unclehq/uncle/issues/148).

## 1. Selected technical approach

- Pure-Python policy library `scripts/lib/housekeeping_policy.py`: tokenizes each command with a strict shlex-style reader (no shell), rejects unreadable constructs, matches against (a) disallow patterns, (b) allowlist operation shapes. Allowlist matching is exact on the full argv: program, subcommand(s), a fixed per-shape flag set, and exact positional arity. Any global option (e.g. `git -c`, `git -C`, `gh --repo`/`-R`), unlisted flag, `--` separator, env-assignment token (`NAME=value`) or extra/missing positional refuses the command. The operation is derived from argv alone: the policy classifies each argv against the allowlist shapes and ignores the model's `op` label for authorization; it refuses the plan if argv matches no allowlist shape, or if the model's `op` label disagrees with the operation derived from argv. One public function `check_plan(plan, disallow)` returns allow or a refusal naming rule and command.
- Config module `scripts/lib/housekeeping_config.py`: load/validate/add/edit/remove/reset disallow patterns in `.uncle/config` key `housekeeping.disallow` (JSON array string); merges the locked built-in floor; corrupt or missing falls back to defaults. Every config write changes only the `housekeeping.disallow` entry and leaves all other keys (and their order, comments and values) unchanged; tests assert this with a multi-key config. CLI subcommands used by the line menu; imported by the TUI.
- Input validator `scripts/lib/housekeeping_input.py`: same limits as change_request_stdin.py, without the CHANGE_REQUEST.md-exists check; also accepts argument text.
- Driver `scripts/housekeeping-workflow.sh`: sources shared libs only for helper functions (stage-config.sh, lock helper; state.sh functions are used only against the housekeeping directory). It reads and writes no state or gate files outside `.uncle/workflow/housekeeping/` (the only shared path touched is the `driver.lock` lock itself), and releases driver.lock on every exit path (success, REFUSED, DECLINED, FAILED, signal/trap). Stages: plan (model emits JSON ops: id, op label, argv, expected, verify argv + expect; the `op` label is advisory: the policy derives the operation from argv and refuses the plan on no match or on disagreement with the label, never trusting the label) -> policy -> approval -> execute (argv, no shell, stop at first failure, log command+exit) -> verify -> report. Verify argv comes from a fixed per-op template in the driver (read-only, also policy-checked); a model-supplied verify argv must equal the template for that op or the plan is refused, and `expected` is compared to the verify output by exact string. Integrity binding: after policy passes, the driver canonicalizes the checked plan (sorted-key JSON, argv arrays) and writes it to `.uncle/workflow/housekeeping/plan.checked.json` with its SHA-256; the approval prompt and record show that hash, and execution reads only that file after re-hashing it and refusing to run (nothing executes, exit 1) if the hash differs from the approved one. The model's raw output is never re-read after policy. Displayed argv (approval prompt, logs, report) is rendered with control characters, escape sequences and non-printable or newline characters escaped (e.g. `\x1b`, `\n`) so the display cannot hide or forge a command. Records under `.uncle/workflow/housekeeping/`.
- Launcher: `--housekeeping` flag, startup action `housekeeping`. TUI: `/housekeeping` and startup action handler launching the driver the same way other actions do.

Ownership and protection rules (AR-007, AR-010, AR-011): `.uncle/config` is a runtime data file edited only through `housekeeping_config.py`; any existing config helper is imported read-only and never edited. Shared libs (state.sh, stage-config.sh, the lock helper) are sourced read-only and never edited. Existing tests, fixtures and expected strings are protected verification paths; no step owns them, so a failing existing assertion stops the run for human re-approval. This supersedes any wording elsewhere that permits editing existing tests.

## 2. Alternatives considered
| Alternative | Rejected because |
|---|---|
| Policy in bash | substring/regex fragility; issue demands word parsing |
| Add a mode to change-workflow.sh | 4977-line file, code-pipeline assumptions; issue forbids copying plumbing |
| Execute via `bash -c` | defeats parser guarantee |

## 3. Why preferred
Smallest surface: new files plus additive hunks; policy is pure and unit-testable; single enforcement function satisfies I-1/I-2.

## 4. Decisions (settled in-scope)

| ID | Decision | Reason |
|---|---|---|
| D-1 | Two distinct lists. (a) Locked floor, hard-coded in housekeeping_policy.py, always applies, never read from or editable via config, shown locked in the list. Matching is on tokenized argv, any flag order, short flag clusters expanded, --flag=value matched by name. Floor entries: (1) `gh repo delete` and `gh repo archive`; (2) `sudo`; (3) `rm` with any recursive or force flag spelling (`-r`, `-R`, `-f`, `-rf`, `-fr`, `--recursive`, `--force`) when any target is `/`, `/*`, `~`, `~/`, `~/*`, `$HOME` or `${HOME}`; (4) `git push` with force semantics (`--force`, `-f`, `--force-with-lease`, `--force-with-lease=...`, or a `+refspec`) targeting the default branch, where default branch means `main`, `master`, or the branch origin HEAD points to. (b) Default editable disallow list = the change-request's disallow lists verbatim, seeded into `housekeeping.disallow` when absent or corrupt. The effective list is floor + editable list; the editable list can only add refusals. Wrapper programs (`env`, `xargs`, `sh`, `bash`, `zsh`, `eval`, `nohup`, `command`, `exec`, `time`, `nice`, `timeout`, `watch`, `su`, `doas`) are handled per D-2, not by this floor. | Resolves spec s15 UNRESOLVED (AR-002, AR-014, AR-019): floor is exactly this list and always applies, floor variants are enumerated, and the default list is verbatim from the change request, giving AC-7 and I-7 tests a fixed oracle. Wrapper handling is delegated to D-2. Open question resolved: yes. |
| D-2 | Allowlist ops: repo-rename, worktree-prune/remove, branch-delete-merged (local `git branch -d`; remote only as exactly `git push origin --delete <branch>`, subject to D-7 remote protections), label-cleanup, issue-triage. issue-triage allows only fixed shapes on one explicit issue number in the current repo: `gh issue edit N --add-label L` / `--remove-label L`, `gh issue close N [--reason R]`, `gh issue comment N --body T`; any other gh issue form is refused. `rm` and wrapper programs (env, xargs, sh -c, etc.) are never allowlisted; `--force-with-lease` and `+refspec` count as force everywhere. | request list; each has a verify template; AR-014 requires no rm or wrappers in the allowlist; issue-triage shapes fixed per AR-017; remote-delete rules per D-7. |
| D-3 | Records in `.uncle/workflow/housekeeping/`, untracked | request suggestion |
| D-4 | Plan stage stage-config key `housekeeping-plan`; verify is deterministic: verify argv comes from a fixed per-op template, model-supplied verify argv must equal it, and `expected` is compared by exact string | avoids model dependence in the safety path |
| D-5 | Config value is a JSON array stored under the `housekeeping.disallow` key; pattern grammar `program [subcommand...] [--flag...]`; an invalid pattern is one that does not parse under this grammar. Empty, whitespace-only, or bare `*` patterns are rejected. Matching semantics: a pattern matches a command when its program and subcommand tokens are a prefix of the command's tokens and every pattern flag appears among the command's flags in any order and any position (including before the subcommand); short-flag clusters (`-rf`) are expanded to single flags, long `--flag=value` is matched by name only, and extra command flags do not prevent a match. Config is add-only: user patterns only add refusals and can never permit a command outside the allowlist or override the locked floor; the floor is hard-coded in the policy module and never read from or written to config. Edge rules: a zero-op plan is refused by check_plan; adding a duplicate pattern or one equal to a locked-floor pattern is rejected and leaves the stored list unchanged. Config writes change only the `housekeeping.disallow` entry and leave all other `.uncle/config` keys unchanged. | one syntax and one matching rule shared by TUI, line menu and policy library; gives AC-7 flag-order/quoting variants and AC-12 invalid-pattern tests a defined oracle; add-only config keeps I-4/I-7 intact and edge rules make them testable; shared config file must not be disturbed (AR-006, AR-011, AR-016) |
| D-6 | Commands run as argv without shell; plan-supplied verify commands must be on a read-only verify allowlist (`gh repo view`, `git worktree list`, `git branch --list`, `git ls-remote`, `gh label list`, `gh issue view`), must also pass the disallow patterns and locked floor, and must be scoped to the operation: the same repo (no URL or `--repo` pointing elsewhere; `git ls-remote` only against the configured `origin` remote), the same refs/branches/labels/worktree paths, and the same issue number as the op it verifies. A verify argv off the read-only verify allowlist, matching a disallow pattern, or targeting any other repo, URL, ref or issue refuses the whole plan before any command runs, in every mode (attended and unattended); it is never downgraded to NOT_VERIFIED. | I-3 / safety; verify commands are executed, so they get the same policy as operation commands (AR-018), and scoping per AR-017 |
| D-7 | Branch delete: local `git branch -d` (merged-only) allowed; `-D` disallowed. Remote `git push origin --delete <branch>` is refused when <branch> is the default branch (main, master, or the origin HEAD target), the current HEAD branch, or the literal `HEAD`. Colon-form and refspec deletes (`:<ref>`, `+`/`src:dst` refspecs) are refused outright. Every remote delete requires a merged check at execute time (branch tip must be an ancestor of origin's default branch, via read-only `git merge-base --is-ancestor`); if the branch is not merged or the check cannot run, that op fails without deleting. | request; AR-013: protects default branch and enforces merged-only for remotes |

## 5. Components not to modify
`scripts/change-workflow.sh`, `workflow.sh`, `from-issue.sh`, `scripts/lib/change_request_stdin.py`, gate/state libs (sourced only), existing tests.

## 6. Data-flow changes
stdin/arg -> input validator -> private temp file -> `UNCLE_STARTUP_TEXT_FILE` -> TUI/driver -> plan JSON -> policy -> approval -> execute log -> verify -> report.

## 7. State-transition changes

New driver state file `.uncle/workflow/housekeeping/state`: PLANNED -> REFUSED | DECLINED | APPROVED(attended|unattended) -> EXECUTED | FAILED -> VERIFIED | VERIFY_FAILED | NOT_VERIFIED -> REPORTED. Existing drivers' state and gate files are neither read nor written; housekeeping touches nothing under `.uncle/workflow/` outside `housekeeping/` except the shared driver.lock, which is released on every exit path. Tests assert this. Plan schema rule (checked before policy and approval): a plan that is invalid JSON, has zero ops, has duplicate op ids, or has any op missing id, op, argv, expected or verify is REFUSED with exit 1 before approval; nothing executes. After FAILED (stop at first failing command), the read-only verify step still runs for every op that executed, and each op never executed is recorded NOT_VERIFIED (never VERIFIED). Process exit status: 0 only for DECLINED or a run whose ops are all VERIFIED; 1 for REFUSED, FAILED, VERIFY_FAILED, and any NOT_VERIFIED op.

## 8. Interface changes

- CLI `--housekeeping [TEXT]`; usage and did-you-mean updated; exclusivity message extended. Exit status: 0 for DECLINED or fully VERIFIED success; nonzero (1) for input refusal, REFUSED, FAILED, VERIFY_FAILED, or NOT_VERIFIED.
- TUI `/housekeeping TEXT`; startup action `housekeeping`.
- Config key `housekeeping.disallow` (optional).
- Exit status of `--housekeeping`: 0 only for DECLINED or fully VERIFIED runs; 1 for input refusal, REFUSED, FAILED, VERIFY_FAILED, or any NOT_VERIFIED op. The report states per-op verification status after a failure.

## 10. Compatibility strategy

All hunks additive. The new Configure entry takes the last number in each menu (line menu and TUI) and no existing item moves or is renumbered; existing option order and numbering are preserved (new Configure entry appended after existing Miscellaneous items). Existing tests, fixtures and expected strings are never edited. Usage, help and did-you-mean changes must pass every existing assertion unchanged. If an existing assertion cannot pass without editing a protected test, implementation stops and the change returns for human re-approval; no test edit is made in the meantime.

## 12. Error and recovery
Refusal, failure, decline and verify mismatch per spec section 8. Rerun is a new run; no resume of partially executed plans (report says what changed).

## 14. Rollback plan
Revert the commit: removes new files and additive hunks in `uncle`/`uncle_tui.py`. Config key is optional and ignored by older versions. Completed housekeeping operations are not reverted.

## 16. Automated-test strategy

| Test | Covers |
|---|---|
| `scripts/tests/housekeeping-policy-test.py` | parser, every disallow pattern, variants, unreadable, allowlist shapes, config module, floor |
| `scripts/tests/housekeeping-input-test.py` | AC-1/2 validator |
| `scripts/tests/housekeeping-workflow-test.sh` | driver with stub gh/git/agent: approve, decline, unattended, refusal, mid-run failure, verify mismatch, lock, tracked-tree unchanged, defect injection |
| `scripts/tests/housekeeping-launcher-test.sh` | flags, exclusivity, usage, did-you-mean |
| `scripts/tests/tui-housekeeping-test.py` | slash, startup action, config edit persistence |

- Policy tests (S-1): op label disagreeing with argv-derived shape refused; argv matching no shape refused; default list equals change-request lists verbatim and floor equals exactly D-1 and always applies, even with corrupt or edited config; remote delete refused for default branch, HEAD, main, master and colon/refspec forms; rm flag spellings and targets, env/xargs/sh -c wrappers, --force-with-lease and +refspec refused; negative tests for each global option, unlisted flag, env-assignment token and wrong positional arity; verify argv for another repo, ref or URL refused; issue-triage shapes outside fixed label/close/comment forms refused; table-driven pattern tests for short-flag clusters, --flag=value, flag order and flags before subcommand; zero-op plan, duplicate and floor-equal patterns, empty and bare `*` patterns rejected; config write with several existing keys changes only housekeeping.disallow.
- Workflow tests (S-3): plan with invalid JSON, zero ops, duplicate ids or any op missing id/op/argv/expected/verify REFUSED exit 1 before approval; model verify argv differing from template refused and `expected` compared by exact string; mutating or disallowed verify argv refuses whole plan with zero commands executed in attended and unattended modes; exit-code oracle table per terminal state (0 only for DECLINED or fully VERIFIED); completed ops verified after a failure and unexecuted ops NOT_VERIFIED; mutating plan.checked.json between approval and execute is refused; control characters in argv escaped in display; remote delete of an unmerged branch fails the execute-time merged check using stubs; .uncle/workflow outside housekeeping/ snapshot unchanged and driver.lock released on every exit path.
- Launcher and TUI tests (S-4, S-5): other flag combinations keep prior behavior; bare `--housekeeping` with TTY stdin refused as empty input; new entry holds the last number in its own menu and every existing item keeps its number.

Fixture git uses signing disabled flags per project rules.

AC-13 mechanism (in housekeeping-workflow-test.sh): the driver executes plan commands only through one bash function (`hk_run_checked`) that takes the check_plan output as its only input and refuses to run anything without an allow result. Static test: grep the driver source and assert that function holds the sole command-execution call site for plan argv (no other expansion of plan argv, eval, or bash -c of plan data) and is reached only after check_plan. Mutation test: copy the driver to a temp dir, delete the check_plan call (or force it to allow), run the refusal cases against the mutant, and expect them to fail (the refused command executes in the stub); the suite fails if the mutant passes.

## 17. Regression-test strategy

Full existing shell and Python suites via the baseline commands, run against unmodified existing tests and compared with baseline (AC-14). A hash/inventory comparison of existing test files before and after the change must show no edits.

## 18. Manual-verification strategy
Scratch repo rename attended and unattended (AC-15); view the TUI disallow list screen.

## 19. Observability
Run record: command, exit status, timing, mode (attended/unattended/no-approval note), refusal rule; report file `.uncle/workflow/housekeeping/REPORT.md`.

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Phase | Binding / feasibility evidence |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST.md Allowlist/Matching | I-1, AC-7, AC-8, AC-9, D-7: unit tests refuse remote delete of default branch, HEAD, and colon/refspec forms | word-based matching with D-5 semantics (prefix program/subcommands, clusters expanded, --flag=value by name, any flag order), unreadable refused; operation derived from argv alone, op label mismatch or no allowlist shape match refused; floor oracle per D-1 (default branch = main, master, origin HEAD; rm recursive/force in any spelling on /, /*, ~, $HOME refused) | Python tokenizer, no shell; allowlist shapes matched on full argv (program, subcommand, fixed flag set, exact positional arity) with the operation derived from argv alone and the op label only cross-checked; global options, unlisted flags, `--` and env-assignment tokens refused | testable pure code | CAP-python3 | CODING | python3 used by uncle:133 launcher; observed |
| R-2 | USER | CHANGE_REQUEST.md Unattended | I-2, AC-6 | policy runs in every mode | one call site, no mode branch | I-2 | CAP-python3 | CODING | same |
| R-3 | USER | CHANGE_REQUEST.md CLI | AC-1 | same stdin limits as change-request | housekeeping_input.py mirrors change_request_stdin.py:14-35 | reuse constants | CAP-python3 | CODING | inspected lines 14-35 |
| R-4 | REPOSITORY | uncle:233 driver.lock | I-8, AC-11, I-6 | one driver per checkout; lock never leaked | reuse lock helper used by drivers; acquire before any housekeeping write and release via trap on every exit path, including refusal | no new lock | CAP-flock | CODING | uncle:233 comment; exact helper inspected at implementation, DESIGN-revisable |
| R-5 | USER | CHANGE_REQUEST.md I-6 | I-6 | no tracked file edits | records under .uncle/workflow/ | issue text | none | CODING | .gitignore status shows .uncle handling; test asserts |
| R-6 | DESIGN | D-6 | I-3, AC-10 | verify cannot mutate; an off-allowlist, disallowed or out-of-scope verify argv refuses the whole plan before execution in every mode | read-only verify allowlist plus disallow check applied to verify argv inside check_plan, before approval and execution; verify argv is scoped to the op's repo, refs and issue number | verify is also executed | CAP-python3 | CODING | unit tests |
| R-7 | USER | CHANGE_REQUEST.md Manual check | AC-15 | live rename | scratch GitHub repo with gh auth | LIVE | CAP-gh-auth | LIVE_VERIFICATION | not available now; LIVE_VERIFICATION only, does not block coding |

Live check: AC-15 manual, command `uncle --housekeeping` with text `rename scratch repo X to Y`; non-secret prerequisite evidence: `gh auth status` output path recorded in verification report.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/housekeeping_policy.py` (new) | parser, allowlist, disallow, check_plan | I-1,I-2 | Low (new) | housekeeping-policy-test.py |
| `scripts/lib/housekeeping_config.py` (new) | disallow list CRUD + floor + fallback; reject duplicate and floor-equal patterns (list unchanged); user patterns only add refusals | I-4,I-7,H-9 | Low | housekeeping-policy-test.py (incl. duplicate, floor-equal, zero-op plan cases) |
| `scripts/lib/housekeeping_input.py` (new) | input validation | H-1 | Low | housekeeping-input-test.py |
| `scripts/housekeeping-workflow.sh` (new) | driver | H-3..H-10 | Low | housekeeping-workflow-test.sh |
| `prompts/housekeeping-plan.md` (new) | plan prompt requiring JSON ops | H-1 | Low | driver test with stub agent |
| `uncle` | flag, usage, did-you-mean, exclusivity, line-menu disallow editor (entry takes the last number in the Configure menu; no existing item moves), startup action. Flag combinations beyond the three exclusive flags keep their prior behavior; `--housekeeping` with no text and TTY stdin is refused as empty input (exit 1) | H-1,H-9,H-11 | Medium | housekeeping-launcher-test.sh (incl. other-flag combos unchanged, bare TTY refusal) + baseline suites |
| `uncle_tui.py` | `/housekeeping`, startup action, Misc config entry (takes the last position in the menu; no existing item moves) | H-2,H-9 | Medium | tui-housekeeping-test.py + baseline suites |
| `scripts/tests/housekeeping-*` (new) | tests | AC-13 | Low | self; includes AC-13 sole-call-site static test and check_plan-removal mutation test in housekeeping-workflow-test.sh |
| `README.md` | document flag | docs | Low | none |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1,2 (other flag combinations keep prior behavior; `--housekeeping` with no text and TTY stdin refused as empty input) | H-1, H-11 | - | uncle, housekeeping_input.py | input + launcher tests (flag-combination and empty-TTY cases) | - |
| AC-3 | H-2 | - | uncle_tui.py | tui-housekeeping-test.py | - |
| AC-4,5,6 | H-3, H-4 | I-2, I-5, I-6 | housekeeping-workflow.sh | workflow test | AC-15 |
| AC-7,8,9,13 | H-5, H-6, H-7 | I-1, I-2 | housekeeping_policy.py | policy test (enumerates every D-1 floor spelling: rm -rf/-fr/-Rf/--recursive --force on /, /*, ~, $HOME; force push variants to main, master, origin HEAD), defect injection | - |
| AC-10 | H-8 | I-3 | driver | workflow test, policy test: verify argv off the read-only allowlist or matching a disallow pattern refuses the whole plan before any command runs, in attended and unattended modes, and nothing executes | AC-15 |
| AC-11 | H-10 | I-8 | driver | workflow test | - |
| AC-12: disallow list is viewable and editable; invalid, empty or bare `*` patterns are rejected leaving the list unchanged; config can only add refusals; the locked floor is hard-coded and cannot be edited or removed. | H-9 | I-4, I-7 | config module, TUI, uncle | policy test (config module: empty/bare-* rejected, add-only, floor not in config), tui test, assert the new entry is last in each menu and existing items keep their numbers | TUI view |
| AC-14 | H-12 | - | all | baseline suites | - |

## Implementation sequence

Step IDs; no live prerequisites needed for coding. Decisions D-1..D-7 apply.

1. S-1 Policy library and config module (R-1,R-2,R-6; D-1,D-2,D-5,D-6,D-7). Pattern matching follows D-5 semantics (prefix program/subcommands, all pattern flags in any order, clusters expanded, --flag=value by name); unit tests cover clusters, =value, flags before subcommand, extra flags and partial-flag non-match. check_plan refuses a zero-op plan. Policy refuses remote `--delete` and `:ref` refspecs targeting the default branch, HEAD, main or master, with an execute-time merged check for remote deletes; tests cover each. Config module rejects empty or bare `*` patterns and duplicate or floor-equal pattern add/edit (list unchanged); user patterns only add refusals; the floor is hard-coded, not stored in config; tests assert each.
   Owns: `scripts/lib/housekeeping_policy.py`, `scripts/lib/housekeeping_config.py`, `scripts/tests/housekeeping-policy-test.py`
2. S-2 Input validator (R-3)
   Owns: `scripts/lib/housekeeping_input.py`, `scripts/tests/housekeeping-input-test.py`
3. S-3 Driver and prompt (R-4,R-5; D-3,D-4). The lock helper path is resolved at S-3 start by inspecting how existing drivers take driver.lock; it is sourced read-only and never edited. S-3 writes only under `.uncle/workflow/housekeeping/` (plus the shared driver.lock). The AC-13 static and mutation tests live in housekeeping-workflow-test.sh, owned by S-3, and operate on a temp copy of the driver.
   Owns: `scripts/housekeeping-workflow.sh`, `prompts/housekeeping-plan.md`, `scripts/tests/housekeeping-workflow-test.sh`
   Depends on: 1
4. S-4 Launcher flag, usage, did-you-mean, line-menu editor (builds on S-1 config CLI and S-2). The new entry takes the last number in the line menu; no existing item moves; no ordering dependency on S-5. Other flag combinations keep prior behavior; bare TTY `--housekeeping` is refused as empty input.
   Owns: `uncle`, `scripts/tests/housekeeping-launcher-test.sh`
   Depends on: 1, 2, 3
5. S-5 TUI slash command, startup action, Misc config entry (shares no file with S-4). The new entry takes the last position in the TUI menu; no existing item moves; no ordering dependency on S-4.
   Owns: `uncle_tui.py`, `scripts/tests/tui-housekeeping-test.py`
   Depends on: 1, 3
6. S-6 Docs and defect-injection evidence note (inside S-3 test already; docs only)
   
   S-1 and S-2 are independent; S-4 and S-5 are independent after their dependencies.
   Owns: `README.md`
   Depends on: 4, 5

## Scope cuts under time pressure
Cut first: README docs (S-6); then line-menu editor parity (keep TUI editor); then issue-triage and label-cleanup ops (allowlist shrinks to rename, worktree, branch cleanup per the issue's suggestion); never cut policy check, verify honesty, or defect injection tests.

## 22. Risks and unresolved questions

| Risk | Mitigation |
|---|---|
| Parser gap bypasses policy | strict tokenizer refuses anything unusual; exhaustive variant tests; locked floor |
| Existing tests pin usage/help text | additive edits; minimal expected-string updates recorded; renewed authority if protected tests change |
| `.uncle/config` syntax unknown | reuse existing helpers; verify at S-1/S-4 start |
| Plan model emits bad JSON | refuse run, nothing executes |

Risk row 2 is amended: existing tests are never edited. Usage changes must pass every existing assertion unchanged; otherwise implementation stops for human re-approval.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | The plan did not say how argv maps to an allowlist shape versus the model's op label; deriving the op from argv alone closes that gap. | Edited s1.1.i1 and s1.1.i4 and R-1 to state that the policy derives the op from argv and refuses on no match or label disagreement. |
| AR-002 | Accepted | Floor and default list were conflated and the floor list was unresolved; separating them gives AC-7 tests an oracle. | D-1 now defines the locked floor as exactly its list, and the default list as the change-request lists verbatim. |
| AR-003 | Accepted | Remote branch delete was allowed without protecting default/current branch or refspec forms; real gap. | Edit D-2 and D-7 to add remote-delete refusal rules (default branch, HEAD, colon/refspec forms) and add test coverage to R-1. |
| AR-004 | Accepted | The plan was ambiguous about who supplies verify argv; a fixed per-op template removes model dependence from the safety path. | Edited s1.1.i4 and D-4 so verify argv comes from a fixed per-op template, with model-supplied verify argv required to equal it and expected compared by exact string. |
| AR-005 | Accepted | Mid-run failure behavior and exit codes were undefined; the proposed rule is consistent with the state machine and the verify-honesty goal. | Section 7 state-transition prose now defines post-failure verify and exit codes; section 8 CLI item states exit statuses. |
| AR-006 | Accepted | Edge inputs (zero-op plan, duplicate/floor-equal patterns, user patterns vs allowlist) were unspecified and need a testable rule. | D-5 extended with edge rules; s17.1.r2 coverage updated; step-1 text and tests note the zero-op and duplicate/floor-equal cases. |
| AR-007 | Accepted | Editing existing tests contradicts AC-14, which requires existing suites to pass as at baseline. | Section 10 (s9.1) now forbids editing existing tests; section 17 (s13.1) requires unmodified suites to pass. |
| AR-008 | Accepted | Real gap: only three exclusive flags were specified; other combinations and bare --housekeeping with empty TTY stdin were undefined. | Launcher row s17.1.r6 and AC-1/2 traceability row s18.1.r1 now state that other flag combinations keep prior behavior and bare --housekeeping on TTY stdin is refused as empty input. |
| AR-009 | Accepted | The menu position was ambiguous and could shift existing numbered selections or item-count tests. | Section 10 now says the entry takes the last number in each menu and no item moves; the uncle and TUI impact rows and AC-12 agree. |
| AR-010 | Accepted | The plan sourced state.sh and reused driver.lock without bounding shared-state access or lock release, so the boundary must be explicit. | Edit driver item s1.1.i4, R-4 and s7.1 to confine state/gate files to .uncle/workflow/housekeeping/ and release driver.lock on every exit path. |
| AR-011 | Accepted | Real gap: config writes into shared .uncle/config must not disturb other keys. | Edited s1.1.i2 and D-5 so config writes change only housekeeping.disallow and leave every other key unchanged. |
| AR-012 | Accepted | The argv grammar for allowlisted shapes was undefined; exact full-argv matching closes global-option, `--`, `git -c`, `gh --repo` and env-prefix bypasses. | s1.1.i1 and R-1 now specify exact full-argv matching and refusal of global options, unlisted flags, `--` and env-assignment tokens. |
| AR-013 | Accepted | Remote delete of the default branch/HEAD and merged-only enforcement for remote deletes were unspecified; both are real safety gaps. | Edit D-2 and D-7 to refuse default-branch/HEAD/main/master remote deletes and colon refspecs and require an execute-time merged check; mirror in step-1. |
| AR-014 | Accepted | Floor variants were unspecified; rm and wrappers are not allowlisted and force spellings must be covered by the floor. | Edit D-1 to define floor variants and D-2 to exclude rm/wrappers from the allowlist. |
| AR-015 | Accepted | Real TOCTOU gap: nothing bound the approved plan to the executed argv, and displayed argv escaping was unspecified. | Section 1 driver item now hashes the policy-checked plan, approves that hash, executes only it, and escapes control characters in displayed argv. |
| AR-016 | Accepted | Config scope was unspecified; making it add-only with hard-coded floor and rejecting empty or over-broad patterns closes the gap. | Updated D-5, step-1 text, and AC-12 requirement/tests to state add-only config, rejected empty/bare-* patterns, and hard-coded floor. |
| AR-017 | Accepted | Read-only verify commands can take arbitrary targets and issue-triage had no defined shape; scoping both closes the gap. | Edit D-2 (fixed issue-triage shapes), D-6 and R-6 (verify argv scoped to the operation's repo/refs/issue). |
| AR-018 | Accepted | Plan left open whether verify argv is policy-checked and what an off-allowlist verify does; refusing the whole plan up front is the safe, mode-independent choice. | Edit D-6 and R-6 to require verify argv to pass the verify allowlist and disallow check, refusing the whole plan pre-execution; update AC-10 to cover it. |
| AR-019 | Accepted | The floor and default-branch definitions were vague, leaving AC-7 tests without an oracle; a precise definition is needed. | D-1 now defines the exact floor and default branch; R-1 and the policy traceability row require tests against that oracle. |
| AR-020 | Accepted | The pattern grammar left flag matching semantics open; fixing them gives AC-7 and AC-12 tests a precise oracle. | D-5 now defines match semantics (prefix program/subcommands, all flags any order, clusters expanded, --flag=value by name); step-1 and R-1 carry it. |
| AR-021 | Accepted | Real gap: only invalid JSON was covered; zero-op, duplicate-id and missing-field plans were unspecified. | Section 7 state text now adds a plan schema rule: invalid JSON, zero ops, duplicate ids or missing fields is REFUSED with exit 1 before approval. |
| AR-022 | Accepted | Exit statuses and post-failure verification were unspecified; the proposed rule is clear and consistent with honest-verify. | Section 7 state text gains post-FAILED verify and exit-code rule; section 8 gains an exit-status interface item. |
| AR-023 | Accepted | AC-13 static and mutation tests need a concrete mechanism for a bash driver; a single execution function consuming check_plan output provides one. | Section 16 gains a prose block defining the sole-call-site static test and check_plan-removal mutation test; change-impact row for tests cites it. |
