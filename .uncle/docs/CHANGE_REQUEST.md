# Change Request

Issue 164

Seeded from [unclehq/uncle#164](https://github.com/unclehq/uncle/issues/164).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Home chat supervisor does anything before a build (full Claude capabilities); remove housekeeping

## Motivation

## Problem

When Uncle is not running a build, the home chat can do very little beyond starting one. It cannot clone or fork a repo, create a directory and work in it, or run an ordinary command. Housekeeping was added to cover some of that, but it is a separate mode with its own CLI flag, driver, policy and TUI settings, and it restricts the agent to an allowlist and disallow list. Two chat modes (`housekeeping` and `supervisor`) with different powers is confusing, and neither is the general assistant that is wanted.

## What exists today (from the code)

- The home chat has two modes (`uncle_tui.py`, `/mode housekeeping|supervisor`). The default is `housekeeping`: a persistent tool-enabled agent (`housekeeping_session.py`) whose commands are checked against a deny list. The `supervisor` mode is the tool-free chat that proposes validated actions.
- The tool-free chat (`home_chat.py`, `home_actions.py`) turns requests into one validated action (`create_app`, `create_change`, `run_app`, `run_change`, `github_issue`, `stop_build`, `clear_build`, `resume_build`). The prompt tells it to \"not run commands or write files yourself\", and the application starts the build. This is how \"build issue 34\" works.
- Housekeeping footprint:
  - launcher: `uncle --housekeeping [TEXT]`, `UNCLE_STARTUP_ACTION=housekeeping`, usage text and mutual-exclusion lists;
  - driver and libs: `scripts/housekeeping-workflow.sh`, `housekeeping_config.py`, `housekeeping_input.py`, `housekeeping_policy.py`, `housekeeping_session.py`;
  - TUI: the `/housekeeping` command, `/mode`, the Configure > Miscellaneous > housekeeping disallow list, about 77 mentions in `uncle_tui.py`, and entries in `run_duties.py`, `uncle_headless.py` and `mode.sh`;
  - README text (9 mentions) and five test files: `housekeeping-input-test.py`, `housekeeping-launcher-test.sh`, `housekeeping-policy-test.py`, `housekeeping-session-test.py`, `housekeeping-workflow-test.sh`, plus `tui-housekeeping-test.py`.

## Requested behavior

1. **Remove housekeeping completely.** No `--housekeeping`, no `/housekeeping`, no housekeeping driver, policy, disallow list or Configure entry, no `housekeeping` home-chat mode, no tests or docs for it. The launcher treats `--housekeeping` as an unknown option (with the usual did-you-mean hint that does not suggest a removed flag).
2. **One home-chat agent: the supervisor.** Before a build starts, it has all of Claude's capabilities: run shell commands, read and write files, use `git` and `gh`, create directories, change into them, fetch from the network, and so on. Examples it must handle in plain language:
   - \"fork unclehq/uncle and clone it here\"
   - \"make a directory called demo and work in it\"
   - \"clone https://github.com/owner/repo and tell me what's in it\"
   - \"what changed on main since yesterday\"
3. **Keep starting builds from chat.** Everything the supervisor does today to start work stays:
   - \"build issue 34\" starts the issue workflow for issue 34;
   - \"create for me a hello world C program that runs on the command line\" drafts the brief and starts a new-application build;
   - the existing `create_change`, `run_app`, `run_change`, `stop_build`, `clear_build` and `resume_build` actions keep working.
4. **Working directory follows the conversation.** When the agent creates a directory and moves into it (or clones a repo and moves into it), that directory becomes the project a following \"build ...\" request targets. The status bar and terminal title show it.
5. **Scope in time.** The full capabilities apply when no build is running. While a build runs, the supervisor keeps its current limited, tool-free role (steering and answering questions about the build), so it cannot interfere with a run in progress.

## Observable behaviors

| Id | Trigger | Expected result | Failure behavior |
|---|---|---|---|
| S-1 | \"fork unclehq/uncle\" with no build running | The agent forks the repo and reports the result | Command failure is shown with its output; nothing is reported as done that was not |
| S-2 | \"make a directory demo and move into it\" | Directory created; the supervisor's working directory (and shown project) becomes `demo` | Directory exists or is not writable: explained, working directory unchanged |
| S-3 | \"clone owner/repo\" then \"build issue 34\" | The clone becomes the project and issue 34 is built from that repository | Issue not found or origin mismatch: refused with the reason |
| S-4 | \"build issue 34\" | Starts the issue build exactly as today | Same failure handling as today |
| S-5 | \"create a hello world c program that runs on the command line\" | A brief is drafted and a new-application build starts, as today | Same as today |
| S-6 | Any request while a build runs | Only the limited supervisor role applies; no shell or file tools | Request for a command is declined with a note that a build is running |
| S-7 | `uncle --housekeeping ...` | Unknown option; usage shown | Exit non-zero, nothing started |
| S-8 | `/housekeeping` or `/mode housekeeping` | Not recognized | Same as any unknown command |
| S-9 | Configure > Miscellaneous | No housekeeping entry | n/a |
| S-10 | A project's `.uncle/config` containing old `housekeeping.*` keys | Ignored without error | Never crashes or re-enables anything |
| S-11 | A command that needs approval | Uses the normal Claude permission flow: the TUI asks in attended mode; the unattended behavior is decided under open questions | Never bypasses permissions silently |

## Invariants

- **I-1:** no code path, flag, setting, test or doc refers to housekeeping after the removal, except a migration note for ignored legacy config keys.
- **I-2:** a build is started only through the validated action path that exists today (the application validates and executes the action), never by the agent running the driver itself.
- **I-3:** while a build runs, the supervisor has no tools.
- **I-4:** the agent never claims an action completed unless the application or the command's real result says so.
- **I-5:** the agent uses Claude's normal permission system; Uncle does not pass permission-bypass flags (the project's rule against unsafe bypass flags still applies).

## Open questions (need decisions in the plan)

- **Permissions and unattended mode:** \"all of Claude's capabilities\" means arbitrary commands, and the earlier housekeeping design relied on a deny list as its safety boundary. With that removed, what governs approval? Suggest: Claude's standard permission prompts, answered by the user in the TUI; and in `--unattended`/`--noui` runs, where there is no one to ask, the chat agent is not available (it only exists when someone is typing). Confirm that this is acceptable, since a home chat implies a person is present.
- **Runner:** the chat agent needs a runner with tools and a permission model. Claude only (like housekeeping), or also codex and kimi where they can be made equivalent?
- **Untrusted content:** the agent will read repositories, issues and web pages. State the policy for text that tries to instruct it (the existing sanitization of untrusted excerpts may not be enough once the agent can act).
- **Session lifetime:** the old housekeeping session was persistent and primed at startup. Keep one persistent session for the home chat, and how it hands off when a build starts and ends.
- **Cost controls:** the existing per-call budget (`call_max_cost_usd`) applies to a tool-free supervisor. Decide the limits for a tool-enabled one.
- **Relationship to other issues:** this supersedes the housekeeping design in #148 and the housekeeping parts of #151, and affects #155 (default unattended) and #160 (`--noui`), which both mention housekeeping. Those issues should be updated or closed with a pointer here.

## Verification

- Launcher tests: `--housekeeping` is rejected; usage and did-you-mean text do not mention it; mutual-exclusion and stdin rules still hold for the other options.
- TUI tests: `/housekeeping`, `/mode`, and the Configure entry are gone; the supervisor with no build running accepts and executes a scripted command (fake runner), changes directory, and the next build request targets the new directory.
- Action tests: \"build issue 34\" and the hello-world request still map to the same validated actions (golden transcripts from the current behavior).
- A test for I-3: with a build running, the supervisor session is started with no tools.
- A test for I-2: a chat request cannot start a driver except through the validated action.
- A static test that no file in the repository matches `housekeeping` outside the migration note and this issue's removal tests.
- Defect injection: give the supervisor tools while a build runs, and confirm the I-3 test fails.
- Manual check: from an empty directory, ask the supervisor to fork a repo, clone it, then build an issue in it; then ask it for a hello world C program.

## Non-goals

- Changing how builds, gates, verification or PRs work.
- A new permission model; this uses Claude's existing one.
- Keeping any part of the housekeeping allowlist or disallow-list design.
- Giving the supervisor tools during a build.

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
