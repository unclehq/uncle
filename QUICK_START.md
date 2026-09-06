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
| New app | Requirements → Plan → Adversarial review → Updated plan → Implementation → **Review the code** → Manual checklist → Execution → Final audit |
| Change request | Analyze → Plan → Adversarial review → Updated plan → Implement → **Review the code** → Checklist → Execution → Final audit |

At each gate, open the listed file, read it, and answer `y` to approve.

The gate after implementation is the one that shows you code. Open
`.workflow/IMPLEMENTATION_REVIEW.md`: it holds the diff, the result of the
driver re-running your project's own test commands, and the agent's notes.

If those commands passed before the change and fail now, the gate says so and
asks you to *override* rather than approve. The run also stops before
`COMPLETE` if the final audit did not say the change is ready.

## 4. Reading the result

When the driver reaches `COMPLETE`, read in this order:

1. `FINAL_AUDIT.md` — ends with `READY`, `READY WITH NON-BLOCKING ISSUES`, or
   `NOT READY`. Only the first two reach `COMPLETE` on their own; anything else
   needs a recorded human override, which the final summary reports.
2. `VERIFICATION_REPORT.md` — what was actually run.
3. Test report (`AUTOMATED_TEST_REPORT.md` or `CHANGE_TEST_REPORT.md`).
4. The source diff or implementation notes.

## 5. Resume or reset

The workflow is stateful:

```sh
# Resume after an interruption
./scripts/stagegate.sh

# Restart a specific stage
echo REQUIREMENTS > .workflow/state

# Send a rejected implementation back to be redone
echo IMPLEMENT > .workflow/state
./scripts/stagegate.sh

# Full reset
rm -rf .workflow
```

See [`README.md`](README.md) for full configuration options and
[`CONTRIBUTING.md`](CONTRIBUTING.md) if you want to improve the project.
