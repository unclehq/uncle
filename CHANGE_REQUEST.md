# Change Request

## Change Type

Feature

## Summary

Extend token-price cost estimation beyond Kimi models so stages running on
`x-ai/grok-4.5` — and future non-Kimi models — get labeled cost estimates
instead of "Unavailable".

## Motivation

After the kimi-k3 change, a typical run shows estimates on the Kimi stages and
"Unavailable" on the rest. In practice that is half the pipeline: the
resume_viewer config (`.uncle/config`) runs adversarial-review,
updated-change-plan, implementation, and manual-checklist on `x-ai/grok-4.5`
via the cline driver — including implementation, the longest and most
expensive stage. A cost panel that is blind to exactly the stages that cost
the most still is not a cost picture.

## Observed Current Behavior

- `RATES`/`SOURCES` in `scripts/lib/usage-cost.py` cover only
  `moonshot-ai/*` models, sourced from the official Kimi pricing pages.
  `enrich()` returns `cost_status: "unknown"` for everything else, so
  grok-4.5 stages render "Unavailable" in the TUI, metrics, and
  `--performance`.
- The escape hatch exists (`WORKFLOW_PRICING_FILE`, README.md:410) but makes
  every operator hand-maintain rates for models uncle could ship.
- Public pricing is verifiable: the OpenRouter models API
  (`https://openrouter.ai/api/v1/models`, fetched 2026-09-09) lists
  `x-ai/grok-4.5` at $2/1M input, $6/1M output, $0.30/1M cache read —
  **with a tier override: prompts ≥200k tokens bill at $4/1M input, $12/1M
  output, $0.60/1M cache read.** The same API cross-checks kimi-k3 at
  $3/$15/$0.30, matching the official Kimi page already in `RATES`.
- Two complications the flat `RATES` schema does not currently handle:
  1. **Tiered pricing.** grok-4.5 doubles above 200k prompt tokens. Workflow
     stages routinely exceed that (a real preflight stage: ~4M tokens). Flat
     base rates would underestimate long stages 2×; flat tier rates would
     overestimate short ones 2×.
  2. **Billing path is unconfirmed.** The config's model ids mix conventions
     (`x-ai/grok-4.5` is OpenRouter spelling; `moonshot-ai/kimi-k3` is not).
     Whether cline bills these via OpenRouter, xAI/Moonshot direct, or cline
     credits determines which price list is the truthful estimate source, and
     the markup differs.
- `cline-pass/*` models (cline subscription) are per-plan, not per-token;
  estimating them at API list prices would be fiction.

## Desired Behavior

- `x-ai/grok-4.5` stages show labeled `est` costs in the TUI status bar,
  metrics rows, and `--performance`, same labeling rules as the Kimi models.
- The pricing schema can represent the ≥200k-token tier, or the
  implementation documents why it does not and picks a defensible single rate
  (e.g. always the base rate, with the underestimate called out on the
  surface). A schema that silently misprices 4M-token stages is worse than no
  new rates.
- Before rates are baked in, the implementation confirms the actual billing
  path for `x-ai/*` and `moonshot-ai/*` ids in cline (OpenRouter vs provider
  direct vs cline credits) and sources rates from that path. If it cannot be
  confirmed, ship a documented `WORKFLOW_PRICING_FILE` template for grok-4.5
  instead of baked rates — an explicit operator-set rate beats a wrong one.
- `SOURCES` generalizes to non-Kimi providers; each entry keeps its own
  source URL and `pricing_checked_at`.
- `cline-pass/*` and other subscription models remain unestimated by default;
  `WORKFLOW_PRICING_FILE` remains the opt-in for those.

## Reproduction

Not applicable (feature). To see the gap: run any stage on `x-ai/grok-4.5`
and watch the cost cell stay "Unavailable" while a kimi-k3 stage estimates.

## Constraints

- Never present an estimate as billed or reported cost; the `est` label rules
  from the kimi change apply unchanged.
- Rates must carry a source URL and verification date, and must match the
  billing path cline actually uses, not just any public price list.
- Model ids in `RATES` must match what the runner reports in usage events
  verbatim (`x-ai/grok-4.5`, not `x-ai/grok-4.5-turbo` or an OpenRouter
  alias).
- No network calls in the status, render, or metrics path.
- Do not change the behavior of `FREE_MODEL_IDS` (reported $0 on a free model
  is a fact, not an unknown).

## Known Relevant Files

- `scripts/lib/usage-cost.py` — `RATES`, `SOURCES`, `enrich()`; the tier
  question lives here
- `uncle_tui.py` — `_live_cost` (line ~1580), `FREE_MODEL_IDS` (line 177),
  cost labeling (line ~1640)
- `README.md` (line ~410) — `WORKFLOW_PRICING_FILE` documentation
- `scripts/performance-report.sh` — Estimated USD column
- `.uncle/config` in consuming projects — stage → model/billing mapping
  (evidence for which models matter)
- Tests: `scripts/tests/usage-cost-test.py`,
  `scripts/tests/tui-session-panel-test.sh`,
  `scripts/tests/performance-test.sh`,
  `scripts/tests/kimi-cost-integration-test.sh`

## Out of Scope

- Changing cline or OpenRouter; reconciling against actual invoices.
- Kimi models (covered by the previous change).
- `cline-pass/*` subscription pricing semantics.
- Tier/threshold pricing for models other than grok-4.5 unless the schema
  work makes it free.

## Success Criteria

- A stage running `x-ai/grok-4.5` shows a labeled live estimate in the status
  bar and an `est` cost line in the stage panel; metrics rows carry
  `estimated_cost_usd`, `cost_status: "estimated"`, a grok-appropriate
  `pricing_source`, and a current `pricing_checked_at`.
- A stage whose prompt exceeds 200k tokens is priced per the implementation's
  documented tier decision, with a test pinning that decision.
- Kimi model estimates are byte-identical to before the change.
- `cline-pass/*` stages still show "Unavailable" unless a pricing file
  provides rates.
- New/updated tests cover the grok rates, the tier behavior, and the
  id-verbatim requirement; existing cost/TUI suites pass.
