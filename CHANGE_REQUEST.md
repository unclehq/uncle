# Change Request

## Change Type

Feature

## Summary

When preflight reports a blocker, the gate should offer the operator three
explicit choices — review the blockers, skip them, or decline the run —
instead of funneling them into supplying the input or signing a waiver.

## Motivation

The preflight gate exists to make blockers cheap, but the moment one fires,
the operator's only real moves are to hand over the missing prerequisite on
the spot or to sign a waiver for it. Neither fits every case: sometimes the
right response is to read the evidence first, sometimes the blocker genuinely
does not matter for this run, and sometimes the right answer is to stop and
amend the plan. Today those last two are only reachable through a per-id
waiver justification ritual or an implicit failure exit, so operators sign
waivers they do not mean just to get past the gate — which teaches the
workflow that "waived" means "rubber-stamped".

## Observed Current Behavior

In `scripts/stagegate.sh`, the `PREFLIGHT` state (lines ~1520-1615) reads
`acceptance_result PREFLIGHT_REPORT.md` and, for attended runs:

- `BLOCKED-SETUP`: the driver lists the blocked ids, then
  `collect_human_inputs` asks the operator to provide each prerequisite
  interactively. Anything still outstanding goes to `record_waiver`, which
  requires a recorded justification per id (the waiver popup,
  `scripts/lib/waiver-popup.py`). Declining that stops the run with
  "Not provided and not waived; stopping before implementation." (exit 1).
  If the same ids block the next attempt, `human_input_repeating` exits with
  advice. There is no option to inspect the report from the pause, no way to
  continue without either providing or signing, and no first-class "stop"
  choice — stopping is the failure case, not an offered outcome.
- `BLOCKED-IMPOSSIBLE` / `FAIL` / `UNKNOWN`: prints "Resolve and rerun." and
  exits 1. The operator is not asked anything.
- `BLOCKED-HUMAN` and `PASS`: continue (correct as-is).
- Unattended mode auto-waives `BLOCKED-SETUP` and continues (correct as-is).

The report's blocker rows print as bare ids (`acceptance_blocked_ids |
sed 's/^/  /'`); the evidence column explaining each one is in
PREFLIGHT_REPORT.md, which the gate tells the operator to open themselves.

## Desired Behavior

When preflight ends with any required row not PASS, the attended gate
presents three explicit choices before anything is signed:

1. **Review** — show the blocker rows with their Status and Evidence (and the
   resolution action for BLOCKED-SETUP) in place, then return to the choice.
   No opening files by hand, no re-running the stage.
2. **Skip** — record one explicit operator decision covering the outstanding
   blockers and continue to implementation. The skip is written down with the
   same auditability a waiver has (which ids, when, by whom it was chosen),
   but it is one decision, not a per-id justification popup, and it is
   labeled as what it is: the operator proceeded with known-missing
   prerequisites. Implementation and the checklist must still see the rows as
   blocked-in-report; a skip is not a PASS and must not become one
   downstream.
3. **Decline** — stop the run cleanly as a deliberate outcome: state
   preserved, blocker summary printed, and the next step named (amend the
   plan / resolve the named action and rerun). Declining is a recorded
   operator decision, not an error exit.

Providing the prerequisite interactively stays available — it becomes one
option inside review/skip/decline, not the only door. The current per-id
waiver path may remain as the mechanism a skip records through, but the
operator must be able to choose it once for all outstanding ids.

BLOCKED-IMPOSSIBLE gets the same three choices rather than a bare "Resolve
and rerun" — declining is the natural answer there, and skipping an
impossible prerequisite must still be possible since the checklist is
required to not depend on it.

Unattended behavior is unchanged (auto-waive and continue, already recorded
as such).

## Reproduction

Not applicable (feature). To see the current shape: run a workflow whose
PREFLIGHT_REPORT.md has a BLOCKED-SETUP row; the gate immediately asks for
the input or a signed waiver, with no review or decline option.

## Constraints

- Auditability is not weakened: every skip and decline is recorded with the
  ids it covered and is visible to the audit stage and in the workflow
  records, at least at the level the current waiver records provide.
- A skip must not flip any report row to PASS and must not satisfy
  `preflight_settled` as if the prerequisite existed; downstream gates
  (checklist, verification) keep seeing the blocker.
- `human_input_repeating`'s protection stays: re-asking the same unresolved
  ids verbatim must not loop.
- No interactive prompt in unattended mode; the TUI and plain-terminal paths
  both get the three choices (the TUI may render them as its own picker; the
  shell gate as a prompt).
- The y/n gate idiom from the earlier change applies to the choice prompt.

## Known Relevant Files

- `scripts/stagegate.sh` — `PREFLIGHT` state (~1500-1615),
  `acceptance_setup_pause` (~433), `acceptance_human_continue` (~446),
  `acceptance_after_waiver` (~461), `acceptance_transition` (~474),
  `preflight_settled` (~349), waiver functions (`record_waiver`,
  `write_waivers`, `waive_file`, `waived_ids`)
- `scripts/lib/acceptance.sh` — `acceptance_result`,
  `acceptance_blocked_ids`, `acceptance_problem`
- `scripts/lib/waiver-popup.py` — the justification popup a skip should not
  require per-id
- `scripts/lib/human-input.sh` — `collect_human_inputs`,
  `human_input_repeating`, `apply_human_inputs`
- `uncle_tui.py` — if the TUI renders the gate
- Tests: `scripts/tests/blocked-classes-test.sh`,
  `scripts/tests/human-input-test.sh`, `scripts/tests/waiver-popup-test.sh`,
  `scripts/tests/unattended-test.sh`

## Out of Scope

- What the preflight agent reports or how blockers are classified
  (prompts/preflight.md is unchanged).
- Unattended-mode behavior.
- The BLOCKED-HUMAN continue path.
- Any change to implementation or later gates beyond what keeps a skipped
  blocker visible as blocked.

## Success Criteria

- With a BLOCKED-SETUP row present, the gate offers review / skip / decline
  (plus provide-input) and each choice does what this request says:
  review shows evidence and returns to the menu; skip records one decision
  covering the outstanding ids and the run reaches IMPLEMENT with the rows
  still blocked in the report; decline exits with the blocker summary and
  the rerun/amend instruction, state preserved at PREFLIGHT.
- The same three choices appear for BLOCKED-IMPOSSIBLE.
- A skipped run's records show the skip (ids, timestamp) in the same places a
  waiver appears today, and the audit/final-audit stages can see it.
- Re-running after a skip does not re-ask the same ids (the recorded decision
  settles them for this run) and does not mark them provided.
- Unattended runs behave exactly as before.
- Updated `blocked-classes-test.sh` and `human-input-test.sh` cover the new
  transitions; existing suites pass.
