# Manual checklist

## Coverage

### MC-105
- Required for acceptance: YES
- Exclusive resources: tui:session, file:.uncle/workflow/housekeeping.lock
- Depends on: none
- Exact action: Start housekeeping from a second terminal with `scripts/housekeeping-workflow.sh --unattended 'long chore'` so it holds the lock, then in the TUI type `/housekeeping other chore`.
- Expected result: The TUI launch exits with the lock refusal and posts 'Housekeeping already running' (not a FAILED notice), and the first terminal run continues unaffected.
- Evidence to capture: The TUI notice and the second terminal's output showing it is still running.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-202
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/housekeeping.lock
- Depends on: none
- Exact action: Start a housekeeping run in one terminal with `scripts/housekeeping-workflow.sh --unattended 'chore'`. While it runs, launch a second `scripts/housekeeping-workflow.sh --unattended 'chore2'` from another terminal.
- Expected result: The second invocation exits 1 with a lock-held message. The first run continues and completes normally.
- Evidence to capture: Exit code and output of the second run, and the first run's final state.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/housekeeping.lock
- Depends on: none
- Exact action: Run housekeeping in a TUI session while another terminal holds housekeeping.lock, using `/housekeeping x` (hk_proc is None).
- Expected result: The script exits 1 and the TUI posts 'Housekeeping already running'. It does not post a FAILED notice.
- Evidence to capture: Chat notice text and the contents of .uncle/workflow/housekeeping/tui.out.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start a background housekeeping run and, after it ends, check the chat for notices. Repeat with a housekeeping run that fails (for example a stub or killed process). Then start a long run and quit the TUI.
- Expected result: A successful run posts exactly one DONE notice with code 0. A failed or killed run posts exactly one FAILED notice with its exit code or signal. Quitting the TUI terminates the live run and posts no completion notice.
- Evidence to capture: Chat notices for each case and a process listing after quit showing no leftover housekeeping process.
- Actual result: 
- Status: NOT RUN

## Resources

### MC-303
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/housekeeping.lock
- Depends on: none
- Exact action: While one background housekeeping run is still alive, issue `/housekeeping` a second time in the TUI; then, from a second terminal, run housekeeping-workflow.sh while the first run holds housekeeping.lock.
- Expected result: The TUI shows 'Housekeeping already running' and starts no second process; the second-terminal script exits 1 with a lock message, and the first run continues unaffected.
- Evidence to capture: TUI chat text, the script's exit code and message, and proof that the first run is still alive.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/housekeeping
- Depends on: none
- Exact action: In the TUI with no workflow running, enter `/housekeeping list merged branches` (attended preference) and observe the flow.
- Expected result: The foreground path runs as before, including the attended confirmation prompt, and finishes with its normal result; no background-start notice appears.
- Evidence to capture: Terminal capture showing the confirmation prompt and the foreground completion.
- Actual result: 
- Status: NOT RUN
