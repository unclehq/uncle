# Manual checklist

## Coverage: spending stop

### MC-105
- Required for acceptance: YES
- Exclusive resources: dir:headless-run-231
- Depends on: none
- Exact action: Trigger a host spending stop (HTTP 402) during the repair turn of a headless run with an invalid plan, then raise the budget and resume.
- Expected result: The stage stops with a spending_limit stop-reason and no re-check. The resume runs a fresh repair turn.
- Evidence to capture: Stop-reason file content, run output, and the agent calls on resume.
- Actual result: 
- Status: NOT RUN

## Coverage: UPDATED_PLAN repair

### MC-106
- Required for acceptance: YES
- Exclusive resources: dir:headless-run-231
- Depends on: none
- Exact action: Run the updated-plan stage with an invalid saved UPDATED_PLAN, with a real model agent.
- Expected result: One repair turn runs and the stage continues if the re-check passes. Otherwise it exits 1 with the file, step and resume command named.
- Evidence to capture: Run log and stderr showing the repair turn and outcome.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Create a scratch project whose saved PROJECT_PLAN has a valid Owns line plus a step whose Owns is a backticked span `foo bar`, run the stage headlessly with a stub agent that rewrites the span to a real path, and count agent calls.
- Expected result: Exactly one repair agent call occurs, the warning line 'warning: step <label> owns: dropped foo bar' appears on stderr, the re-check passes and the run continues; a rerun with a valid plan makes zero repair calls.
- Evidence to capture: Stderr transcript, agent-call count, and presence/absence of the plan-check-repair-project-plan marker file after the run.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-202
- Exact action: After a failed repair, hand-edit the plan to still be invalid but different, then resume; separately, run the same scenario for the UPDATED_PLAN check.
- Expected result: The changed plan hash gets exactly one fresh repair call; the UPDATED_PLAN check behaves identically (one repair, then final failure naming UPDATED_PLAN with no second repair).
- Evidence to capture: Agent-call counts per run and stderr showing the plan file name.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the repair with stub agents that respectively exit non-zero, edit nothing, truncate the plan file, delete it, and edit an unrelated file in the working tree.
- Expected result: In every case there is exactly one agent call, no re-check, exit 1, the marker is retained, and the message names the file and resume command (the stray-file case reports the stray change on stderr).
- Evidence to capture: Per-case exit code, stderr, agent-call count and marker state.
- Actual result: 
- Status: NOT RUN

### MC-207
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the plan parser against Owns lines containing `../x`, `a/../../b`, `/abs`, `a..b.py`, `src/{a,b}.py`, `~`, and `src/`, on both the Markdown and JSON routes.
- Expected result: `../x`, `a/../../b` and `/abs` are dropped with warnings; `a..b.py`, `src/{a,b}.py` and `~` are kept; `src/` is kept by the filter but the validator still rejects it as a directory; an all-dropped step yields empty owns with warnings first and then the missing-owns error.
- Evidence to capture: Printed owns lists, stderr warnings, and validator output per route.
- Actual result: 
- Status: NOT RUN

## Dropped-token warning display

### MC-303
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the plan check on a plan whose Owns line contains a backticked span with spaces and one whose token includes an ANSI escape sequence and a 200-character run, viewing stderr in a real terminal.
- Expected result: Each dropped token prints as one `warning: step <label> owns: dropped <token>` line; the terminal shows no escape-driven colour or cursor effects and long tokens end in `...` at 80 characters.
- Evidence to capture: Screenshot or copied terminal output of the warning lines.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Feed the parser previously valid tokens (`src/{a,b}.py`, `~`, `+`, `=`, `a..b.py`, `src/`) on a ticked Owns line and on JSON owns arrays, then run validation on each.
- Expected result: All tokens are kept unchanged with no warning on stderr, `src/` is still rejected by the validator's directory rule, and tokens with a `..` segment or whitespace are dropped with a warning `warning: step <label> owns: dropped <token>`.
- Evidence to capture: Owns lists, stderr text, and validator output per input.
- Actual result: 
- Status: NOT RUN
