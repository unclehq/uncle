## AR-001: Unspecified: a configured runner not installed (and not self-hosted) when nothing is installed; C4 vs V1 can diverge.

- Severity: HIGH
- References: CHANGE_SPEC C4 and V1; CHANGE_PLAN section 1 (stage_runner logic untouched).
- Failure: Unspecified: a configured runner not installed (and not self-hosted) when nothing is installed; C4 vs V1 can diverge. Say: 'With no runner installed runners_for returns ["self-hosted"]; stage_runner still returns a configured runner or DEFAULT_RUNNER if set, even if absent from runners_for.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: AC-3 says opencode maps to self-hosted, but duplicates and the opencode-only case are unspecified.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3; CHANGE_PLAN section 16 (AC-3 case covers claude and opencode only).
- Failure: AC-3 says opencode maps to self-hosted, but duplicates and the opencode-only case are unspecified. Say: 'With only opencode on PATH, runners_for returns ["self-hosted"] once; self-hosted never appears twice.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Unspecified whether the fallback is independent per side (agent/reviewer) and exempt from any distinct-runner rule.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 ('both agent and reviewer sides'); CHANGE_PLAN section 1.
- Failure: Unspecified whether the fallback is independent per side (agent/reviewer) and exempt from any distinct-runner rule. Say: 'The fallback applies independently per side; no agent-reviewer distinctness rule filters it.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The unreachable 'No agents installed' label conflicts with the description text seeing the fallback; the no-runner descr

- Severity: MEDIUM
- References: CHANGE_PLAN section 6 (label at line 1297 unreachable) vs section 1.
- Failure: The unreachable 'No agents installed' label conflicts with the description text seeing the fallback; the no-runner description text is unspecified. Say: 'With no runners installed the description lists "Self hosted" and never shows "No agents installed".'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: V1 'never empty' is unscoped, yet section 22 admits the supervision picker may stay empty.

- Severity: LOW
- References: CHANGE_SPEC V1 and assumptions; CHANGE_PLAN section 22.
- Failure: V1 'never empty' is unscoped, yet section 22 admits the supervision picker may stay empty. Say: 'V1 applies only to runners_for output; the supervision picker filtered by SUPPORTED_RUNNERS may be empty.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Plan never says what happens when a runner is configured (e.g.

- Severity: HIGH
- References: CHANGE_SPEC C4 vs C1/V1; CHANGE_PLAN s5 leaves stage_runner untouched. Say: 'A configured runner absent from runners_for output is still returned by stage_runner; only an unset value falls back to self-hosted.'
- Failure: Plan never says what happens when a runner is configured (e.g. claude) but none is installed. C4 keeps the configured value, but V1 and the picker would show only Self hosted, so the default and the picker disagree.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan does not state the result when only opencode is installed, or whether the fallback could duplicate self-hosted.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3; CHANGE_PLAN s16. Say: 'With only opencode installed runners_for returns exactly ["self-hosted"], and the fallback never appends to a non-empty list.'
- Failure: Plan does not state the result when only opencode is installed, or whether the fallback could duplicate self-hosted. AC-3 only tests claude+opencode.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Plan declares the 'No agents installed' label unreachable but does not check for other guards keyed on an empty runner l

- Severity: MEDIUM
- References: CHANGE_PLAN s6 and s22; only uncle_tui.py:690-709 was inspected. Say: 'Defaulting to self-hosted does not bypass the existing self-hosted configuration requirement; this is tested.'
- Failure: Plan declares the 'No agents installed' label unreachable but does not check for other guards keyed on an empty runner list or runner=="". It also does not say whether defaulting to unconfigured self-hosted can start a run.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Plan does not say whether runners_for reads PATH on each call or caches it.

- Severity: LOW
- References: CHANGE_PLAN s16. Say: 'runners_for reads PATH on every call, and the test creates fake binaries portably or skips on Windows with a stated reason.'
- Failure: Plan does not say whether runners_for reads PATH on each call or caches it. It also does not say how fake binaries work on Windows, which the repo supports.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The plan never says what happens when the fallback self-hosted runner is selected while unconfigured: launch with empty

- Severity: MEDIUM
- References: CHANGE_PLAN §1 and §5 leave the self-hosted config flow unmodified; CHANGE_SPEC non-goals exclude it. Nothing covers stage_runner (AC-2) returning an unconfigured self-hosted default.
- Failure: The plan never says what happens when the fallback self-hosted runner is selected while unconfigured: launch with empty credentials/endpoints, or block. Add: 'Selecting unconfigured self-hosted must not start a stage and must show a configuration-required error.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The plan says unreadable PATH entries count as not found, but does not say that PATH contents (empty, unset, or attacker

- Severity: LOW
- References: CHANGE_SPEC §8 treats unreadable PATH entries as not found. CHANGE_PLAN §16 tests only an empty PATH directory and a temp directory with fake binaries.
- Failure: The plan says unreadable PATH entries count as not found, but does not say that PATH contents (empty, unset, or attacker-controlled directories) never select or auto-launch a runner beyond the existing scan. State that the fallback is the only behavior change.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan never says how the test isolates the runner scan and stage_runner inputs from the host.

- Severity: HIGH
- References: CHANGE_PLAN s16 and CHANGE_SPEC AC-2 mention an empty PATH dir and no configured runner, but give no isolation mechanism.
- Failure: Plan never says how the test isolates the runner scan and stage_runner inputs from the host. Settle with: 'The test sets PATH to a temp dir only, patches DEFAULT_RUNNER to "", and uses an empty config.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: AC-3 expected shape is ambiguous: ["claude","self-hosted"] vs 'no extra entries' with opencode mapped to self-hosted.

- Severity: MEDIUM
- References: CHANGE_PLAN s16 AC-3 case against CHANGE_SPEC AC-3.
- Failure: AC-3 expected shape is ambiguous: ["claude","self-hosted"] vs 'no extra entries' with opencode mapped to self-hosted. Settle with: 'With fake claude and opencode on PATH, runners_for returns exactly ["claude","self-hosted"] with self-hosted once.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The 'both sides' argument values for runners_for are never named.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 and CHANGE_PLAN s16 say 'both sides' without the signature or values.
- Failure: The 'both sides' argument values for runners_for are never named. Settle with: 'The test calls runners_for with each valid side value (name them) and asserts ["self-hosted"] for each.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The manual picker check does not say whether the supervision picker is in scope, though the plan admits it may stay empt

- Severity: LOW
- References: CHANGE_PLAN s13 against s19.
- Failure: The manual picker check does not say whether the supervision picker is in scope, though the plan admits it may stay empty. Settle with: 'Manual check covers stage runner pickers only; the supervision picker is excluded from pass/fail.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
