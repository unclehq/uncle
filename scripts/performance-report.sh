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
find "$dir" -name '*.json' -type f -exec cat {} + | jq -s -r '
    def known: map(select(type == "number")) | if length == 0 then "—" else (add|tostring) end;
    def cell: tostring | gsub("\\|"; "&#124;") | gsub("[\\r\\n]"; " ");
    "| Kind | Stage | Attempts | Work seconds | Usage reports | Input tokens | Output tokens | Reported total tokens |",
    "|---|---|---:|---:|---:|---:|---:|---:|",
    (group_by([.kind,.stage]) | sort_by(map(.elapsed_seconds)|add) | reverse[]
     | "| \(.[0].kind|cell) | \(.[0].stage|cell) | \(length) | \(map(.elapsed_seconds)|add) | \(map(select(.input_tokens != null or .output_tokens != null or .reported_total_tokens != null))|length)/\(length) | \(map(.input_tokens)|known) | \(map(.output_tokens)|known) | \(map(.reported_total_tokens)|known) |"),
    "",
    "Work seconds overlap when stages/checks run concurrently; do not add them as end-to-end latency.",
    "Tokens are runner-reported values, not estimates. Missing usage is unknown; cache counts remain separate in the JSON records.",
    "Reported totals are an alternative view, not extra tokens to add to input/output. Shell timings have one-second resolution.",
    "Records include completed attempts across restarts. Killed attempts may be absent; raw logs can be overwritten by later attempts."
'
