#!/usr/bin/env bash
# One isolated implementation worker for supervised parallel execution.
# It deliberately receives only a fixed driver-built prompt and stage flags;
# scheduling, merge and deletion stay in the parent driver.
set -euo pipefail

step="${1:?implementation step number required}"
# Prompts live in the driver-owned workflow tree, which is intentionally not
# copied into every sandbox.  An absolute handoff path keeps the worker's
# instruction immutable and avoids a missing-prompt failure in copy mode.
prompt="${PARALLEL_PROMPT_DIR:-.uncle/workflow/parallel/prompts}/step-$step.md"
[[ -s "$prompt" ]] || { echo "parallel worker prompt missing: $prompt" >&2; exit 2; }
[[ -n "${PARALLEL_AGENT_CMD:-}" ]] || { echo 'parallel worker agent command missing' >&2; exit 2; }

export UNCLE_PROJECT_ROOT="$PWD"
export UNCLE_CONFIG="$PWD/.uncle/config"
export UNCLE_RUNNER_REUSE=0
# Every isolated worker reports itself independently to the TUI.  Without
# this, the parent scheduler is visibly active but its concurrent children
# appear to do nothing until the whole group has merged.
export UNCLE_STATUS_STAGE="implementation-step-$step"
export UNCLE_STATUS_STAGE_TURNS="${PARALLEL_AGENT_TURNS:-50}"
args=(-p --max-turns 50 --output-format stream-json --verbose --strict-mcp-config
      --exclude-dynamic-system-prompt-sections --allowedTools "${PARALLEL_AGENT_TOOLS:-}")
[[ -z "${PARALLEL_AGENT_MODEL:-}" ]] || args+=(--model "$PARALLEL_AGENT_MODEL")
[[ -z "${PARALLEL_AGENT_EFFORT:-}" ]] || args+=(--effort "$PARALLEL_AGENT_EFFORT")
[[ -z "${PARALLEL_AGENT_BUDGET:-}" ]] || args+=(--max-budget-usd "$PARALLEL_AGENT_BUDGET")

exec "$PARALLEL_AGENT_CMD" "${args[@]}" < "$prompt"
