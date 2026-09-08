# Quick start

This guide gets you from zero to a running workflow in a few minutes.

## Prerequisites

- `cline` CLI (for the `./uncle` launcher), or `claude` + `kimi` (the
  `scripts/agent-kimi.sh` default) — or set `WORKFLOW_AGENT_CMD` to any compatible CLI
- `codex` CLI (or set `WORKFLOW_REVIEWER_CMD` to a compatible alternative)
- `jq`
- `bash` 3.2+

Run `./uncle` to pick a workflow and set the model, reasoning effort, and
per-stage overrides from a menu instead of calling a driver directly.

## 1. New application

Write a project brief in `REQUIREMENTS.md` under `# Project brief`, then run:

```sh
./scripts/stagegate.sh
```

The driver stops at each gate and asks you to approve the produced document.
Answer `y` to continue; anything else pauses the workflow.

### Start from a GitHub issue

```sh
./scripts/from-issue.sh https://github.com/owner/repo/issues/123 --new
./scripts/stagegate.sh
```

## 2. Change request in an existing repo

Copy the workflow files into the target repository:

```sh
TEMPLATE=/path/to/stagegate
cp -R "$TEMPLATE/prompts" .
cp -R "$TEMPLATE/scripts" .
cp "$TEMPLATE/CLAUDE.md" .
cp "$TEMPLATE/CHANGE_REQUEST.md" .
chmod +x scripts/*.sh
```

Fill in `CHANGE_REQUEST.md`, commit or stash unrelated work, then run:

```sh
./scripts/change-workflow.sh
```

### Start from a GitHub issue

```sh
./scripts/from-issue.sh https://github.com/owner/repo/issues/123 --change
./scripts/change-workflow.sh
```

## 3. What happens next

The workflow runs stages and pauses at gates:

| Pipeline | Stages |
|---|---|
| New app | Requirements → Plan → Adversarial review → Updated plan → Prerequisites → Implementation → **Review the code** → Test review → Manual checklist → Execution → Final audit |
| Change request | Analyze → Plan → Adversarial review → Updated plan → Implement → **Review the code** → Checklist → Execution → Final audit |

At each gate, open the listed file, read it, and answer `y` to approve.

The gate after implementation is the one that shows you code. Open
`.uncle/workflow/IMPLEMENTATION_REVIEW.md`: it holds the diff, the result of the
driver re-running your project's own test commands, and the agent's notes.

If those commands passed before the change and fail now, the gate says so and
asks you to *override* rather than approve. The run also stops before
`COMPLETE` if the final audit did not say the change is ready.

For a new application, inspect `PREFLIGHT_REPORT.md` if prerequisites block
implementation, and `TEST_REVIEW.md` if tests need correction. Required checks
marked BLOCKED or NOT RUN pause execution; resolve the missing prerequisite
and rerun. Failed reviews or checks enter repair and return to the code gate.
The default limit is two repair attempts across restarts. After inspecting an
unresolved defect, set `WORKFLOW_MAX_REPAIRS=3` (for example) to permit one more.

The updated plan must list the complete automated acceptance commands and
`Protected verification paths`: tests, fixtures, helpers, and test configuration.
Verification cannot change those inputs and still pass. Test corrections belong
in repair, with a documented reason and renewed review.

## 4. Reading the result

When the driver reaches `COMPLETE`, read in this order:

1. `FINAL_AUDIT.md` — ends with `READY`, `READY WITH NON-BLOCKING ISSUES`, or
   `NOT READY`. Only the first two reach `COMPLETE` on their own; anything else
   needs a recorded human override, which the final summary reports.
2. `VERIFICATION_REPORT.md` — what was actually run.
3. Test report (`AUTOMATED_TEST_REPORT.md` or `CHANGE_TEST_REPORT.md`).
4. The source diff or implementation notes.

## 5. Resume or reset

To see where the current project's run spends time, run `uncle --performance`.
It lists completed attempts, approval waits, and available token usage. Timing
for overlapping work is not additive. New records are collected by default;
earlier runs are not retrospectively estimated.

The workflow is stateful:

```sh
# Resume after an interruption
./scripts/stagegate.sh

# Restart a specific stage
echo REQUIREMENTS > .uncle/workflow/state

# Send a rejected implementation back to be redone
echo IMPLEMENT > .uncle/workflow/state
./scripts/stagegate.sh

# Full reset
rm -rf .uncle/workflow
```

See [`README.md`](README.md) for full configuration options and
[`CONTRIBUTING.md`](CONTRIBUTING.md) if you want to improve the project.
