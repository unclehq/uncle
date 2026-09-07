#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
    -h|--help) echo 'Usage: performance-report.sh [project-directory]'; exit 0 ;;
esac
[[ $# -le 1 ]] || { echo 'Expected at most one project directory.' >&2; exit 1; }
dir="${1:-.}/.uncle/workspace/metrics"
if [[ ! -d "$dir" ]]; then
    echo 'No performance records yet. Run a workflow with WORKFLOW_METRICS=1.'
    exit 0
fi
# find includes atomic .pending.*.json records, but never incomplete files.
find "$dir" -name '*.json' -type f -exec cat {} + | jq -s -r --arg estimates "${WORKFLOW_SHOW_COST_ESTIMATES:-0}" '
    def known: map(select(type == "number")) | if length == 0 then "Unavailable" else (add|tostring) end;
    def money: map(select(type == "number")) | if length == 0 then "Unavailable" else ((add * 1000000 | round) / 1000000 | tostring) end;
    def cell: tostring | gsub("\\|"; "&#124;") | gsub("[\\r\\n]"; " ");
    def token_total:
        if (.reported_total_tokens|type) == "number" then .reported_total_tokens
        elif ([.input_tokens,.output_tokens]|all(type == "number")) then
            if (.input_includes_cache or ((.runner // "") | test("(agent|reviewer)-cline[.]sh$"))) then .input_tokens + .output_tokens
            elif ([.cache_read_tokens,.cache_write_tokens]|all(type == "number")) then
                .input_tokens + .output_tokens + .cache_read_tokens + .cache_write_tokens
            else null end
        else null end;
    "| Kind | Stage | Attempts | Work seconds | Usage reports | Input tokens | Output tokens | Cache read | Cache write | Total tokens | Total coverage | Reported USD | Cost coverage |" + (if $estimates == "1" then " Estimated USD |" else "" end),
    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|" + (if $estimates == "1" then "---:|" else "" end),
    (group_by([.kind,.stage]) | sort_by(map(.elapsed_seconds)|add) | reverse[]
     | (.[0].kind == "agent" or .[0].kind == "reviewer") as $model_stage
     | "| \(.[0].kind|cell) | \(.[0].stage|cell) | \(length) | \(map(.elapsed_seconds)|add) | \(map(select(.input_tokens != null or .output_tokens != null or .reported_total_tokens != null))|length)/\(length) | \(if $model_stage then map(.input_tokens)|known else "N/A" end) | \(if $model_stage then map(.output_tokens)|known else "N/A" end) | \(if $model_stage then map(.cache_read_tokens)|known else "N/A" end) | \(if $model_stage then map(.cache_write_tokens)|known else "N/A" end) | \(if $model_stage then map(token_total)|known else "N/A" end) | \(map(select((token_total|type)=="number"))|length)/\(length) | \(if $model_stage then map(.reported_cost_usd)|money else "N/A" end) | \(map(select(.reported_cost_usd != null))|length)/\(length) |" + (if $estimates == "1" then " \(if $model_stage then map(.estimated_cost_usd)|money else "N/A" end) |" else "" end)),
    "",
    "Unavailable means the runner did not supply the value. N/A means a non-model step, such as approval or a shell check.",
    "Total tokens include cached tokens once. Coverage shows attempts with a complete total; subtotals can be partial when coverage is incomplete.",
    "Reported USD excludes estimates. Unavailable cost does not mean free. Set WORKFLOW_SHOW_COST_ESTIMATES=1 to display separate API-price estimates.",
    "Work seconds overlap for concurrent stages; do not sum them as end-to-end latency. Counts cover completed attempts; killed attempts may be absent."
'
