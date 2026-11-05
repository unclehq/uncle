# Change Request

Issue 165

Seeded from [unclehq/uncle#165](https://github.com/unclehq/uncle/issues/165).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Bare `uncle --noui` starts an interactive chat (REPL) without the curses UI

## Motivation

## Problem

`--noui` (added in #160) only runs a startup action headlessly:

- `uncle --noui --application 'build my application'` runs one build and exits.
- `uncle --noui` with no startup action is refused: `--noui needs a startup action ...; the menu is never shown` (exit 2, `uncle` lines ~123 and ~410).

So there is no way to use Uncle interactively without the curses UI. Someone on a plain terminal, over `ssh`, in a terminal that cannot render curses, or who just prefers scrollback, cannot have the conversation the TUI home chat provides: ask something, get an answer, ask again, then start a build when ready.

## Requested behavior

Running `uncle` with `--noui` and **no startup action** starts an interactive session without curses. It works like a chat:

1. Uncle prints a short banner (project, mode, how to quit) and a prompt.
2. The user types a line and presses Enter.
3. Uncle prints the response as plain text and shows the prompt again.
4. The user can keep chatting, then start a build from the chat (for example \`build issue 34\`, or \`create a hello world c program that runs on the command line\`), watch it run with the same plain progress output as `--noui` runs, and return to the prompt when it finishes.
5. The session ends on `/quit`, `/exit`, end of input (Ctrl-D), or Ctrl-C at an idle prompt.

`uncle --noui --application ...`, `--issue`, and `--change-request` behave as they do today (one run, then exit). Only the bare form changes. (`--housekeeping` is being removed in #164 and is not part of this.)

## What the session can do

It offers the same home-chat abilities as the TUI, as plain text:

- free-form conversation with the supervisor (the same agent, runner, model and effort the TUI home chat uses);
- starting work from natural language, through the same validated actions (`create_app`, `create_change`, `run_app`, `run_change`, `github_issue`, `stop_build`, `clear_build`, `resume_build`), with the application, not the model, executing them;
- the slash commands that make sense without a screen: `/help`, `/quit`, `/stop`, `/resume`, `/clear`, `/issue N`, `/run`, `/runstage`, `/triage`, `/do`, `/mode`, `/date` (when it exists), plus a plain-text equivalent for settings (`/settings` prints current values; editing stays in the TUI, or a simple `/set` form is a follow-up);
- whatever #164 gives the supervisor before a build starts (full Claude capabilities); this issue only provides the loop and the I/O, not those capabilities.

While a build runs inside the session, progress prints as in a `--noui` run. The prompt returns when the run finishes or stops. Attended gates ask on the same terminal and read the answer from the same input (see below).

## Observable behaviors

| Id | Trigger | Expected result | Failure behavior |
|---|---|---|---|
| R-1 | \`uncle --noui\` on a terminal | Banner and prompt; no curses, no alternate screen, no cursor-control escapes | stdin not a terminal and no input: exits cleanly at end of input, code 0 |
| R-2 | Type a question, press Enter | The response prints as plain text, then the prompt returns | Runner unavailable: a one-line error and the prompt returns; the session survives |
| R-3 | \`build issue 34\` | The issue build starts exactly as the TUI would start it; progress prints; the prompt returns when it ends | Issue not found or refused: the reason prints; the session continues |
| R-4 | \"create a hello world c program that runs on the command line\" | A brief is drafted and a new-application build starts | Same as the TUI if drafting fails |
| R-5 | Input while a build runs | Queued or answered per the rules below; never lost silently | An invalid command prints usage |
| R-6 | `/quit`, `/exit`, Ctrl-D | Session ends; a running build is stopped first, after a confirmation if attended | Child processes are not left behind |
| R-7 | Ctrl-C at the idle prompt | Cancels the current input line; a second Ctrl-C quits | n/a |
| R-8 | Ctrl-C during a build | Stops the build (resumable state, as in the TUI), then returns to the prompt | State is recorded as interrupted, not complete |
| R-9 | \`uncle --noui\` piped input (for example \`printf 'build issue 34\\n/quit\\n' \| uncle --noui\`) | Runs each line in order and exits; usable in scripts | Exit code reflects the last build result and refusals |
| R-10 | \`uncle --noui --noinput\` | Still refused as contradictory, as in #160 | Exit 2 |
| R-11 | Existing one-shot forms | Unchanged | Unchanged |
| R-12 | Output with no terminal | No prompt decoration or escape sequences; plain lines only | n/a |

## Invariants

- **I-1:** the session never imports or starts curses.
- **I-2:** every action started from the session goes through the same validated action path as the TUI; the model never starts a driver itself.
- **I-3:** the session produces the same run artifacts, state and records as the equivalent TUI or one-shot run; the headless-equivalence test from #160 extends to the REPL.
- **I-4:** a child run is never left running when the session exits.
- **I-5:** gates answered in the session are recorded exactly as in the TUI: a person-answered gate is human, a delegated one is delegated.
- **I-6:** the session keeps one conversation history, like the TUI home chat, and does not replay or leak it into driver prompts beyond what the TUI already does.

## Design questions to settle in the plan

- **Gate prompts while a build runs:** how to ask a gate question and read the answer on the same terminal without mixing it with chat input. Suggest: the gate prints a clearly marked prompt and the next line answers it; chat input is held until the gate resolves.
- **Concurrent input and output:** keep it line-based (no readline redraw races). Use readline for history and editing when stdin is a terminal and `readline` is available; plain `input()` otherwise.
- **Streaming responses:** print as they arrive, or after each reply? Suggest streaming when stdout is a terminal.
- **Unattended in a session:** a session with a person at the prompt is attended by nature, but a build started from it may run unattended per the default in #155. The banner must show the mode a started build will use, and `/mode` or `--attended` must be able to change it for builds started from the session.
- **Shared code:** the loop should call the same home-chat and action modules the TUI uses (`home_chat.py`, `home_actions.py`, `run_duties.py`, `uncle_headless.py`) and not copy TUI logic. The extraction in #160 is the starting point.
- **Prompt text and commands:** a stable prompt like `uncle> ` and a `/help` that lists commands, so scripts and tests can drive it.

## Verification

- Launcher tests with a fake runner: bare `--noui` starts the session; the former refusal is gone; `--noui --noinput` is still refused; one-shot forms unchanged.
- Session tests over a pipe: scripted conversations (question, `build issue N`, hello-world request, `/quit`) with exact stdout and exit codes; blank lines, EOF, and very long lines.
- A pty test: banner, prompt, response, Ctrl-C at idle (cancels the line, second quits), Ctrl-C during a build (stops it, prompt returns), and no cursor-control or alternate-screen bytes in the output.
- A gate test: a build started from the session reaches an attended gate; the answer line records a human approval.
- An equivalence test: the same fixture build started from the TUI, from the REPL and as a one-shot gives the same artifacts and attestation fields.
- A test for I-4: after `/quit` and after SIGTERM, no child process remains.
- Defect injection: have the REPL run a driver directly instead of the validated action, and confirm the I-2 test fails.
- Manual check: run a real session over `ssh` without a pty and with one; chat, start a small build, answer a gate, quit.

## Non-goals

- Replacing or removing the curses TUI.
- Full-screen editing, panes, or mouse support.
- Tool and capability work for the supervisor (tracked in #164).
- A JSON or machine protocol for the session (a possible follow-up).
- Changing how builds, gates, verification or PRs work.

## Related

- #160: introduces `--noui` and the headless runner this builds on; changes its behavior row N-6 (bare `--noui` is no longer refused).
- #164: gives the supervisor tools before a build; the REPL is the plain-text front end for the same agent.
- #155: default unattended mode, which affects builds started from the session.

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
