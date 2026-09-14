<p align="center">
  <img src="uncle.png" alt="Uncle logo" width="240">
</p>

<h1 align="center">uncle</h1>

**Give Uncle an issue. Talk to it while it works. Get a reviewed pull request.**

Uncle is a terminal-native agentic software engineer that works inside your repository. Give it requirements or a GitHub issue, collaborate with it while it works, and approve the result when it's ready.

Underneath, Uncle acts as an integrity layer for AI-generated software changes. Planning, implementation, independent review, verification, and publication are separated by enforced trust boundaries and human approval gates.

**Delegate the work, not the responsibility.**

```text
GitHub Issue / Requirements
            ↓
          Uncle
            ↕
          You
            ↓
          Plan
            ↓
      Human approval
            ↓
     Implementation
            ↓
    Independent review
            ↓
       Verification
            ↓
      Human approval
            ↓
        GitHub PR
```

## Why Uncle?

Coding agents can write code. They shouldn't be trusted to approve their own work.

Uncle enforces the integrity of a change from request to pull request:

* **Work with Uncle while it works.** Ask questions, provide context, or redirect it without leaving the terminal.
* **Human approval gates** before consequential changes advance.
* **Independent adversarial review** by an agent that did not write the code.
* **SHA-256 pinned specs** so approved artifacts cannot silently change.
* **Immutable reviewer-owned files** the implementing agent cannot edit.
* **Driver-run verification and diff gates** independent of the coding agent.
* **Audited GitHub handoff** from issue to pull request.

Uncle works with the coding agents you already use, including Cline, Claude, Codex, Kimi, and OpenCode.

It doesn't replace your IDE, agents, GitHub, or CI. It coordinates the work and establishes the integrity of the change flowing between them.

## Uncle builds Uncle

Uncle is developed using Uncle.

Changes to Uncle itself go through the same issue → plan → implementation → independent review → human approval → pull request workflow Uncle provides to other repositories.

The process isn't just documented here. It's used here.

## Quick start

Install Uncle, open a repository, and give it a `REQUIREMENTS.md`, `CHANGE_REQUEST.md`, or GitHub issue.

```sh
uncle
```

Then work with Uncle while it works.

## Install

See [Prerequisites](PREREQUISITES.md) for required tools, AI clients, authentication, and self-hosted model setup.

### macOS or Debian/Ubuntu/WSL

Homebrew is required on macOS.

```sh
curl -fsSL https://raw.githubusercontent.com/unclehq/uncle/main/install.sh -o install.sh
bash install.sh
```

### Windows PowerShell

Scoop is required.

```powershell
Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/unclehq/uncle/main/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

## GitHub

Uncle can start with a GitHub issue and carry the change through planning, implementation, independent review, verification, and human approval.

When the change is ready, Uncle shows you the audited diff and asks for approval before creating the commit, feature branch, push, and pull request.

**Uncle stops at the pull request.** Your existing GitHub review, CI, and merge controls remain the final authority.

GitHub workflows use your existing `gh` authentication:

```sh
gh auth login
```

See [GitHub integration](GITHUB_INTEGRATION.md) for setup, signing, approvals, and recovery.

## When a run stops

A stage failure writes `.uncle/workflow/TRIAGE.md` -- the state, the failing
stage's log tail and reports, `IMPLEMENTATION_NOTES.md`, the repair count and
source, the green check, and the plan rows those reports cite -- and the
screen opens a triage chat seeded with it. A declined gate, a cancel, or a
stop you chose does not.

At any other stop (an approval, a repair-limit or waiver prompt, any
`[Y/N]`/`ENTER` prompt) press `t`, or type `/triage` in the composer, to open
the same chat beside the pending prompt. Esc returns; the prompt is still
waiting and only your own keystroke answers it.

The triage model replies with what failed, a classification (`code defect`,
`requirement gap`, `needs owner decision`, `tool bug`), and one to three
numbered proposals. Nothing runs until you press the number or type `/do N`.
It works in a sandbox copy of the project; when a selected proposal ends, its
edits to source, tests, and reports are copied into the tree and recorded in
`.uncle/workflow/triage-actions.tsv`. Writes to `approvals/`, reviewer
artifacts, `waivers/`, driver state, and the installed uncle tree are refused
and reverted. `r` or `/resume` relaunches the driver from its recorded state,
so an edited plan reopens its gate and an edited test trips the integrity
check, as they would for any other edit. The ledger is printed at COMPLETE.

Configure the model under the `triage` row (`triage.runner`, `triage.effort`,
`triage.model`); unset, it uses the runner's defaults.

## Supervision (opt-in)

Triage waits for a failure exit and for you. Supervision is the earlier,
narrower step: with `supervision.enabled true` in `.uncle/config` (Configure
→ Supervision), the screen -- or, for a run started from a terminal, the
driver's lock parent -- watches the run's own status events and asks a
tool-free model for one diagnosis when, and only when, one of four things
happens:

1. a driver validator rejects a stage's output (missing or empty artifact,
   enforced document budget, acceptance or implementation-completion check);
2. the same failure signature (stage, exit status, first diagnostic line)
   recurs on the next attempt with the workflow state unchanged;
3. a steering message was accepted by the stage but not answered within
   `supervision.steering_timeout_seconds` of active stage time;
4. a stage exceeds `supervision.stage_time_seconds` of active time (gate
   waits excluded) or `supervision.stage_tokens` reported tokens.

Disabled, or enabled with every stage succeeding, no supervisor process is
started and every stage prompt is byte-identical to today's.

The reply is one strict JSON object that selects an action -- `steer`,
`retry`, `ask` or `none` -- and a fixed correction template
(`revisit_validator`, `respond_steering`, `reassess_progress`). The
correction a stage receives is that template filled only from
driver-generated fields (validator name, artifact, attempt, stage,
measurement); the untrusted excerpt behind it -- a validator diagnostic, a
steering message -- is appended separately, quoted line by line under a
heading that says it is data, not instructions. For `steer` and `retry`
the model's `diagnosis` must repeat, word for word, the driver's own
description of a cited evidence id and its `rationale` must be the fixed
sentence for that template; any other wording is rejected. For `ask` and
`none` the prose is shown to you and nowhere else. A proposal for another
stage, attempt or run, an unknown template, extra keys, a file path, tool
call, or request for approval, waiver, commit, publication, permission or
skipped tests in its text, or a stage that has moved on is rejected and
changes nothing. Corrections are bounded: `supervision.max_interventions`
per stage per run (default 2), `supervision.max_calls_per_run` supervisor
calls (default 8), one call at a time, each with
`supervision.call_timeout_seconds` and `supervision.call_max_cost_usd`. The
next trigger past a bound asks you and calls nothing.

`steer` goes down the stage's steering channel and is reported as queued,
accepted, answered, unconfirmed or rejected -- acceptance is not an answer.
An answer is recorded only when the runner can tie a reply to the message:
`claude` (one response per submitted input, in order), `self-hosted`
OpenCode (a reply names its user message), or the marker a supervisor
correction asks the stage to begin with. `codex`, `cline` and `kimi` accept
steering but give no such tie: their messages end as `unconfirmed`, the
unanswered-steering trigger does not run for them, and a correction that
ends unconfirmed asks you to check the stage output. Every transition is
written to the journal before it is shown, so a resume can explain it. A
stage that has ended, or one without a channel (reviewer stages, a run
without the screen), keeps the correction in
`.uncle/workflow/supervision/retry-note-<stage>.json`; `retry` relaunches the
driver through its ordinary entry, so approval hashes, integrity checks and
the repair limit run again, and the note is appended to that stage's prompt
once: the launch claims it (`retry-note-<stage>.launch`) before the prompt
is built, so a second launch under the same reservation runs without it. A
note whose run, state digest or target attempt no longer matches is left
alone.

Every trigger, call, proposal and delivery is journalled in
`.uncle/workflow/supervision/interventions.json` (authoritative counters,
survives resume) and `ledger.jsonl` (audit); rows carry the run, stage,
attempt, trigger, call and action ids that join a sanitized copy of the
proposal to its disposition and delivery. Each call writes a
`kind=supervisor` record under `.uncle/workflow/metrics/` with tokens, cost,
duration and the same ids, `null` when unknown; stage totals exclude them.
One process owns a workflow's supervision at a time (`supervision/owner.lock`,
a kernel file lock held from before the journal is read until the host
closes); a second screen or terminal over the same checkout reports
"Supervision unavailable" and that run continues unsupervised.

Authority boundary: the supervisor cannot approve, waive, commit, sign,
publish, change permissions, edit files, or invoke git. It runs `claude` in
bare mode with no tools, no settings, no session, an empty temporary working
directory and an allowlisted environment (`PATH`, locale, temporary `HOME`,
and `ANTHROPIC_API_KEY` if set). The worker is an owned process tree: its
combined output is capped at 1 MiB while it runs and the tree is killed at
that cap, at `supervision.call_timeout_seconds`, on cancel, and when the
process hosting supervision exits (a POSIX session with a parent watch; a
Windows Job with kill-on-close). Only `supervision.runner claude` is
supported; any other value reports "Supervision unavailable" and does
nothing. The supervisor path never invokes the triage guard or a live-tree
copy. Triage keeps its place: a failure exit still opens triage, an in-flight
diagnosis is cancelled and charged, and queued triggers run after the triage
turn only if the state digest still matches. The context a diagnosis sees
is bounded: the head of the stage's task prompt, the tail of the rejected
report and of the stage log (each read only from inside the project or the
uncle checkout, never through a symlink out of them), the validator
diagnostic, recent output, pending steering and the run's own history, all
redacted and cut to 98 KiB by dropping entries in a fixed order.

Recovery: `supervision.enabled false` is read again at every stage boundary,
on every poll and before every effect, so it stops the current run's
supervisor too: an in-flight diagnosis is cancelled and charged, a reply
that arrives after the switch is discarded, and counters are kept (the
screen says so once). Delete a `retry-note-*.json` to discard a retained
correction. A note reported `uncertain` (the driver launched its prompt but
exited before the stage confirmed receipt) is never replayed by itself and
stays charged: run `python3 scripts/lib/supervisor.py note-resolve
--state-dir .uncle/workflow --stage <stage> --redeliver` to deliver it on
the next attempt, or `--discard` to drop it. Move `interventions.json` aside
if it is reported unreadable (corrections stay disabled, the run is
unaffected). Secrets: every line sent to the supervisor is filtered for
credential assignments, authorization headers, URL credentials, token
patterns, and the values of credential-bearing keys in the environment and
in `.uncle/config`; suspect lines are replaced wholesale, and a private-key
block is removed from its BEGIN line through its END line or the end of the
text.

Keys and defaults: `supervision.enabled false`, `supervision.runner claude`,
`supervision.model sonnet`, `supervision.effort medium`,
`supervision.max_interventions 2`, `supervision.steering_timeout_seconds 120`,
`supervision.stage_time_seconds 1800`, `supervision.stage_tokens 0`,
`supervision.call_timeout_seconds 300`, `supervision.max_calls_per_run 8`,
`supervision.call_max_cost_usd 0.5`. An unknown or invalid `supervision.*`
value disables corrections with a message naming the key; no limit is ever
substituted.

## Ideas and feedback

Have an idea for Uncle or want to discuss how it should work? Start a [GitHub Discussion](../../discussions).

Found a bug or have a concrete feature request? Open an [issue](../../issues).

**Ideas start in Discussions. Work starts in Issues. Uncle takes it from there.**

---

[Workflow documentation](scripts/README.md) · [Packaging](packaging/README.md) · [License](LICENSE)
