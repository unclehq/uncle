# Stagegate

> Governed CI for coding agents.
>
> Everyone else is building agents that run unsupervised. This is the approval
> layer that makes them acceptable in production.

Stagegate is a human-gated, adversarially-audited CI pipeline for
AI-generated code. A primary agent plans, implements, and verifies; an
independent reviewer audits adversarially; a human approves at every gate.
By default the primary agent is `scripts/agent-kimi.sh` (kimi for the kimi-tier
stages, `claude` otherwise) and the reviewer is `codex`, but both are
configurable — for example `kimi` + `codex`, or `cline` for every stage via the
`./uncle` launcher. Approved artifacts are SHA-256 pinned
and reviewer-owned files are immutable, so what ships is exactly what was
reviewed.

What makes this different from a generic agent framework:

- **Human approval gates** at every planning and review stage.
- **Adversarial review** by a second model that did not write the code.
- **SHA-256 pinned specs** so approved artifacts cannot be silently modified.
- **Immutable reviewer-owned files** that the implementing agent cannot edit.
- **Speculative execution** that is adopted only if the spec remains
  byte-identical.

Use it when the cost of an agent silently shipping the wrong thing is higher
than the cost of waiting for a human to say yes.

---

## What this does

Stagegate runs one of two pipelines. Both share the same gate model: the
primary agent plans/implements/verifies, the reviewer adversarially audits, and
you approve every gate.

| Workflow | Script | Input | Use case |
|---|---|---|---|
| **New application** | `./scripts/stagegate.sh` | `REQUIREMENTS.md` | Build a new project from a requirements brief. |
| **Change request** | `./scripts/change-workflow.sh` | `CHANGE_REQUEST.md` | Modify an existing codebase with baseline, spec, plan, and audit. |

### New application vs. change request

Use the **new-application** workflow when you are starting from a blank slate
and want the agent to design and build a whole project.

- You write a requirements brief in `REQUIREMENTS.md`.
- The agent creates `REQUIREMENTS_INTERPRETATION.md`, a project plan, an
  adversarial review, an updated plan, and then implements.
- Artifacts are produced in the repository root alongside your source.

Use the **change-request** workflow when you already have a codebase and want
to add a feature, fix a bug, refactor, or otherwise change existing behavior.

- You describe the change in `CHANGE_REQUEST.md`.
- The agent establishes a baseline of current behavior, writes a change spec
  and plan, runs an adversarial review, updates the plan, and implements the
  change.
- The driver records `git diff` as the authoritative change record.

---

## How to run it

### Prerequisites

| Tool | Used for | Check |
|---|---|---|
| Primary agent CLI (default `scripts/agent-kimi.sh`) | planning, implementation, verification stages | `claude --version` (kimi stages use `kimi`) |
| Reviewer CLI (default `codex`) | adversarial review, manual checklist, final audit | `codex --version` |
| `cline` CLI | every stage via the `./uncle` launcher | `cline --version` |
| `jq` | rendering the agent event stream as progress lines | `jq --version` |
| `bash` 3.2+ | the driver (macOS system bash is fine) | `bash --version` |

The reviewer CLI runs with `--sandbox read-only` and `--ephemeral`, so it can
never write source. Primary-agent stages run with an explicit tool allowlist and
never with permission-bypass flags.

Instead of driving a script directly, you can run `./uncle`: set the model,
reasoning effort, and per-stage overrides in its Configure menu (persisted to
`.uncle.config`), then launch a driver.

### Run a new-application build

1. Put the project in this repository. The driver resolves its root from the
   script's own location and `cd`s there, so `prompts/`, `scripts/`, the
   requirements, and the source tree all live together.
2. Write the requirements brief in `REQUIREMENTS.md` under `# Project brief`.
3. Start the pipeline:

   ```sh
   ./scripts/stagegate.sh
   ```

4. Answer the gates. Each gate prints the file to review; open it in another
   terminal, come back, and answer `y` to approve. Anything else declines.

### Run a change request

1. Copy `scripts/`, `prompts/`, `CLAUDE.md`, and `CHANGE_REQUEST.md` into the
   target repository, or run directly if you are already in a checkout that
   contains the workflow files.
2. Fill in `CHANGE_REQUEST.md`. Use `./scripts/from-issue.sh` to seed it from a
   GitHub issue.
3. Commit or stash unrelated work — the driver records `git diff` of the whole
   working tree as the authoritative change record.
4. Start the pipeline:

   ```sh
   ./scripts/change-workflow.sh
   ```

### Start from a GitHub issue

If the request is already in a GitHub issue, seed the right workflow from the
issue number or URL:

```sh
# Defaults to new-app if the repo looks empty, change-request if it looks like
# an existing codebase.
./scripts/from-issue.sh 52638
./scripts/from-issue.sh https://github.com/owner/repo/issues/52638

# Force the mode explicitly:
./scripts/from-issue.sh 52638 --change
./scripts/from-issue.sh https://github.com/owner/repo/issues/52638 --new
```

`--change` writes `CHANGE_REQUEST.md`, then prints it for review and asks you to
type `RUN` exactly. Typing anything else — or sending EOF — leaves
`CHANGE_REQUEST.md` on disk, starts nothing, and prints the command to run
later. That prompt is the human editing window: edit `CHANGE_REQUEST.md` in
another terminal before answering it.

Confirming runs `./scripts/change-workflow.sh` in the same terminal. When that
run reaches `COMPLETE` and its `FINAL_AUDIT.md` verdict is `READY` or `READY
WITH NON-BLOCKING ISSUES`, the originating issue is closed with a comment
pointing at the audit. A `NOT READY` or unparseable verdict, a run that stops at
a gate, a failed driver, or a fetch that fell back to unauthenticated `curl` all
leave the issue open with a message saying why. Closing requires an
authenticated `gh`.

The prompt blocks even when stdin is a pipe — a non-interactive caller of
`--change` waits for the word rather than being auto-declined.

`--change` also binds the checkout to one issue in `.workflow/origin`. Seeding a
different issue while a run is in flight is refused rather than overwriting the
first issue's `CHANGE_REQUEST.md`; finish or reset that run first. Only one
`change-workflow.sh` may run per checkout at a time — a second one refuses to
start and names the process holding `.workflow/lock`.

`--new` writes the project brief to `REQUIREMENTS.md` for
`./scripts/stagegate.sh`. It is unchanged: no prompt, no auto-run, no close.

Both drivers are resumable state machines. Interrupt them and re-run the same
command — they pick up from `.workflow/state`.

---

## Stages, artifacts, and gates

### New application

| # | Stage | Agent | Produces | Gate |
|---|---|---|---|---|
| 1 | Requirements | Primary agent | `REQUIREMENTS_INTERPRETATION.md` | `Y/N` |
| 2 | Project plan | Primary agent | `PROJECT_PLAN.md` | `Y/N` |
| 3 | Adversarial review | Reviewer | `ADVERSARIAL_REVIEW.md` | `Y/N` |
| 4 | Updated plan | Primary agent | `UPDATED_PROJECT_PLAN.md` | `Y/N` |
| 5 | Implementation | Primary agent | source, `IMPLEMENTATION_NOTES.md`, `AUTOMATED_TEST_REPORT.md` | — |
| 6 | Manual checklist | Reviewer | `MANUAL_CHECKLIST.md` | — |
| 7 | Checklist execution | Primary agent | `VERIFICATION_REPORT.md`, `DEFECTS.md` | — |
| 8 | Final audit | Reviewer | `FINAL_AUDIT.md` | — |

`UPDATED_PROJECT_PLAN.md` is the sole plan input to stages 5–8; it must stand
alone, because nothing downstream reads `PROJECT_PLAN.md` or
`ADVERSARIAL_REVIEW.md`.

### Change request

| State | Agent | Produces | Gate |
|---|---|---|---|
| `ANALYZE` | Primary agent | `BASELINE_REPORT.md`, `CHANGE_SPEC.md` | `Y/N` |
| `PLAN` | Primary agent + reviewer | `CHANGE_PLAN.md`, `ADVERSARIAL_REVIEW.md` | `Y/N` |
| `UPDATED_PLAN` | Primary agent | `CHANGE_PLAN.md` (revised in place) | `Y/N` |
| `IMPLEMENT` | Primary agent + reviewer | source, `IMPLEMENTATION_NOTES.md`, `CHANGE_TEST_REPORT.md` | — |
| `CHECKLIST` | Reviewer | `MANUAL_CHECKLIST.md` | — |
| `EXECUTE_CHECKLIST` | Primary agent | `VERIFICATION_REPORT.md`, `DEFECTS.md` | — |
| `FINAL_AUDIT` | Reviewer | `FINAL_AUDIT.md` | — |

`CHANGE_PLAN.md` is the sole plan input to implementation and verification.
The `UPDATED_PLAN` stage answers the adversarial review by editing that file in
place — appending a disposition table and the frozen-scope sections — rather
than writing a second plan that restates the first. The reviewer writes the verification checklist concurrently
during implementation from the frozen, approved artifacts so it cannot race the
primary agent's edits.

Both pipelines end in `READY`, `READY WITH NON-BLOCKING ISSUES`, or `NOT READY`.

Reviewer-owned artifacts (`ADVERSARIAL_REVIEW.md`, `MANUAL_CHECKLIST.md`,
`FINAL_AUDIT.md`) are never edited by the primary agent.

---

## How the gates work

An approval records the SHA-256 of the exact bytes you read, in
`.workflow/approvals/`. Downstream stages re-hash the file and refuse to run if
it changed. Edit an approved document and the pipeline stops until you approve
it again.

A gate prompt names the action and the file(s) it covers and ends with `[Y/N]`.
Only `y` or `Y` approves; anything else — including `n`, an empty line, a
leading space, or closed stdin — pauses the workflow and exits cleanly. State is
preserved, so re-running resumes at the same gate.

While you read a gated document, the driver starts the *next* stage in the
background (speculative execution). The result is adopted only if the file is
byte-identical when you approve; any edit during review discards that work and
the stage replays. Implementation is never speculated — it may not begin before
the approved updated plan (`UPDATED_PROJECT_PLAN.md` or the revised
`CHANGE_PLAN.md`) is in place.

Disable it with `WORKFLOW_SPECULATE=0` if you routinely edit documents mid-review
or want strictly serial token spend.

---

## Configuration

All settings are environment variables. For `stagegate.sh`, stage keys are
the log names: `REQUIREMENTS`, `PROJECT_PLAN`, `ADVERSARIAL_REVIEW`,
`UPDATED_PLAN`, `IMPLEMENTATION`, `MANUAL_CHECKLIST`, `EXECUTE_CHECKLIST`,
`FINAL_AUDIT`.

| Variable | Default | Effect |
|---|---|---|
| `WORKFLOW_SPECULATE` | `1` | Run the next stage during a gate |
| `WORKFLOW_AGENT_CMD` | `scripts/agent-kimi.sh` | Primary agent CLI or wrapper |
| `WORKFLOW_REVIEWER_CMD` | `codex` | Reviewer CLI or wrapper |
| `WORKFLOW_MODEL_<STAGE>` | `opus`; `sonnet` for requirements and checklist execution | Model for one stage |
| `WORKFLOW_EFFORT_<STAGE>` | `high`; `medium` for those two | Reasoning effort |
| `WORKFLOW_TURNS_<STAGE>` | `40`; `200` implementation, `120` checklist execution | Turn cap |
| `WORKFLOW_TOOLS_<STAGE>` | `Read,Glob,Grep,Write` (+ `Edit,TodoWrite,Bash` for implementation and checklist execution) | Tool allowlist |
| `CODEX_MODEL` | Codex default | Model for all reviewer stages |

Example:

```sh
WORKFLOW_MODEL_REQUIREMENTS=opus WORKFLOW_TURNS_IMPLEMENTATION=300 \
  ./scripts/stagegate.sh
```

Use a different primary agent or reviewer by setting the command variables:

```sh
WORKFLOW_AGENT_CMD=kimi WORKFLOW_REVIEWER_CMD=codex \
  ./scripts/stagegate.sh
```

The swapped CLI must accept the same flags the driver passes. If the flags
differ, provide a wrapper script that translates them and set the variable to
that wrapper's path.

`change-workflow.sh` has additional knobs for per-stage dollar budgets and
parallel checklist generation. Defaults and documentation are in the header of
`scripts/change-workflow.sh`. One more it is worth knowing about:

| Variable | Default | Effect |
|---|---|---|
| `WORKFLOW_CLOSE_ISSUE` | `1` | `0` stops `change-workflow.sh` from closing the originating issue at `COMPLETE` |

---

## State and logs

Everything under `.workflow/` is gitignored:

```
.workflow/state              current stage, as <STAGE> or <issue>:<STAGE>
.workflow/approvals/*.sha256 recorded approvals
.workflow/logs/*.jsonl       raw primary-agent event streams
.workflow/logs/*.log         reviewer transcripts, speculative stage output
.workflow/speculative/       input hashes for speculative stages (stagegate.sh)
.workflow/cost.tsv           per-stage spend ledger (change-workflow.sh)
.workflow/change.diff        authoritative diff the final audit reads (change-workflow.sh)
.workflow/issue-closed       which run closed the originating issue (change-workflow.sh)
```

To redo a stage, write its name into `.workflow/state` and re-run. A bare stage
name is always accepted; `change-workflow.sh` adds the `<issue>:` prefix itself
when it knows which issue it is working on, and the prefix is informational —
`.workflow/origin` remains the only thing that decides issue ownership. To start
over, delete `.workflow/` and the generated `*.md` artifacts.

---

## Troubleshooting

- **"Stage produced no artifact"** — check the log for `[tool ERROR]`; a denied
  `Write` is the usual cause. State did not advance, so re-running replays the
  stage.
- **`[done] error_max_turns`** — raise `WORKFLOW_TURNS_<STAGE>`.
- **"changed after approval"** — the file was edited post-approval; approve it
  again.
- **No output for a long stretch** — implementation legitimately runs long;
  tail `.workflow/logs/implementation.jsonl`.

---

## Manual helpers

`scripts/workflow.sh` (`approve-plan`, `approve-review`,
`approve-updated-plan`, `status`), `scripts/codex-review-plan.sh`, and
`scripts/codex-create-checklist.sh` drive the same gates by hand. They predate
the unified driver and record approvals in the same place; use them only when
running stages piecemeal.

See [`scripts/README.md`](scripts/README.md) for the exact invocation syntax
of all six scripts.

---

## Documentation

- [`QUICK_START.md`](QUICK_START.md) — run the workflows end-to-end in a few
  minutes.
- [`AGENTIC.md`](AGENTIC.md) — the design philosophy behind the gates.
- [`CLAUDE.md`](CLAUDE.md) — the agent instruction contract.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — the contributor guide.
- [`GOOD_FIRST_ISSUES.md`](GOOD_FIRST_ISSUES.md) — small, well-scoped starter
  tasks.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — before participating.

Open an issue to discuss larger changes before spending time on them.
