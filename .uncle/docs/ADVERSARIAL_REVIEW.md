## AR-001: The chat fallback names only the old `Preview:` label, leaving behavior for the newly required `Local preview:` output u

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-3 requires local URLs to use `Local preview:`, but AC-5 and SB-6 require the no-link response only for local `Preview:` lines; CHANGE_PLAN.json §1-3 repeats the relabel without extending that fallback. Explicitly cover both labels in rule 5 and its checker so the normal local output receives the required response.
- Failure: The chat fallback names only the old `Preview:` label, leaving behavior for the newly required `Local preview:` output unspecified. Add: “When only local preview links are available under either `Preview:` or `Local preview:`, say no link was provided.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The planned live-server fixture cannot prove hosted mode prevents server creation because existing guards already suppre

- Severity: MEDIUM
- References: CHANGE_PLAN.json §16–17 specifies a live preview-server fixture with a start spy; supplied headless_preview.py:165–167 and :181–182 already bypass starting when a server is alive. AC-2 requires hosted suppression of both entry points, so separate eligible fixtures without a live server are needed to detect regressions in that behavior.
- Failure: The planned live-server fixture cannot prove hosted mode prevents server creation because existing guards already suppress it. Add: “For each hosted flag, test poll() and finish() with an eligible app, an available page, no live server, and a start spy; assert no start and finish()==[].”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The hosted start-suppression test can pass without the new guard.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §16-17 combines a live preview-server fixture with the no-start spy assertion; scripts/lib/headless_preview.py:165-167 and :181-182 already suppress starts when a server is alive. Keep the live-server fixture for announcement suppression, but require separate eligible no-server fixtures to make AC-2 fail before the change.
- Failure: The hosted start-suppression test can pass without the new guard. Add: "Test poll() and finish() for each hosted flag with an otherwise eligible app, an available page, and no live server; assert no start calls and finish()==[], with a non-hosted control that starts successfully."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
