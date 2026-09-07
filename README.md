```
                #@@@@@@##@@@@@@#
                @@@@@@@@@@@@@@@@
                @@@@@@@@@@@@@@@@
               #@@@@@@@@@@@@@@@@#
               @@@@@@@@@@@@@@@@@@
    #@@@@@@@@@ @@@@@@@@@@@@@@@@@@ @@@@@@@@@#
    @@@@@@@@@@                    @@@@@@@@@@
     @@@@@@@@@@@@@@##########@@@@@@@@@@@@@@
       #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#
          #@@##@@@@@@@@@@@@@@@@@@##@@#
       #@@@@@# @@@@@@@@##@@@@@@@@ #@@@@@#
     @@@@@@@@@  @@@@@@    @@@@@@  @@@@@@@@@
    @@@@@@@@@@@                  @@@@@@@@@@@
     @@@@@@@@@@@                @@@@@@@@@@@
      #@@@@@@@@@@              @@@@@@@@@@#
       ##@@@@@@@@@@          @@@@@@@@@@##
    #@@@@@@@@@@@@@@@@#    #@@@@@@@@@@@@@@@@#
  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
#@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#
 #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#
    #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#
       #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#
```

<div align="center">

# uncle

> Governed CI for coding agents.

> Everyone else is building agents that run unsupervised. This is the approval
> layer that makes them acceptable in production.

</div>

uncle is a human-gated, adversarially-audited CI pipeline for AI-generated
code. A primary agent plans, implements, and verifies; an independent reviewer
audits it adversarially; you approve at every gate. By default `cline` runs
every stage, on both sides.

- **Human approval gates** at every planning and review stage.
- **Adversarial review** by a second model that did not write the code.
- **SHA-256 pinned specs** so approved artifacts cannot be silently modified.
- **Immutable reviewer-owned files** the implementing agent cannot edit.
- **A green check and a diff gate** after implementation, run by the driver
  rather than by the agent that wrote the code.

Use it when the cost of an agent silently shipping the wrong thing is higher
than the cost of waiting for a human to say yes.

---

## Install

```sh
brew install uncle
```

You also need the `cline` CLI, `jq`, and bash 3.2+ (macOS system bash is fine).

Optionally install `glow` or `bat`, anywhere on your `$PATH`: a gate can then
render the document you are approving in the same window. Without one, it
shows the raw text.

Runs on macOS and Linux. On Windows use WSL or Git Bash — the drivers are bash
— and `pip install windows-curses` for the full-screen menu; without curses,
`uncle` falls back to a line-based menu.

---

## Run it

```sh
cd /path/to/your/project
uncle
```

That is the whole interface. The first run in a project opens the Configure
screen, which lists every stage of the pipeline. Open a stage and you pick the
runner that drives it, its reasoning effort, and — only when that runner is
cline — the model it runs; claude, kimi, and codex are given no model and use
their own default. Settings are saved per stage to `.uncle/config` in that
project. Later runs go straight to the menu:

| Menu item | You provide | What happens |
|---|---|---|
| **New application** | `REQUIREMENTS.md` | Plans and builds a project from a requirements brief. |
| **From GitHub issue** | an issue number or URL | Seeds the right workflow from the issue, then runs it. |
| **Change request** | `CHANGE_REQUEST.md` | Baselines, specs, plans, and implements a change to an existing codebase. |
| **Configure stages** | — | Per-stage runner, effort, and cline model. |

Runners are per side. An agent stage — which writes code — can run on `cline`,
`claude`, `kimi`, or `codex`; a reviewer stage, which must stay read-only, on
`cline`, `codex`, or `claude`. The same runner is not the same thing on both
sides: codex runs `--sandbox workspace-write` as an agent and
`--sandbox read-only` as a reviewer, and that is enforced by the shim, not by
the prompt.

Both pipelines are resumable. Interrupt one and re-run `uncle` — it picks up
where it stopped, from `.uncle/workspace/` in your project. That directory is
the only thing uncle adds to your tree.

---

## The gates

Each stage produces one document and stops. uncle asks whether to approve it
in a box in the middle of the screen: `y` continues, anything else pauses the
run and exits cleanly, and `v` opens the document itself — through `glow` or
`bat` when either is installed.

An approval records the SHA-256 of the exact bytes you read. Downstream stages
re-hash the file and refuse to run if it changed, so editing an approved
document sends it back to its gate.

After implementation there are two checks the implementing agent does not
control: the driver re-runs the verification commands from the document you
already approved — comparing them against the pre-change baseline, for a
change request — and then shows you the real diff. A regression turns that
approval into an explicit, recorded override. A final audit that does not say the change is ready stops the run.

Runs end in `READY`, `READY WITH NON-BLOCKING ISSUES`, or `NOT READY`.

For new applications, a prerequisite check runs before implementation. It
verifies access to the tools, browsers, source inputs, and reviewers required
for acceptance. Missing prerequisites pause the run. Approved verification
commands must cover the full automated acceptance suite, including browser
tests when applicable.

After the code gate, an independent test review checks coverage, assertions,
expected results, and evidence that critical tests reject representative
defects. Failed reviews or acceptance checks return to repair, then repeat the
driver checks, human diff approval, test review, and checklist. Two repair
attempts are allowed across restarts by default (`WORKFLOW_MAX_REPAIRS`, 0–100).
Missing evidence or external prerequisites pauses verification instead of
consuming repair attempts. Final audit starts only after required checks pass;
an implementation green-check override does not waive acceptance.

The updated plan also names protected tests, fixtures, helpers, and test
configuration. The driver hashes these files and directory inventories before
verification and rejects changes even when commands report success. Repairs
may change tests, but must explain each change and pass another diff approval
and independent test review. This detects changed inputs at stage boundaries;
it does not make an agent with filesystem access physically unable to edit them.

---

## Performance

To inspect runtime and reported token usage for the current project:

```sh
uncle --performance
```

The report separates agent/reviewer attempts, approval waits, driver checks,
and integrity checks. Stage runtime includes the model and its tool calls;
missing token usage is shown as unknown. Records accumulate across repairs and
restarts, so compare attempts as well as elapsed time when tuning stage effort.
Reviewer model and effort choices in Configure are passed to the reviewer CLI.

Independent checks can run concurrently when their positions are listed in an
approved `Parallel verification groups` plan section. Concurrency defaults to
two workers (`WORKFLOW_VERIFY_JOBS=1` forces sequential execution; maximum 8).
Ungrouped checks remain sequential. Protected inputs are checked around each
command, and the driver retains separate exit statuses and logs.

Integrity hashing uses one Python process when available, with the complete
portable shell implementation as a fallback. The terminal redraws on changes
instead of on every idle poll. These optimizations preserve the acceptance gates.

## Documentation

- [`QUICK_START.md`](QUICK_START.md) — end-to-end in a few minutes.
- [`REQUIREMENTS.md`](REQUIREMENTS.md) — the requirements-brief template.
- [`CHANGE_REQUEST.md`](CHANGE_REQUEST.md) — the change-request template.
- [`OUTPUT_RULES.md`](OUTPUT_RULES.md) — the shape every document a stage
  writes for you to review must have.
- [`lib/gates/GATES.md`](lib/gates/GATES.md) — the output gates every plan must
  satisfy.
- [`AGENTIC.md`](AGENTIC.md) — the design philosophy behind the gates.
- [`CLAUDE.md`](CLAUDE.md) — the agent instruction contract.
- [`scripts/README.md`](scripts/README.md) — the drivers, their stages, and
  every configuration variable, for running stages by hand.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — the contributor guide.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — before participating.

Open an issue to discuss larger changes before spending time on them.
