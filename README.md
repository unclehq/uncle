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

## Ideas and feedback

Have an idea for Uncle or want to discuss how it should work? Start a [GitHub Discussion](../../discussions).

Found a bug or have a concrete feature request? Open an [issue](../../issues).

**Ideas start in Discussions. Work starts in Issues. Uncle takes it from there.**

---

[Workflow documentation](scripts/README.md) · [Packaging](packaging/README.md) · [License](LICENSE)
