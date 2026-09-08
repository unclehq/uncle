# scripts/

Six standalone bash scripts. Each resolves two roots: the install root, from
its own location, which supplies the prompts, libs, and agent shims; and the
project root, which is `UNCLE_PROJECT_ROOT` when the `uncle` launcher exports
it and the install root otherwise. The driver `cd`s to the project root, so
`.uncle/workflow`, the artifacts, and the diff belong to the project being
worked on rather than to the directory uncle is installed in. All are bash 3.2 compatible (macOS system bash).

Every script accepts `-h` / `--help`, prints a usage summary, and exits 0
without performing any other work — no directory creation, no precondition
checks, and no `claude` / `codex` invocation.

## Scripts

### `stagegate.sh` — new-application workflow driver

Runs the human-gated new-application workflow from `REQUIREMENTS.md`. It is a
resumable state machine; re-run it to continue from the current stage.

```sh
./scripts/stagegate.sh              # run / resume the workflow
./scripts/stagegate.sh -h
./scripts/stagegate.sh --help
./scripts/stagegate.sh --version    # prints 0.1.0
./scripts/stagegate.sh --unattended # run with nobody at the terminal
```

Takes no positional arguments. All configuration is via `WORKFLOW_*`
environment variables (see [Configuration](#configuration)). Approvals are
recorded with `./scripts/workflow.sh`.

### `--unattended`

Both drivers accept it, and `uncle --unattended` hands it to whichever driver
the menu picks. Every gate that would wait for a person passes on its own:
approvals are recorded against the real digest of the file, preflight
prerequisites that nobody can supply are waived, and each one is appended to
`.uncle/workflow/unattended-gates`. COMPLETE reports how many gates went
unreviewed, so a run finished this way never reads as one a person signed off.

What it does not do is make anything pass. A waiver records that a required
check was not performed and keeps saying so; a failing verification suite, a
regressed baseline, and a final audit that does not say READY all still stop
the run, because those wait on a result rather than on a person. The change
driver also leaves the originating GitHub issue open: closing it would tell
everyone watching that a person accepted the change.

It is opt-in and never inferred. A piped run with no terminal is still a run
someone is watching; only the flag says otherwise.

New applications run `PREFLIGHT` after updated-plan approval, then `IMPLEMENT`,
the human diff gate, `TEST_REVIEW`, `MANUAL_CHECKLIST`, `EXECUTE_CHECKLIST`, and
`FINAL_AUDIT`. Preflight requires both a `Verification commands` block and a
`Protected verification paths` block in the approved plan. Automated browsers
and local test servers belong in the commands when acceptance needs them.

`PREFLIGHT_REPORT.md`, `TEST_REVIEW.md`, and `VERIFICATION_REPORT.md` have an
`Acceptance gate` table with `ID`, `Required`, `Status`, and `Evidence` columns.
Required rows must all PASS. FAIL routes test review or execution to `REPAIR`;
BLOCKED/NOT RUN/N/A on a required row pauses the current stage. Malformed or
missing tables fail closed. Preflight failures always pause before code changes.

Test review receives the current driver verification summary directly in its
prompt, plus exact paths and hashes for hidden workflow evidence. Historical
failures must be reconciled with current results. Additional regression cases
inside approved commands are assessed against requirements and scope; a longer
defect-ID list alone is not a reason to remove coverage or require reapproval.

Repairs use a fresh `implementation` runner and `prompts/repair.md`. Context is
limited to current blocking findings, matching approved constraints, protected
paths, and affected source/tests. The agent expands those inputs only when the
fix requires it and runs failing commands and targeted checks; the driver still
runs the complete approved verification suite. Earlier passes are not reported
as fresh repair evidence. Repairs preserve
the failed report, update code and implementation reports, and return through
driver verification, fresh human diff approval, independent test review, and
checklist execution. `.uncle/workflow/repair-source` identifies the report;
`repair-count` records attempts across restarts. `WORKFLOW_MAX_REPAIRS` defaults
to 2 (0 disables automatic repair; maximum 100). An exhausted limit leaves the
state at `REPAIR`; inspect the defect before deliberately raising the limit.

The driver stores protected path scopes and SHA-256 inventories in
`verification.paths` and `verification.manifest` under `.uncle/workflow` and
includes them in the implementation review. Test commands and checklist
execution must preserve those inputs. Edits, additions, or deletions invalidate
verification, produce `VERIFICATION_INTEGRITY.md` in that workflow, and leave
the run at `REPAIR`. Python bytecode caches are excluded; other generated outputs
must go outside protected scopes. Test reviewers check that scopes include all
test helpers, expected values, and runner configuration. Hash comparisons detect
changes around each driver command and at stage boundaries; they are not an
OS-level write restriction.
The driver retains copies in `verification-snapshot.*` directories. After a
repair, `TEST_CHANGES.diff` compares the old and new protected inputs and is
included in the human implementation review and independent test review. This
preserves the previous assertions even when the project has no Git history.

These acceptance transitions apply to the new-application driver. Existing
change-workflow transitions are unchanged. Project-local prompt overrides must
adopt the new report tables and plan block before using these stages. An old
run resumed at final audit is sent back for missing acceptance evidence; a plan
missing the new path block needs amendment and renewed approval.

### Performance controls and reports

Run `uncle --performance` from a project, or
`bash /path/to/uncle/scripts/performance-report.sh /path/to/project`.
Both drivers write atomic per-attempt JSON records under
`.uncle/workflow/metrics/`; reports sort stages by accumulated work time.
Agent and reviewer records include the runner, configured model and effort,
workflow state (including repair), and speculative-execution flag. No telemetry
is sent elsewhere. `WORKFLOW_METRICS=0` disables collection without affecting
verification. Shell timings resolve whole seconds; Python check timings have
subsecond resolution. Token values are copied from the last runner result or
final token trailer, with unknown values left null; cache fields and reported
totals are not added to input/output counts. Stage runtime includes model and
tool execution. Parallel work overlaps, and killed attempts may lack records.

The approved command source may optionally include this separate section:

````md
## Parallel verification groups

```text
2 3
5 6
```
````

Numbers are consecutive, one-based positions in the verification command list.
Groups must be ordered, disjoint, and in range. Ungrouped commands and boundaries
between groups remain sequential. Use this only for checks with independent
ports, outputs, fixtures, and state. New applications read groups from
`UPDATED_PROJECT_PLAN.md`; changes read them from approved `BASELINE_REPORT.md`,
using the same grouping before and after the change. `WORKFLOW_VERIFY_JOBS`
limits concurrency to 1–8 (default 2). Without Python or a compatible guard,
execution falls back to sequential checks. Missing dependencies in a check
still fail that check. Output is collected per command and combined in approved
order; failures remain visible. Interrupting the executor stops its children.

For new applications, each concurrent command checks protected inputs before
and after running. Any observed mutation invalidates the verification even if
another check later restores the file. Already running checks are joined before
the driver enters repair, and later groups do not start. The same independent
test review must approve the concurrency assumptions.

`WORKFLOW_HASH_BACKEND=auto` uses a single Python process for complete content
hashing, falling back to the shell implementation only when Python is unavailable.
Set `shell` or `python` to select a backend explicitly. Backend failures never
trigger a fallback that could hide an unreadable or missing protected input.

### `change-workflow.sh` — existing-code change workflow driver

Runs the human-gated existing-code change workflow from `CHANGE_REQUEST.md`.
Also a resumable state machine; re-run it to continue from the current stage.

```sh
./scripts/change-workflow.sh              # run / resume the workflow
./scripts/change-workflow.sh -h
./scripts/change-workflow.sh --help
./scripts/change-workflow.sh --version    # prints 0.1.0
```

Takes no positional arguments. All configuration is via `WORKFLOW_*`
environment variables. Seed `CHANGE_REQUEST.md` from a GitHub issue with
`./scripts/from-issue.sh`.

### `workflow.sh` — manual approval helper

Records a human approval by writing the SHA-256 of the approved file to
`.uncle/workflow/approvals/`, and reports approval status.

```sh
./scripts/workflow.sh approve-plan
./scripts/workflow.sh approve-review
./scripts/workflow.sh approve-updated-plan
./scripts/workflow.sh status
./scripts/workflow.sh -h
./scripts/workflow.sh --help
```

Exactly one subcommand is required. `-h` / `--help` print the usage block and
exit 0. Any other input — no arguments, an unknown subcommand, or a valid
subcommand with extra arguments — prints the same usage block and exits 1.

### `from-issue.sh` — seed a workflow from a GitHub issue

Fetches a GitHub issue and writes `CHANGE_REQUEST.md` or the project-brief
section of `REQUIREMENTS.md` from it.

```sh
./scripts/from-issue.sh <issue-number | github-url> [--change | --new]
./scripts/from-issue.sh 123
./scripts/from-issue.sh https://github.com/owner/repo/issues/123 --new
./scripts/from-issue.sh -h
./scripts/from-issue.sh --help
./scripts/from-issue.sh                   # no arguments: same as --help
```

- `--change` writes `CHANGE_REQUEST.md` (the default if `CHANGE_REQUEST.md`
  already exists or the repo is not empty), then prompts for the exact word
  `RUN` and, on confirmation, runs `./scripts/change-workflow.sh` in the same
  process. Anything other than `RUN`, including EOF, is a decline: the file
  stays, nothing runs, exit 0. The prompt is printed and blocks even when stdin
  is not a terminal.
- `--new` replaces the project-brief section of `REQUIREMENTS.md` for
  `./scripts/stagegate.sh`. Unchanged: no prompt, no auto-run, no close.

Requires either the `gh` CLI (authenticated) or `curl` (public repos only).
Closing the issue additionally requires `gh`: if the issue was fetched over the
`curl` fallback, or `gh` is missing or unauthenticated at close time, the close
is skipped with a message and the run is still a success.

The issue is closed only if all of these hold: `.uncle/workflow/audit-verdict` records
this run's id, its verdict class is `READY` or `READY_WITH_NON_BLOCKING_ISSUES`,
`.uncle/workflow/origin` still names this issue, and `FINAL_AUDIT.md` still hashes to
the value recorded when it was classified. Any mismatch leaves the issue open
and prints the reason. A driver exit code other than 0 is propagated and no
close is attempted.

`change-workflow.sh` now performs that same close itself on reaching `COMPLETE`,
so a run started or resumed directly — without going back through
`from-issue.sh` — still closes its issue. The decision lives in one place,
`scripts/lib/issue-close.sh`, and both entry points call it. The driver's close
additionally requires that the run can prove which issue it owns: either
`.uncle/workflow/state` already carried an issue prefix when the run started, or
`STAGEGATE_ORIGIN_REPO`/`STAGEGATE_ORIGIN_ISSUE` were set for that invocation.
A leftover `.uncle/workflow/origin` found on disk by an otherwise fresh run is not
enough. `WORKFLOW_CLOSE_ISSUE=0` disables the driver-side close entirely. After
a successful close the driver writes `.uncle/workflow/issue-closed`, and
`from-issue.sh`'s own post-run check — now a defensive fallback rather than the
only path — sees that marker and does not close a second time. A close that
fails leaves no marker, so a later rerun of the same run id may retry it.

State files this contract depends on, all under the gitignored `.uncle/workflow/`:

| File | Written by | Meaning |
|---|---|---|
| `origin` | `from-issue.sh` on confirmation; `change-workflow.sh` in `ANALYZE` | `<owner/repo>TAB<issue>[TAB<gh\|curl>]` that owns this checkout's in-flight run. The third field records how the issue was fetched; only `gh` may authorize a close, and a two-field file written before this field existed reads as `curl` |
| `audit-verdict` | `change-workflow.sh` in `FINAL_AUDIT` | `<run-id>TAB<class>TAB<sha256 of FINAL_AUDIT.md>`; `stagegate.sh` writes `<class>TAB<sha256>` |
| `audit-override` | either driver in `WAIT_AUDIT_OVERRIDE` | `<utc>TAB<class>TAB<sha256 of FINAL_AUDIT.md>`; a human chose to finish over a failing audit, and the issue is never closed |
| `IMPLEMENTATION_REVIEW.md` | either driver, at the implementation gate | the generated document the operator approves: file list, green check, agent notes and test report, and the full diff. Rebuilt from the tree on every gate entry |
| `green-check.baseline.tsv` | `change-workflow.sh` in `PLAN` | `<exit status>TAB<command>` for the approved command list, run before anything changed |
| `green-check.tsv` | either driver after implementation | `<PASS\|FIXED\|PREEXISTING\|REGRESSION>TAB<command>` |
| `green-check-override` | either driver at the implementation gate | `<utc>TAB<n> regression(s) overridden`; a human approved over a failing check |
| `untracked-before.txt` | either driver at the start of implementation | untracked paths that already existed, so they are not charged to the change |
| `issue-closed` | `change-workflow.sh` after a successful close | `<run-id>TAB<owner/repo>TAB<issue>`; absence means no driver-side close happened |
| `state` | either driver on every transition | `<STAGE>`, or `<issue>:<STAGE>` when the issue is known. The prefix is informational; a bare token stays valid |
| `lock/pid` | `change-workflow.sh` for the length of a run | pid of the run holding the checkout |

A state file whose issue prefix disagrees with `.uncle/workflow/origin`'s issue is
treated as corruption by both the driver's preflight and `from-issue.sh`'s seed
gate: they refuse and exit 1 rather than resolve it in either file's favour.

`from-issue.sh --change` refuses to seed when `.uncle/workflow/state` shows an
in-flight run whose `.uncle/workflow/origin` names a different issue, or names nothing
at all. When the origin matches the issue being seeded, `CHANGE_REQUEST.md` is
left as it is — hand edits survive a resume — and only the prompt is repeated.
`change-workflow.sh` performs the mirror-image check when launched by
`from-issue.sh`, and refuses to start at all while another run holds
`.uncle/workflow/lock`. The refusal names the exact command that clears the state
deliberately; neither script ever clears it automatically.

### `codex-review-plan.sh` — adversarial plan review (Stage 2)

Runs the reviewer CLI against the approved `PROJECT_PLAN.md` and writes
`ADVERSARIAL_REVIEW.md`.

```sh
./scripts/codex-review-plan.sh
./scripts/codex-review-plan.sh -h
./scripts/codex-review-plan.sh --help
```

Takes no positional arguments. Requires `REQUIREMENTS.md`, `PROJECT_PLAN.md`,
and a matching approval record in `.uncle/workflow/approvals/PROJECT_PLAN.sha256`.
Normally invoked by the driver; can be run by hand.

### `codex-create-checklist.sh` — manual checklist generation (Stage 6)

Runs the reviewer CLI against the approved `UPDATED_PROJECT_PLAN.md` and the
automated-test report, and writes `MANUAL_CHECKLIST.md`.

```sh
./scripts/codex-create-checklist.sh
./scripts/codex-create-checklist.sh -h
./scripts/codex-create-checklist.sh --help
```

Takes no positional arguments. Requires `REQUIREMENTS.md`,
`UPDATED_PROJECT_PLAN.md`, `AUTOMATED_TEST_REPORT.md`, and a matching approval
record in `.uncle/workflow/approvals/UPDATED_PROJECT_PLAN.sha256`. Normally invoked
by the driver; can be run by hand.

## Argument handling summary

| Script | `-h` / `--help` | `--version` | Positional arguments | Unrecognized argument |
|---|---|---|---|---|
| `stagegate.sh` | usage, exit 0 | `0.1.0`, exit 0 | none | usage on **stderr**, exit 1 |
| `change-workflow.sh` | usage, exit 0 | `0.1.0`, exit 0 | none | usage on **stderr**, exit 1 |
| `codex-review-plan.sh` | usage, exit 0 | not supported | none | usage on **stderr**, exit 1 |
| `codex-create-checklist.sh` | usage, exit 0 | not supported | none | usage on **stderr**, exit 1 |
| `workflow.sh` | usage, exit 0 | not supported | exactly one subcommand | usage on **stdout**, exit 1 |
| `from-issue.sh` | usage, exit 0 | not supported | issue number or URL, optional `--change` / `--new` | usage on **stdout**, exit 1 |

Two intentional exceptions to the "unrecognized argument goes to stderr" rule:
`workflow.sh`'s fall-through branch and all of `from-issue.sh` write usage to
**stdout**. Both are pre-existing behaviors that callers may depend on, and
both are deliberately preserved rather than made uniform.

A recognized flag with trailing arguments (for example
`./scripts/stagegate.sh --help extra`) is rejected as an unrecognized
argument; it is not silently accepted.

## Configuration

`stagegate.sh`, `change-workflow.sh`, and the two `codex-*` helpers read all
configuration from `WORKFLOW_*` environment variables, never from CLI flags.
The full list of variables, with defaults, is in the top-level `README.md`
under "Configuration". The two that decide which external CLI is spawned:

| Variable | Default | Used by |
|---|---|---|
| `WORKFLOW_STEPWISE_IMPLEMENT` | `0` | `change-workflow.sh` |
| `WORKFLOW_DIFF_GATE` | `1` | both drivers |
| `WORKFLOW_GREEN_CHECK` | `1` | both drivers |
| `WORKFLOW_AUDIT_GATE` | `1` | both drivers |
| `WORKFLOW_AGENT_CMD` | `scripts/agent-kimi.sh` | `stagegate.sh`, `change-workflow.sh` |
| `WORKFLOW_REVIEWER_CMD` | `codex` | both drivers and both `codex-*` helpers |

Setting both to `false` is a convenient way to exercise the argument-handling
paths without spawning a real agent.

Every stage can override those two, and its model and effort, on its own:

| Variable | Effect |
|---|---|
| `WORKFLOW_AGENT_CMD_<STAGE>` | the agent CLI for one stage; falls back to `WORKFLOW_AGENT_CMD` |
| `WORKFLOW_REVIEWER_CMD_<STAGE>` | the reviewer CLI for one stage; falls back to `WORKFLOW_REVIEWER_CMD` |
| `WORKFLOW_MODEL_<STAGE>` | the model for one stage — **set and empty means pass no model flag** |
| `WORKFLOW_EFFORT_<STAGE>` | the reasoning effort for one stage |

`<STAGE>` is the stage's log name, upper-cased with non-alphanumerics replaced
by `_`: `REQUIREMENTS`, `PROJECT_PLAN`, `ADVERSARIAL_REVIEW`, `IMPLEMENTATION`,
`FINAL_AUDIT`, and so on.

The empty-model rule is what lets one run mix runners. cline needs to be told
which model to use; claude, kimi, and codex have their own defaults, and a
model uncle invented for them would be wrong more often than right. So a stage
configured for one of those exports an empty model, and the driver omits
`--model` entirely rather than substituting its own default. An *unset*
variable still falls back to the driver's built-in default, which is what keeps
a driver run directly, with no launcher, behaving as before.

### Runner shims

One shim per runner per side, and the side is the difference that matters:

| Runner | Agent stage | Reviewer stage |
|---|---|---|
| `cline` | `agent-cline.sh` (act mode) | `reviewer-cline.sh` (plan mode) |
| `claude` | `claude` | `reviewer-claude.sh` |
| `kimi` | `agent-kimi.sh` | `reviewer-kimi.sh` (ReadFile, Glob, Grep only) |
| `codex` | `agent-codex.sh` (`--sandbox workspace-write`) | `codex` (`--sandbox read-only`) |

Each shim takes the flags the drivers send (`claude -p`'s set for an agent
stage, `codex exec`'s for a reviewer stage) and translates them onto its own
CLI, then rewrites that CLI's event stream into the stream-json schema the
drivers render and cost-account against. A shim that cannot express one of the
driver's limits says so in its header: `agent-codex.sh` drops `--max-turns`,
`--max-budget-usd`, and `--allowedTools` because codex exec has no equivalent,
so a stage on that runner is bounded by its sandbox and nothing else.

### Output rules and plan gates

Every stage that writes a markdown document for a human to read gets
`OUTPUT_RULES.md` appended to its prompt — the requirements interpretation, the
specs, the plans, the notes and reports, and the reviewer's own artifacts.
Plan-producing stages additionally get `lib/gates/GATES.md`, which is the
quality bar a plan must pass; the stage's prompt owns the target file and the
section list.

Both resolve local-first: an explicit `UNCLE_OUTPUT_RULES` / `UNCLE_GATES`
path, then the project's own copy, then the copy installed with uncle. The
driver logs which source it used, and the rules are appended to the prompt it
sends, never written into the prompt files on disk.

Every document stage also receives per-file byte and line ceilings from
`scripts/lib/gates.sh`, enforced before advancement. This includes stepwise
handoffs, background checklists, repairs, test reports, and acceptance evidence
summaries. Raw logs and source code are uncapped. See the root README's budget
table and `WORKFLOW_DOC_MAX_BYTES_<ARTIFACT>` / `WORKFLOW_DOC_MAX_LINES_<ARTIFACT>`
overrides. An oversized document is preserved and stops the stage; required
checks, evidence, and dispositions must not be dropped to fit.

### Frozen scope and stepwise implementation

`scripts/lib/plan-scope.sh` reads the two machine-usable structures out of
`CHANGE_PLAN.md`: the file list in the change-impact table, and the ordered
steps in the implementation sequence.

The driver uses the file list twice. It appends it to the implementation
prompt, so the stage opens the named files instead of searching for the change
surface; and it checks the diff against it afterwards. Changing a file the plan
did not name is allowed — a review disposition routinely requires it — but it
must be named in `IMPLEMENTATION_NOTES.md` with a reason, which the workflow
already required and did not enforce. An unrecorded one fails the stage.

The check reads the same file set the operator is shown at the implementation
gate — `change_diff_files` — rather than `git diff` alone. `git diff` reports
only tracked changes, so a file the agent *created* escaped the frozen scope
entirely, which is the largest kind of scope creep there is. Untracked paths
that already existed when implementation started are recorded in
`.uncle/workflow/untracked-before.txt` and excluded: a scratch file in the operator's
checkout is not something the agent did.

`scripts/lib/workflow-artifacts.sh` holds the one list of files the workflow
writes, shared by this check and the review diff. They previously carried two
different copies, and the difference could not surface while only tracked files
were examined: none of these artifacts is committed in a target repository.

A plan with no change-impact table is a warning, not a failure: the scope is
unknown rather than empty, and failing every file would punish plan formatting
rather than scope creep.

`WORKFLOW_STEPWISE_IMPLEMENT=1` runs implementation as one invocation per step
of the sequence, each starting cold, instead of one run of up to 200 turns.
Nothing is evicted from a context, so cost is turns x context and the last
turns of a long run are the most expensive tokens in the pipeline. Splitting
resets the accumulated tool output at each step; the plan is re-read per step,
so the fixed part is paid N times while the growing part is paid once per step.
`IMPLEMENTATION_NOTES.md` and the code on disk are the handoff between steps.

The turn cap is divided across the steps rather than multiplied, and
`.uncle/workflow/implement-step-done` makes a partial run resumable. It is off by
default: it changes how the most consequential stage runs, and a step boundary
in the wrong place costs coherence, which is worth more than tokens.

Covered by `scripts/tests/plan-scope-test.sh`.

### The gates around implementation

`scripts/lib/green-check.sh` and `scripts/lib/implementation-review.sh` carry
the two checks that sit between the implementation stage and everything that
reads its output.

`verify_commands` reads a command list out of a fenced block under a document's
verification-command heading — section 8 of `BASELINE_REPORT.md`, or
`## Verification commands` in `UPDATED_PROJECT_PLAN.md`. Nothing outside that
block is read, and the block is only taken from a document that has already
passed a human gate: the driver executes these commands with its own
privileges, so what it runs has to be something the operator approved.

`green_run` records `<exit status>TAB<command>` per line, with stdin closed so
a command that reads it cannot consume the rest of the list. `green_classify`
compares a post-change run against the baseline run: `PREEXISTING` for a check
that was already failing, `REGRESSION` for one that was green and is not. A
command with no baseline entry that fails is a `REGRESSION` — an unrecorded
baseline is not evidence of a prior failure. The new-application pipeline has
no baseline at all, so every failure there is a failure of the build.

`write_change_diff` materializes the change: everything the tree changed
against `HEAD` plus untracked files, with workflow artifacts removed. Untracked
files matter — a file the agent created is the one file in the change with no
prior reviewer — and are rendered with `git diff --no-index`, which never
writes to the index. `write_implementation_review` composes the document the
gate shows.

The document is generated rather than agent-written, so it is reproducible:
rebuilding it from an unchanged tree yields the same bytes. That is what turns
the approval digest into a check on the tree. The stage after the gate rebuilds
it and compares; a mismatch re-opens the gate on the current tree instead of
carrying a stale approval forward.

A failing check does not end the run. It changes the gate's wording from
approve to override and records the override, which keeps the decision with the
operator. With `WORKFLOW_DIFF_GATE=0` there is no operator in the path, so the
driver refuses to continue past a regression instead.

Covered by `scripts/tests/green-check-test.sh`,
`scripts/tests/implementation-review-test.sh`, and
`scripts/tests/gates-test.sh`, which drives both real drivers through these
states in a scratch git repository against stub CLIs.

### agent-kimi.sh

The default agent command is a shim, not a CLI. The drivers spawn one agent
command for every stage and pick the tier with `--model`, so pointing
`WORKFLOW_AGENT_CMD` straight at `kimi` would move the opus stages too.
`agent-kimi.sh` dispatches on the model instead: `kimi` and `kimi:<alias>` run
on kimi, every other value is passed through to `claude` unchanged.

kimi is not flag-compatible with `claude -p`, so the kimi path also moves the
prompt from stdin to `-p`, drops the claude-only flags, and rewrites kimi's
event stream into the schema the drivers' `format_claude_stream` renders.

kimi talks to a remote API and a connection can go established but silent; the
process then sits in a socket read at 0% CPU indefinitely. Because the shim
drops `--max-turns` and `--max-budget-usd` (kimi does not accept them), nothing
else in the pipeline bounds that. The shim therefore enforces its own guard on
*silence* rather than on total runtime — a stage that legitimately runs for
twenty minutes is fine; one that has emitted nothing for five is not. On firing
it stops kimi's whole process group and emits an `is_error` result, so the
driver fails the stage instead of parking on it.

| Variable | Default | Meaning |
|---|---|---|
| `WORKFLOW_KIMI_IDLE_TIMEOUT` | `300` | Seconds of no output before kimi is stopped |
| `WORKFLOW_KIMI_MODEL` | `moonshot-ai/kimi-k2.7-code-highspeed` | Model for a bare `kimi` tier |
| `WORKFLOW_KIMI_CMD` | `kimi` | kimi binary |
| `WORKFLOW_CLAUDE_CMD` | `claude` | Binary for the passthrough branch |

Set `WORKFLOW_AGENT_CMD=claude` to take every stage back to Claude, or set an
individual stage back with e.g. `WORKFLOW_MODEL_BASELINE=sonnet`.

### uncle — interactive launcher

`uncle` (repo root) is an interactive launcher for the three drivers. The model,
reasoning effort, and per-stage overrides are set in the Configure menu (menu
option 4) and persisted to `.uncle/config`; when a driver runs they are exported
as `UNCLE_CLINE_MODEL`/`UNCLE_CLINE_EFFORT`, and
`WORKFLOW_AGENT_CMD`/`WORKFLOW_REVIEWER_CMD` are set to the matching shims. When
stdin and stdout are real terminals it opens a full-screen TUI (`uncle_tui.py`);
otherwise it falls back to a line menu. The config is `STAGE VALUE` lines:

| Key | Meaning |
|---|---|
| `runner` | `cline` (default), `claude`, `kimi`, or `codex` — picks the agent/reviewer commands |
| `model` | cline model id for agent stages (`UNCLE_CLINE_MODEL`); empty = cline default |
| `effort` | reasoning effort (`high`/`medium`/`low`) |
| `reviewer` | cline model id for reviewer stages (`UNCLE_CLINE_REVIEWER_MODEL`) |
| `<stage>` | cline model id for that stage (`WORKFLOW_MODEL_<STAGE>`) |

Valid stage keys: `requirements`, `project-plan`, `updated-plan`,
`preflight`, `implementation`, `execute-checklist`, `baseline`, `change-spec`,
`change-plan`, `updated-change-plan`, `adversarial-review`, `test-review`,
`manual-checklist`, `final-audit`. Repairs use the `implementation` settings.

### agent-cline.sh / reviewer-cline.sh

The cline runner (the `uncle` default). `agent-cline.sh` translates the drivers'
`claude -p` flag set onto `cline` and rewrites cline's `--json` NDJSON
(`agent_event` / `content_end` / `usage` / `run_result`) into the stream-json
schema the drivers render and cost. `reviewer-cline.sh` translates `codex exec`
onto `cline -p`; plan mode enforces read-only, and the review text and token
totals come from `run_result` (falling back to a `done` event).

| Variable | Default | Meaning |
|---|---|---|
| `WORKFLOW_CLINE_CMD` | `cline` | cline binary for both shims |
| `UNCLE_CLINE_MODEL` | (none) | cline model id for agent stages; overrides the driver `--model` |
| `UNCLE_CLINE_REVIEWER_MODEL` | (none) | cline model id for reviewer stages |
| `UNCLE_CLINE_EFFORT` | `medium` | reasoning effort (`none`/`low`/`medium`/`high`/`xhigh`) |

Both are covered by `scripts/tests/agent-cline-test.sh` and
`scripts/tests/reviewer-cline-test.sh`.

Kimi reviewer stages use the current Kimi Code CLI Markdown agents (`--agent-file`).
The reviewer uses `lib/kimi/reviewer.md` with an explicit read-only tool list.
Set `WORKFLOW_KIMI_CMD` to the Kimi executable and `WORKFLOW_KIMI_MODEL` to its
configured model alias when needed. No model override now correctly selects Kimi.

Oversized reviewer artifacts (including background checklists) receive one bounded
compaction pass, using the same runner/model/effort and read-only sandbox. No new
review is requested. Original text and candidates stay in the stage log directory;
failed compaction never replaces the original. `WORKFLOW_REVIEW_COMPACT=0` opts
out; `WORKFLOW_REVIEW_COMPACT_SECONDS` defaults to 120 (range 1–600). The checks
preserve structural anchors; the human still judges whether meaning is retained.
Covered by `scripts/tests/review-compaction-test.sh`.

Adversarial plan-review retries use `.uncle/workflow/review-cache/` when local
inputs, Git HEAD, review instructions and reviewer settings match. Budget changes
do not invalidate the review. A speculative review rejected on size returns 42
and pauses without replaying the full stage. Set `WORKFLOW_REVIEW_CACHE=0` to
force fresh analysis. Caching is disabled for later evidence/audit stages,
symlink inputs, and snapshots over 100 MB. Existing reviews without a snapshot
are not retroactively trusted. Tests: `scripts/tests/review-cache-test.sh` and
the cache/retry cases in `scripts/tests/gates-test.sh`.
