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

---

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
