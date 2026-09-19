#!/usr/bin/env bash
# One isolated implementation worker for supervised parallel execution.
# It deliberately receives only a fixed driver-built prompt and stage flags;
# scheduling, merge and deletion stay in the parent driver.
set -euo pipefail

step="${1:?implementation step number required}"
prompt=".uncle/workflow/parallel/prompts/step-$step.md"
[[ -s "$prompt" ]] || { echo "parallel worker prompt missing: $prompt" >&2; exit 2; }
[[ -n "${PARALLEL_AGENT_CMD:-}" ]] || { echo 'parallel worker agent command missing' >&2; exit 2; }

export UNCLE_PROJECT_ROOT="$PWD"
export UNCLE_CONFIG="$PWD/.uncle/config"
export UNCLE_RUNNER_REUSE=0
args=(-p --max-turns 50 --output-format stream-json --verbose --strict-mcp-config
      --exclude-dynamic-system-prompt-sections --allowedTools "${PARALLEL_AGENT_TOOLS:-}")
[[ -z "${PARALLEL_AGENT_MODEL:-}" ]] || args+=(--model "$PARALLEL_AGENT_MODEL")
[[ -z "${PARALLEL_AGENT_EFFORT:-}" ]] || args+=(--effort "$PARALLEL_AGENT_EFFORT")
[[ -z "${PARALLEL_AGENT_BUDGET:-}" ]] || args+=(--max-budget-usd "$PARALLEL_AGENT_BUDGET")

exec "$PARALLEL_AGENT_CMD" "${args[@]}" < "$prompt"
