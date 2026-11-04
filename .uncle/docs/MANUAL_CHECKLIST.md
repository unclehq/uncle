# Manual checklist

### MC-101
- Exclusive resources: file:sandbox-project-state
- Depends on: none
- Exact action: In recovery with each non-`tool bug` classification (code defect, requirement gap, owner decision) and with no classification, check the banner and type `/report`.
- Expected result: No /report hint in the banner; /report prints the fixed refusal line, arms no confirmation, creates no bug-report draft, and no gh call occurs.
- Actual result: 
- Status: NOT RUN

### MC-104
- Exclusive resources: file:sandbox-project-state
- Depends on: none
- Exact action: Run /report with a fake `gh` on PATH, then answer `no` (also try empty input and another slash command at the confirmation prompt); check the fake gh log and that the input did not reach triage chat.
- Expected result: Report cancelled with a one-line message; no `gh issue create` invoked; draft retained; the input was not forwarded to the triage chat; existing triage-issue-N.md files are unchanged.
- Actual result: 
- Status: NOT RUN

### MC-105
- Exclusive resources: file:sandbox-project-state
- Depends on: none
- Exact action: Run /report with an authenticated fake gh that prints extra output then a URL last, and answer ` YES ` at confirmation.
- Expected result: Exactly one `gh issue create --repo unclehq/uncle --title ... --body-file ...` call is made and the issue URL is displayed; the draft remains.
- Actual result: 
- Status: NOT RUN

### MC-106
- Exclusive resources: file:sandbox-project-state
- Depends on: none
- Exact action: Run /report and answer `yes` with (a) gh absent from PATH, (b) gh failing `auth status`, (c) gh create exiting 0 with no URL or timing out.
- Expected result: Each case keeps the draft and shows an actionable message with a copyable shell-quoted `gh issue create --repo unclehq/uncle ...` command; in (c) the message says the issue may already exist and there is no retry; no crash.
- Actual result: 
- Status: NOT RUN

### MC-201
- Exclusive resources: file:.uncle/workflow/bug-report-drafts
- Depends on: none
- Exact action: In a recovery session, run `/report` with classifications code defect, requirement gap, needs owner decision, none, and outside recovery. Check each for the refusal line and for new draft files.
- Expected result: Each attempt prints the fixed refusal line, arms no confirmation, creates no bug-report draft, and calls no gh. The banner offers /report only for `tool bug`.
- Actual result: 
- Status: NOT RUN

### MC-204
- Exclusive resources: file:.uncle/workflow/bug-report-drafts
- Depends on: none
- Exact action: With gh absent from PATH, run `/report` and answer `yes`. Repeat with a gh whose `auth status` fails. Record the message each time and snapshot existing triage-issue-*.md files before and after.
- Expected result: No issue is created in either case. The sanitized draft is saved, with an actionable message and a copyable `gh issue create --repo unclehq/uncle --title ... --body-file ...` command. Existing triage-issue-*.md files are byte-identical.
- Actual result: 
- Status: NOT RUN

### MC-205
- Exclusive resources: file:.uncle/workflow/bug-report-drafts
- Depends on: none
- Exact action: With a fake authenticated gh on PATH that logs argv and prints extra output followed by an https:// URL, run `/report` then answer ` YES `. Then run `/report` and answer `y`.
- Expected result: The ` YES ` answer triggers exactly one `gh issue create --repo unclehq/uncle` call and the URL is displayed. The draft is kept after publish. The `y` answer cancels with no gh call.
- Actual result: 
- Status: NOT RUN

### MC-206
- Exclusive resources: file:.uncle/workflow/bug-report-drafts
- Depends on: none
- Exact action: Run `/report` to arm the confirmation, then type `/clear`. Separately arm again and type `/report`. Then arm and press Enter with empty input. Check whether gh was called and whether the triage chat received any of these inputs.
- Expected result: None of these inputs publish. `/clear` cancels and then clears as normal. The repeated `/report` replaces the pending state with a fresh draft. Empty input cancels. None of the inputs reach the triage chat.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: dir:sandbox-project-bugreport
- Depends on: MC-300
- Exact action: In the sandbox, with gh unauthenticated or absent from PATH, run /report and answer `yes`.
- Expected result: No issue is created; a draft is saved and an actionable message with a copyable shlex-quoted `gh issue create --repo unclehq/uncle --title ... --body-file ...` command is shown; the TUI does not crash.
- Evidence to capture: Transcript of the message and the saved draft path.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: dir:sandbox-project-bugreport
- Depends on: MC-301
- Exact action: In recovery with an ineligible classification (e.g. code defect) and again with none, type /report and observe the banner and response.
- Expected result: The banner shows no /report hint, and /report prints the fixed refusal line, arms nothing and creates no bug-report draft.
- Evidence to capture: Transcript of both refusals and directory listing showing no new draft.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a sandbox project, trigger a stage failure so the recovery chat auto-opens and triage classifies it as a non-tool-bug (e.g. code defect). Observe the banner, then run /do N and /resume, and also type /report.
- Expected result: Recovery chat opens with diagnosis, banner shows /do N and /resume with no /report hint, /do N and /resume work as before, and /report prints the fixed refusal line with no draft created.
- Evidence to capture: Terminal transcript of the recovery session and a listing of .uncle/workflow showing no bug-report-N.md file.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Stop a stage by human stop, decline, or clean exit in the TUI and observe whether triage auto-opens.
- Expected result: Triage recovery chat does not auto-open on human stop, decline or clean exit, and no report offer appears.
- Evidence to capture: Terminal transcript or screenshot showing the TUI state after each stop type.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In recovery with a tool bug classification, run /report, then reply `no`. Then run /report again and send a normal chat message such as `why did this fail?` as the confirmation input. Then send an ordinary chat message after the cancel.
- Expected result: Each cancel prints a one-line cancellation, the confirming input is never forwarded to triage chat, no gh issue is created, and the next ordinary message after cancel reaches triage chat and gets a normal reply.
- Evidence to capture: Terminal transcript of the sequence and a listing of the bug-report-N.md drafts.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Before using /report, note the contents of any existing .uncle/workflow/triage-issue-N.md and compute its hash. Run /report through preview, cancel, then again with gh unauthenticated and answer yes, then re-hash.
- Expected result: The triage-issue-N.md files are byte-identical before and after, and new drafts appear only as separate bug-report-N.md files that are never overwritten.
- Evidence to capture: Before and after hashes of triage-issue-N.md and a listing of bug-report-*.md files.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In recovery with a pending /report confirmation armed, type /clear, then check whether the pending report is cancelled and the chat clears. Afterwards type `yes` as an ordinary message.
- Expected result: /clear cancels the pending report and performs its normal clear; the later `yes` is treated as ordinary input and publishes nothing.
- Evidence to capture: Terminal transcript showing the cleared chat and no gh invocation.
- Actual result: 
- Status: NOT RUN
