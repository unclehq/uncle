#!/usr/bin/env bash
# One atomic record per completed attempt, safe for concurrent/speculative
# stages. Observability must not change the outcome of a workflow.
perf_record() (
    [[ "${WORKFLOW_METRICS:-1}" == 1 && -n "${STATE_DIR:-}" ]] || exit 0
    local kind="$1" stage="$2" elapsed="$3" status="$4"
    local log="${5:-/dev/null}" runner="${6:-}" model="${7:-}" effort="${8:-}"
    local dir="$STATE_DIR/metrics" tmp
    mkdir -p "$dir" || exit 0
    tmp="$(mktemp "$dir/.pending.XXXXXX")" || exit 0
    [[ -f "$log" ]] || log=/dev/null
    if jq -R -s -c --arg kind "$kind" --arg stage "$stage" \
        --arg runner "$runner" --arg model "$model" --arg effort "$effort" \
        --arg log "$log" --arg state "${state:-}" \
        --argjson elapsed "$elapsed" --argjson exit_code "$status" \
        --argjson ended "$(date +%s)" \
        --argjson speculative "${UNCLE_SPECULATIVE:-false}" '
        [split("\n")[] | fromjson? | select(type == "object" and .type == "result")] as $results
        | ($results[-1] // {}) as $r
        | [scan("tokens used[\\r\\n ]+([0-9,]+)") | .[0] | gsub(","; "") | tonumber] as $totals
        | {schema:1, kind:$kind, stage:$stage, workflow_state:$state,
           runner:$runner, model:$model, effort:$effort, speculative:$speculative,
           ended_at:$ended, started_at:($ended-$elapsed), elapsed_seconds:$elapsed,
           process_exit:$exit_code, reported_error:$r.is_error,
           turns:($r.num_turns // null), input_tokens:($r.usage.input_tokens // null),
           output_tokens:($r.usage.output_tokens // null),
           reported_total_tokens:($r.usage.total_tokens // $totals[-1] // null),
           cache_read_tokens:($r.usage.cache_read_input_tokens // $r.usage.cached_input_tokens // null),
           cache_write_tokens:($r.usage.cache_creation_input_tokens // $r.usage.cache_write_input_tokens // null),
           reported_cost_usd:($r.total_cost_usd // null),
           usage_scope:"last reported result", log:$log}
    ' "$log" > "$tmp"; then
        mv "$tmp" "$tmp.json"
    else
        rm -f "$tmp"
    fi
    exit 0
)
