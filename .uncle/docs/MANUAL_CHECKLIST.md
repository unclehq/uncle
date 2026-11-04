# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch project with a TTY, run `uncle --application "demo app"` with no mode flag or env set, and watch the start of the run.
- Expected result: stderr shows `Mode: unattended (default). Approval gates are delegated to the agent; use --attended to approve each gate yourself.` and the run proceeds through gates without waiting for a person.
- Evidence to capture: Terminal transcript of the banner and the first gates passing unprompted.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch project with a TTY, run `uncle --application "demo app" --attended` and observe the first approval gate.
- Expected result: Banner `Mode: attended. Each approval gate waits for your decision.` appears and the run stops at the first gate waiting for a typed decision.
- Evidence to capture: Terminal transcript showing the banner and the pending gate prompt.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --application "demo" --attended </dev/null`, then repeat with `UNCLE_ATTENDED=1 uncle --application "demo" </dev/null`, and check for created state afterward.
- Expected result: Both exit nonzero with stderr `uncle: attended mode needs an interactive terminal on stdin; set UNCLE_ATTENDED_STDIN=1 to answer gates from stdin.`, start nothing, and never run unattended.
- Evidence to capture: Exit codes, stderr text, and a listing showing no .uncle/workflow state or mode file was created.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --application "demo" --attended --unattended`, then `uncle --application "demo" --unattended`, each in a scratch project with a TTY.
- Expected result: The first refuses with exit 1 and `uncle: --attended and --unattended contradict each other; choose one.`, starting nothing. The second runs unattended and prints `uncle: --unattended is deprecated; unattended is now the default. Use --attended to approve gates yourself.` on stderr only.
- Evidence to capture: Exit codes, stderr and stdout captured separately.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start an attended run in a scratch project and stop it at the first gate. Resume with no flag in a TTY, then resume with `</dev/null`, then resume with `--unattended`.
- Expected result: TTY resume prints `Mode: attended (resumed from .uncle/workflow/mode).` and waits. The no-TTY resume refuses with exit 1 and never runs unattended. `--unattended` overrides the recorded mode and runs unattended with the deprecation notice. The refused resume leaves the mode file unchanged.
- Evidence to capture: Transcripts, exit codes, and a before/after hash of .uncle/workflow/mode.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the interactive TUI with `uncle` (default), check the header, press Shift-Tab, then start another session with `uncle --attended`.
- Expected result: The header reads `Mode: unattended` by default, Shift-Tab switches the session to attended, and `--attended` starts the TUI as `Mode: attended`. The auto-mode help text states that issue runs publish a PR and other runs do not commit or push.
- Evidence to capture: Screenshots or a terminal capture of the TUI header in each state and the help text.
- Actual result: 
- Status: NOT RUN

### MC-108
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run housekeeping with a disallowed command in default mode, then with an allowed command in default mode, then with an allowed command under `--attended` in a TTY.
- Expected result: The disallowed command is refused by the policy gate identically in both modes. The allowed command runs with no `Run these commands? [y/N]` prompt by default, and the prompt appears under `--attended`.
- Evidence to capture: Terminal transcripts of the three runs.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch directory, run `uncle --attended --application 'demo' </dev/null` with UNCLE_ATTENDED_STDIN unset, then run `UNCLE_ATTENDED=1 uncle --change-request demo </dev/null`.
- Expected result: Both refuse with exit 1 and stderr `uncle: attended mode needs an interactive terminal on stdin; set UNCLE_ATTENDED_STDIN=1 to answer gates from stdin.`; nothing starts, no .uncle/workflow state is created, and the run never proceeds unattended.
- Evidence to capture: Exit codes, stderr text, and a directory listing showing no workflow state.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --attended --unattended --application 'demo'` in a scratch directory, then repeat it with the direct drivers stagegate.sh and change-workflow.sh.
- Expected result: Each entry point exits 1 with stderr `uncle: --attended and --unattended contradict each other; choose one.` and starts nothing.
- Evidence to capture: Exit code and stderr for each entry point.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --application 'demo'` with no mode flag or env in a real terminal and observe startup. Then run it again with `--unattended`.
- Expected result: The first run prints the banner `Mode: unattended (default). Approval gates are delegated to the agent; use --attended to approve each gate yourself.` on stderr and delegates gates without prompting. The second run behaves the same and also prints the `--unattended is deprecated` notice once.
- Evidence to capture: Terminal transcript showing banner, deprecation notice, and no gate prompts.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a real terminal, run `uncle --attended --application 'demo'` and observe the first approval gate. At the gate, close stdin with Ctrl-D, or enter garbage text.
- Expected result: The banner `Mode: attended. Each approval gate waits for your decision.` prints. The run waits at the first gate. EOF or an invalid answer counts as a decline and stops the run, and the gate is never delegated or auto-approved.
- Evidence to capture: Transcript showing the attended banner, the gate prompt, and the stop. The unattended-gates ledger has no entry for that gate.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: file:.uncle/workflow/mode
- Depends on: none
- Exact action: Start an attended run in a real terminal and stop it at the first gate. Record the hash of .uncle/workflow/mode. Resume with `</dev/null` and no flag, then with `UNCLE_ATTENDED_STDIN=1`, then with `--unattended`, then in a terminal with no flag.
- Expected result: With no TTY and no escape the resume refuses with exit 1, the mode file hash is unchanged, and it never runs unattended. With the escape it resumes attended. With `--unattended` it overrides and runs unattended. In a terminal it resumes attended and prints `Mode: attended (resumed from .uncle/workflow/mode).`
- Evidence to capture: Exit codes, stderr and banners for each resume, and the mode file hash before and after the refusal.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `UNCLE_UNATTENDED=0 uncle --application demo`, `UNCLE_ATTENDED=0 uncle --application demo`, `UNCLE_ATTENDED=1 uncle --unattended --application demo`, and `UNCLE_UNATTENDED=1 uncle --application demo`, in a terminal.
- Expected result: The first two ignore the env value silently and run unattended with no notice. The third resolves attended and prints the `--unattended is deprecated` notice. The fourth runs unattended and prints the `UNCLE_UNATTENDED=1 is deprecated` notice.
- Evidence to capture: Banner and notice lines for each run.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: dir:scratch-mode-run
- Depends on: none
- Exact action: In a scratch directory with no prior run state, run `uncle --application "hello"` with no mode flag or env, then run `uncle --application "hello" --attended </dev/null`; capture stderr and exit codes of each.
- Expected result: First run prints `Mode: unattended (default). Approval gates are delegated to the agent; use --attended to approve each gate yourself.` on stderr and proceeds without pausing at gates. Second run prints `uncle: attended mode needs an interactive terminal on stdin; set UNCLE_ATTENDED_STDIN=1 to answer gates from stdin.`, exits 1, and starts nothing.
- Evidence to capture: Terminal transcript with stderr banner/refusal text, exit codes, and a listing showing no run state or mode file created by the refused run.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: dir:scratch-mode-attended
- Depends on: none
- Exact action: In an interactive terminal in a fresh scratch directory, run `uncle --application "hello" --attended` and observe the first approval gate; then answer it by hand. Then run `uncle --application "hello" --attended --unattended`.
- Expected result: Attended banner `Mode: attended. Each approval gate waits for your decision.` appears and the run waits for a person at the first gate. The contradictory invocation prints `uncle: --attended and --unattended contradict each other; choose one.`, exits 1, and starts nothing.
- Evidence to capture: Terminal transcript or screen capture showing the banner, the waiting gate prompt, the refusal text and exit code.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: dir:scratch-mode-attended
- Depends on: MC-302
- Exact action: Run `uncle --application "hello" --unattended` in a fresh scratch directory and capture stderr; then in an attended run directory (started via MC-302 and stopped at a gate) resume with `uncle --application "hello" </dev/null` and no flag.
- Expected result: The `--unattended` run works as the default and prints `uncle: --unattended is deprecated; unattended is now the default. Use --attended to approve gates yourself.` once on stderr. The resume without TTY prints `Mode: attended (resumed from .uncle/workflow/mode).` or refuses with the no-TTY message, exits 1, and never proceeds unattended.
- Evidence to capture: Stderr transcripts for both commands, exit codes, and the mode file content before and after the refused resume (unchanged).
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: In a git-less scratch directory run the TUI with `uncle` (no flags) and observe the header, then press Shift-Tab; quit and rerun with `uncle --attended` and observe the header.
- Expected result: Default TUI header shows `Mode: unattended` and Shift-Tab toggles it to attended for the session; with `--attended` the TUI starts showing `Mode: attended`. Auto-mode help text accurately states that issue runs publish a PR and other runs do not commit or push.
- Evidence to capture: Screen captures of the TUI header in each state and the auto-mode help text.
- Actual result: 
- Status: NOT RUN

### MC-305
- Required for acceptance: YES
- Exclusive resources: dir:scratch-housekeeping
- Depends on: none
- Exact action: Run `uncle --housekeeping "<an allowed command request>"` unflagged, then with `--attended` in an interactive terminal, then with a request for a disallowed command in both modes.
- Expected result: Unflagged run skips the `Run these commands? [y/N]` prompt only after the policy gate passes; attended run shows the prompt; the disallowed command is refused identically in both modes before any approval or prompt.
- Evidence to capture: Terminal transcripts of all four runs showing prompt presence/absence and refusal text.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch project, run `uncle --application "tiny demo"` with a real terminal and no mode flag or env, and let it run. Then run `uncle --application "tiny demo" --attended` in a terminal.
- Expected result: The unflagged run prints the unattended banner on stderr and finishes without waiting at a gate. The attended run prints the attended banner and pauses at the first approval gate until you answer.
- Evidence to capture: Terminal transcripts of both runs showing the banner lines and the first gate pause.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --attended --application "x" </dev/null`. Then run `uncle --attended --unattended --application "x"`. Check the scratch project's .uncle/workflow directory afterward.
- Expected result: Both runs exit nonzero and start nothing. The first prints the no-TTY refusal and the second prints the contradictory-flags refusal, each on stderr. No .uncle/workflow/mode file is created.
- Evidence to capture: Exit codes, stderr text, and a directory listing of .uncle/workflow.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --unattended --application "x"` and capture stdout and stderr separately.
- Expected result: The run behaves as the default unattended run. Stderr carries one deprecation notice for --unattended and nothing is added to stdout.
- Evidence to capture: Separately captured stdout and stderr showing the single deprecation line.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: file:scratch-project-run-dir
- Depends on: none
- Exact action: Start a run with `--attended` in a terminal and stop it at the first gate. Resume it in a terminal with no flag. Then resume it with `</dev/null`. Finally resume it with `--unattended`.
- Expected result: The terminal resume prints the resumed banner with the attended mode and waits at the gate. The `</dev/null` resume refuses with exit 1 and never runs unattended. The `--unattended` resume overrides the recorded mode.
- Evidence to capture: Banner lines, the refusal message, exit codes, and the content of .uncle/workflow/mode after each step.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run an unattended issue or change run to completion in a scratch project. Open the resulting PR body or final report, the attestation, and the unattended-gates ledger.
- Expected result: Gates are recorded as delegated and the PR body or final report states no human reviewed. The attestation fields and the human-check waiver wording are unchanged from before the change. A failing test still stops the run.
- Evidence to capture: The PR body or final report text, .uncle/attestation.json, and the ledger contents.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --housekeeping "<an allowed command request>"` with no flag and then with `--attended`. Then run it with a request for a disallowed command in both modes.
- Expected result: The default run skips the `Run these commands? [y/N]` prompt. The attended run shows the prompt. The disallowed request is refused by the policy gate in both modes, before any prompt.
- Evidence to capture: Terminal transcripts of all four runs.
- Actual result: 
- Status: NOT RUN

### MC-407
- Required for acceptance: YES
- Exclusive resources: browser:system
- Depends on: none
- Exact action: Run `uncle --help`, then launch the interactive TUI with no flags and read its header and auto-mode help. Press Shift-Tab, then start a second TUI with `--attended`.
- Expected result: The help names `--attended`, the new default, and the deprecation. The TUI starts unattended with the Mode header shown, and Shift-Tab switches it to attended. The `--attended` TUI starts attended. The auto-mode help describes actual PR behavior.
- Evidence to capture: The help text and screenshots or transcripts of the TUI header in each state.
- Actual result: 
- Status: NOT RUN

### MC-408
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With a newer version available, run an unflagged `uncle` command in a terminal, then run it with `--attended` in a terminal.
- Expected result: The unflagged run prints a single line naming the newer version and the upgrade command, and does not prompt. The attended run prompts for the upgrade.
- Evidence to capture: Terminal transcripts of both runs.
- Actual result: 
- Status: NOT RUN
