# Change Request

## Change Type

Feature

## Summary

Show kimi stage costs in the live status bar and stage reports as labeled
estimates, instead of "Unavailable". Extend the pricing table to the models
actually in use (kimi-k3 included).

## Motivation

On a kimi-driven run every stage shows "Cost: Unavailable" while it works and
"cost unknown" when it ends, even though uncle already recovers the token
counts and already computes dollar estimates for the metrics record. The
operator cannot see what a long stage is costing until the run is over, and
even then only in the session-totals "projected" line. For kimi-k3 runs not
even that exists: the model has no entry in the rate table, so estimates come
back "unknown".

Observed 2026-09-08 on a real run: a 15-minute implementation stage that
failed reported "error_during_execution — 1 turns, 0s" with cost unknown,
and the preflight stage (3,981,946 tokens) showed Cost Unavailable
throughout.

## Observed Current Behavior

- The kimi CLI reports no dollar figures anywhere. Its stream-json output has
  no result/usage event, and its local session records
  (`~/.kimi-code/sessions/*/agents/*/wire.jsonl`, `usage.record` events)
  carry only token buckets (`inputOther`, `output`, `inputCacheRead`,
  `inputCacheCreation`). Verified by inspection 2026-09-08.
- `scripts/agent-kimi.sh` recovers tokens post-hoc by diffing local session
  state (`scripts/lib/kimi-usage.py`) and synthesizes the stage `result`
  with `total_cost_usd: null` (`scripts/agent-kimi.sh:198`). The TUI renders
  a null cost as "Unavailable" (`uncle_tui.py:1605`).
- Estimates exist but only after the fact: `scripts/lib/usage-cost.py`
  `enrich()` attaches `estimated_cost_usd` with `cost_status: "estimated"`
  to metrics rows. They surface in the session totals ("Reported +
  projected") and in `uncle --performance` only when
  `WORKFLOW_SHOW_COST_ESTIMATES=1` is set.
- `RATES` in `usage-cost.py` covers only `moonshot-ai/kimi-k2.7-code` and
  `moonshot-ai/kimi-k2.7-code-highspeed` (official page verified 2026-09-07).
  kimi-k3, which current runs use, has no rates, so no estimate is produced.
- The cline driver with bring-your-own kimi models (e.g. cline running
  `moonshot-ai/kimi-k3`) also yields null cost from cline's `totalCost`, so
  those stages show "Unavailable" too.

## Desired Behavior

- During a kimi stage, the status bar shows a live, clearly labeled estimate
  (e.g. `~$0.0123 est`), priced from the token buckets `publish_usage` in
  `agent-kimi.sh` already pushes to the status file every 10 seconds.
- Stage results and metrics rows carry `estimated_cost_usd` with
  `cost_status: "estimated"` consistently, and every surface that prints
  money (TUI status bar, stage report, `--performance`) distinguishes
  estimates from reported dollars.
- The rate table (or a shipped `WORKFLOW_PRICING_FILE` default) covers
  kimi-k3, with rates re-verified against the official pricing page at
  implementation time and `pricing_checked_at` updated.
- Reported dollars stay authoritative: when a runner supplies
  `total_cost_usd`, it displays exactly as today with no "est" marker.

## Reproduction

Not applicable (feature). To see the current gap: run any kimi-driven stage
and watch the status bar — tokens accumulate while Cost reads "Unavailable".

## Constraints

- Never present an estimate as billed or reported cost
  (`scripts/lib/usage-cost.py` docstring rule). Estimates must be visibly
  labeled on every surface.
- Rates must come from the official Kimi pricing page (or the operator's
  `WORKFLOW_PRICING_FILE` override, which must keep working and keep winning
  over built-in rates).
- Live usage is session-diff based and arrives in 10-second batches; the
  display must tolerate partial/absent data without erroring, and a stage
  with no recoverable usage still shows "Unavailable".
- No network calls in the status or render path; pricing is arithmetic over
  already-collected numbers.
- Do not relax the missing-`result`-event stage-failure semantics in the
  drivers; the kimi shim's synthesized result stays mandatory.

## Known Relevant Files

- `scripts/agent-kimi.sh` — `publish_usage` (line 97), result synthesis
  (line 195)
- `scripts/lib/kimi-usage.py` — token recovery from local sessions
- `scripts/lib/usage-cost.py` — `RATES`, `enrich()`
- `uncle_tui.py` (lines 1590–1690) — status bar rendering, "Unavailable"
- `scripts/change-workflow.sh` — `record_cost`, session totals
- `scripts/performance-report.sh` — estimates display gate
- `scripts/backfill-kimi-costs.py` — historical-row repair
- `scripts/agent-cline.sh` — only if the cline + BYO-model case is taken on
- Tests: `scripts/tests/agent-kimi-test.sh`, `usage-cost-test.py`,
  `kimi-cost-integration-test.sh`, `session-totals-test.py`,
  `tui-session-panel-test.sh`

## Out of Scope

- Changing the kimi CLI itself, or reconciling against actual billing; no
  invoice-grade cost exists to recover.
- Reported-cost handling for claude/codex runners (already works).
- Cline-driver cost estimation for bring-your-own models: same display rules
  apply if `estimated_cost_usd` is present, but pricing cline-side usage is a
  separate change unless folded in explicitly.
- `reviewer-kimi.sh` beyond sharing the same library code paths.

## Success Criteria

- A kimi stage displays a labeled live estimate in the status bar no later
  than the first usage publish, and the estimate grows with token accrual.
- At stage end, the stage report and session totals show the estimated cost
  marked as estimated; `--performance` shows it without requiring the
  opt-in env var, still labeled.
- A kimi-k3 stage produces an estimate (rate table or override present).
- A stage whose usage cannot be recovered still shows "Unavailable", not a
  crash or a $0.0000.
- Reported-cost runners render byte-identical output to before the change.
- New/updated fixture tests cover the shim publish path, TUI rendering of
  estimates, and the rate table; existing shim, cost, and TUI suites pass.
