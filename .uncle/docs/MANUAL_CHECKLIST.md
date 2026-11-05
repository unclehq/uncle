# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --housekeeping` and `uncle --housekeeping=x` from a scratch directory, then run `uncle --help`, and note exit codes and output.
- Expected result: Both flag invocations exit non-zero as unknown options, start nothing, and neither the usage nor did-you-mean text mentions housekeeping.
- Evidence to capture: Terminal transcript with exit codes and the printed usage text.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch the TUI, type `/housekeeping`, `/mode` and `/mode supervisor` in the home chat, and open the Configure menus (launcher Configure menu and the TUI config screen, Miscellaneous section).
- Expected result: The slash commands are treated as unknown commands, and no housekeeping entry or disallow-list editor exists in either Configure menu.
- Evidence to capture: Screenshots or transcript of each command response and each menu listing.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: dir:manual-home-agent-scratch
- Depends on: MC-103
- Exact action: In the same session, ask the agent to clone a repo and then say 'build issue 34'. Separately, ask it to move into a nonexistent path and into `/`.
- Expected result: The build action is shown for user confirmation and starts only after confirming, and it targets the clone. Invalid or rejected paths leave the project root unchanged with a note.
- Evidence to capture: Screenshots of the confirmation prompt, the status bar root, and the rejection notes.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: dir:manual-home-agent-scratch
- Depends on: none
- Exact action: Decline a tool approval prompt in the home chat, then trigger another prompt and type an unrelated message while it is pending.
- Expected result: Decline posts a note, grants nothing and re-sends nothing. An unrelated message clears the prompt as a decline and is then handled normally.
- Evidence to capture: Screenshots of the chat log showing the notes and the follow-up reply.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui` and `uncle --unattended` on a trivial request, and also run the TUI with a `.uncle/config` containing legacy `housekeeping.*` keys and `UNCLE_HOUSEKEEPING_UNATTENDED=1` set.
- Expected result: No home chat agent exists in noui or unattended runs. Legacy config keys and env vars are ignored without error or warning, and the TUI starts normally.
- Evidence to capture: Terminal transcript showing startup output and exit status.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch directory, run `uncle --housekeeping` and `uncle --housekeeping=x`, and also `uncle --bogus-flag`; capture exit codes and full stdout/stderr.
- Expected result: Each exits non-zero as an unknown option, starts no workflow, and usage/did-you-mean text never mentions housekeeping.
- Evidence to capture: Terminal transcript with exit codes and output.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: tui:home-chat
- Depends on: none
- Exact action: Launch the interactive app (uncle) in an empty directory with a logged-in claude runner and open Configure menus in the launcher and TUI; type `/housekeeping` and `/mode` in home chat.
- Expected result: No housekeeping entry exists in either Configure menu; both slash commands are treated as unknown commands like any other.
- Evidence to capture: Screenshots or terminal capture of the menus and the slash-command responses.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: tui:home-chat
- Depends on: none
- Exact action: In idle home chat ask the agent to run a command that default permission mode denies (e.g. create a directory and a file outside the project), observe the approval prompt, decline once, then repeat the request and approve.
- Expected result: A pending approval shows the full verbatim command; decline produces a note with no re-send and no grant; approval runs only that exact command once, and no bypass of permissions occurs silently.
- Evidence to capture: Transcript of prompts, notes and resulting filesystem state.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start uncle with `--noui` and with `--unattended` on a trivial request, and attempt to find a home chat agent.
- Expected result: No home chat agent exists in those modes and the runs behave as before.
- Evidence to capture: Terminal transcripts of both runs.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: file:tui-demo-dir
- Depends on: none
- Exact action: In a fresh empty directory with a logged-in claude runner and no build running, launch uncle and send a home-chat message asking to create a directory 'demo' and move into it; observe the status bar and window title.
- Expected result: A tool-enabled agent creates the directory, the app validates the path, and the status bar and title show the new project root; the completion message reflects the real command result.
- Evidence to capture: Screenshot or terminal capture of the chat transcript, status bar and title before and after.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: file:tui-demo-dir
- Depends on: MC-301
- Exact action: In the same home chat, ask the agent to run a command that Claude's default permission mode denies (for example a git clone or a write outside the project); observe the prompt, then approve it once; repeat with another command and decline.
- Expected result: A pending-approval prompt shows the full verbatim command; approval runs only that exact command and the turn is re-sent once; decline posts a note with no re-send and no grant.
- Evidence to capture: Capture of both prompts, the approve and decline outcomes, and the resulting transcript notes.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: file:tui-demo-dir
- Depends on: MC-301
- Exact action: From the home chat, ask 'build issue 34' and then a hello-world C program request; observe the confirmation step for each agent-emitted action, and confirm each.
- Expected result: Each request shows the action to the user for explicit confirmation and starts the build only after confirmation, targeting the current project root; declining discards the action.
- Evidence to capture: Capture of the confirmation prompts and the launched build's start message with its working directory.
- Actual result: 
- Status: NOT RUN

### MC-305
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --housekeeping`, then open the TUI and type `/housekeeping` and `/mode`, then open the Configure menu in both the launcher and the TUI.
- Expected result: The flag exits non-zero as an unknown option with usage text not mentioning housekeeping; the slash commands are treated as unknown; no housekeeping entry appears in either Configure menu.
- Evidence to capture: Terminal output with exit status and screenshots of the TUI responses and menus.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `./uncle --housekeeping` and `./uncle --housekeeping=x` from the project root, then `./uncle --help` and a misspelled flag such as `./uncle --aplication`, noting each exit status.
- Expected result: The housekeeping flags exit non-zero as unknown options and start nothing. Usage and did-you-mean text never mention housekeeping. The misspelled flag still gives usage plus a suggestion and a non-zero exit.
- Evidence to capture: Terminal output and exit codes of each invocation.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Launch the TUI interactively. Type `/housekeeping`, `/mode` and `/mode supervisor`, then open the Configure screen and the Miscellaneous section. Also open the launcher Configure menu.
- Expected result: The slash commands are treated as unknown commands like any other. No housekeeping entry or disallow-list editor appears in either Configure UI. The remaining menu items still work.
- Evidence to capture: Screen captures or transcript of each command response and both menus.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `./uncle --noui` and an `--unattended` run on a small task, and also `./uncle --application` with text piped on stdin.
- Expected result: The noui and unattended runs proceed without any home chat agent. The piped `--application` stdin path behaves as it did before, with mutual-exclusion rules intact.
- Evidence to capture: Terminal output and exit codes of the three runs.
- Actual result: 
- Status: NOT RUN

### MC-407
- Required for acceptance: NO
- Exclusive resources: none
- Depends on: none
- Exact action: Create a `.uncle/config` containing legacy `housekeeping.disallow` keys and set `UNCLE_HOUSEKEEPING_SESSION` in the environment, then launch the TUI and send a chat message.
- Expected result: The legacy key and variable are ignored with no error or warning, and nothing housekeeping-related is enabled.
- Evidence to capture: Launch output and chat transcript.
- Actual result: 
- Status: NOT RUN
