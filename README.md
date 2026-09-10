<p align="center">
  <img src="uncle.png" alt="Uncle logo" width="240">
</p>
<h1 align="center">uncle</h1>

**Build apps and ship changes with the AI agents you choose.**

> Governed CI for coding agents.

> Everyone else is building agents that run unsupervised. This is the approval
> layer that makes them acceptable in production.

</div>

Uncle is a human-gated, adversarially-audited CI pipeline for AI-generated
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

> **Just testing uncle?** Use Cline with open-weight models and configure your plan.
> Expect slower runs, but dramatically lower costs than premium models billed
> per token—a good tradeoff while trying out the workflow.

---

## Usage

1. Install Uncle.
1. Create a `REQUIREMENTS.md`, `CHANGE_REQUEST.md`, or GitHub issue.
1. `uncle`

## Install

macOS or Debian/Ubuntu/WSL (Homebrew required on macOS):

```sh
curl -fsSL https://raw.githubusercontent.com/unclehq/uncle/main/install.sh -o install.sh
bash install.sh
```

Windows PowerShell (Scoop required):

```powershell
Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/unclehq/uncle/main/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

## Use

Create a `REQUIREMENTS.md`, `CHANGE_REQUEST.md`, or GitHub issue, then run `uncle` in your project.

Choose runners per stage: Cline, Claude, Codex, Kimi, or Aider. Install your chosen clients separately. For self-hosted Aider, enter a Base URL and API key; Uncle discovers models automatically. GitHub workflows use `gh auth login`.

**Configure → Miscellaneous** sets auto mode and your approval name.

[Workflow documentation](scripts/README.md) · [Packaging](packaging/README.md)
