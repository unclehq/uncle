<div align="center">

<img src="uncle.png" alt="Uncle" width="180">



# uncle

</div>

**Give Uncle an issue. Talk to it while it works.  Get a verified pull request.**


Uncle is a terminal-native agentic software engineer that works inside your repository.

Give it requirements or a GitHub issue. Uncle plans the change, coordinates the coding agents you already use, independently reviews their work, verifies the result, and prepares the pull request with you.

Underneath, Uncle treats every software change as an integrity chain. The agents doing the work are untrusted and replaceable. Uncle establishes what was approved, what was implemented, what was reviewed, what was verified, and exactly what is being published.

**Delegate the work, not the responsibility.**

```text
                    YOU
                     ↕
                   UNCLE
                     │
                     ▼
              approved plan
                     │
                     ▼
              implementation
                     │
                     ▼
           independent review
                     │
                     ▼
                verification
                     │
                     ▼
               human approval
                     │
                     ▼
                 GitHub PR
                     │
                     ▼
              change evidence
````

## Why Uncle?

Coding agents can write code. They should not be trusted to approve their own work or describe their own work as verified.

Uncle separates the people and agents doing the work from the system establishing the integrity of the change.

* **Work with Uncle while it works.** Ask questions, provide context, redirect implementation, or discuss failures without leaving the terminal.
* **Use the agents you already have.** Uncle works with Cline, Claude, Codex, Kimi, OpenCode, and other coding agents.
* **Independent review.** The agent that writes the code does not approve its own implementation.
* **Human authority.** Consequential decisions remain explicit human approval gates.
* **Pinned intent.** Approved specifications and plans are cryptographically identified so they cannot silently change.
* **Artifact identity.** Review and verification apply to an exact Git tree, not an agent's description of the code.
* **Driver-controlled verification.** Trusted workflow state comes from Uncle, not from agent-authored prose.
* **Audited publication.** The artifact being published must be the artifact that passed the required review, verification, and approval stages.

The coding agent is untrusted and swappable. A broken or hostile agent can fail Uncle's checks, but it cannot declare itself verified.

## The change is the unit of trust

Most coding tools focus on the agent doing the work.

Uncle focuses on the **change**.

For a change to be verified, the artifact that was reviewed, verified, approved, and published must be the same artifact.

```text

Implementation       tree f12b8...
                         │
                         ▼
Independent review   tree f12b8...   PASS
                         │
                         ▼
Verification         tree f12b8...   PASS
                         │
                         ▼
Human approval       tree f12b8...
                         │
                         ▼
Publication          tree f12b8...

                         ✓
```

If the code changes after review:

```text
Review               tree f12b8...   PASS
Verification         tree f12b8...   PASS
Publication          tree 91ae3...

                         ✗
                    NOT VERIFIED
```

The review may have been valid. It just was not a review of the code being published.

Uncle treats that distinction as an invariant.

## Verifiable change provenance

> **In development**

Uncle is developing portable attestations for completed changes.

Each trusted stage produces canonical, machine-readable evidence describing what actually happened, including the artifact involved, the result, evidence digests, and producer metadata.

Results distinguish between:

```text
pass
fail
unavailable
```

Evidence records what happened. Policy decides whether that evidence is sufficient to publish.

The resulting change attestation binds together:

```text
requirements hash
       │
       ▼
approved plan hash
       │
       ▼
implementation tree
       │
       ├──────────────┐
       ▼              ▼
 review evidence   verification evidence
       │              │
       └──────┬───────┘
              ▼
        human approval
              │
              ▼
        publication tree
              │
              ▼
         attestation
```

The attestation design uses existing software supply-chain standards where possible, including **in-toto** statements and **DSSE** signing, rather than inventing a proprietary provenance format.

The goal is that a reviewer can independently answer:

> **Is the software being published the exact software that passed Uncle's required process?**

without trusting the coding agent that produced it.

See [#59: Add verifiable change provenance and portable attestations](../../issues/59) and [Attestations](ATTESTATIONS.md) for setup and verification.

## Talk to Uncle while it works

Uncle is not a fire-and-forget coding agent.

You can talk to it throughout a run.

Ask what the current stage is doing. Give additional context. Redirect implementation. Discuss a failure. Ask what a pending decision means. Tell Uncle to steer the active worker.

```text
You
  │
  │  "Why is this taking so long?"
  ▼
Uncle
  │
  │  explains current state
  ▼
You
  │
  │  "Have it use the existing parser instead."
  ▼
Uncle
  │
  │  steers active worker
  ▼
Coding agent
```

Uncle supervises the work while maintaining authority boundaries.

During a build, native runner processes are pooled by runner, permission side,
model and command profile. Once started, a compatible runner stays alive for
later stages and is terminated when the workflow driver exits. Set
`UNCLE_RUNNER_REUSE=0` to diagnose a runner with the previous one-process-per-stage behavior.

The supervisor can observe, explain, diagnose, and steer work. It cannot silently grant itself the authority to waive integrity requirements or publish changes.

You stay in the loop without having to babysit the underlying agents.

## How it works

A typical change looks like:

```text
GitHub Issue / Requirements
            │
            ▼
           Uncle
            ↕
           You
            │
            ▼
           Plan
            │
            ▼
      Human approval
            │
            ▼
      Implementation
            │
            ▼
    Independent review
            │
            ▼
       Verification
            │
            ▼
      Human approval
            │
            ▼
        GitHub PR
```

Uncle works inside your existing repository and with your existing development tools.

It does not replace your IDE, coding agents, GitHub, or CI.

The terminal is the interface.

The change is the unit of work.

Agents are workers.

Uncle is the supervisor and integrity layer.

GitHub remains the system of record.

## Uncle builds Uncle

Uncle is developed using Uncle.

Changes to this repository go through the same workflow Uncle provides to other projects:

```text
issue
  ↓
plan
  ↓
human approval
  ↓
implementation
  ↓
independent review
  ↓
verification
  ↓
human approval
  ↓
pull request
```

As Uncle's change-attestation support lands, Uncle's own changes will also produce the same portable integrity evidence it provides to other repositories.

The process isn't just documented here. It's used here.

## Quick start

Install Uncle, open a repository, and run:

```sh
cd my-project
uncle
```

Give Uncle a `REQUIREMENTS.md`, `CHANGE_REQUEST.md`, or GitHub issue.

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

Uncle can start with a GitHub issue and carry the change through planning, human approval, implementation, independent review, verification, and publication.

When the change is ready, Uncle shows you the audited diff and asks for approval before creating the commit, feature branch, push, and pull request.

Uncle stops at the pull request. Your existing GitHub review, CI, and merge controls remain the final authority.

GitHub workflows use your existing `gh` authentication:

```sh
gh auth login
```

See [GitHub integration](GITHUB_INTEGRATION.md) for setup, signing, approvals, and recovery.

### Two issues on one project: worktrees

One run per directory is the rule. To work a second issue at the same time,
run it in a git worktree beside the project:

```sh
./scripts/from-issue.sh 64 --worktree          # creates ../<project>-issue-64 on a new branch
uncle --runs                                    # #64  IMPLEMENT  locked  /path/<project>-issue-64
```

`--worktree-dir PATH` and `--branch NAME` override the defaults. The worktree
gets a copy of `.uncle/config` and its own workflow state; the branch becomes
the PR head. When the run completes, Uncle offers to remove the directory
(never the branch); `bash scripts/lib/worktrees.sh remove <dir>` does the same
later and refuses while a run holds the lock or is not `COMPLETE`. Every
worktree runs the one installed `uncle`, so do not upgrade it mid-run. Details
in [scripts/README.md](scripts/README.md#--worktree---worktree-dir---branch--run-an-issue-in-a-git-worktree).

## Recovery and supervision

Uncle includes interactive triage for failed stages and supervision for detecting and correcting problems while work is still running.

Supervision is configured with `supervision.enabled`, `supervision.runner`,
`supervision.model`, `supervision.effort`, `supervision.max_interventions`,
`supervision.steering_timeout_seconds`, `supervision.stage_time_seconds`,
`supervision.stage_tokens`, `supervision.call_timeout_seconds`,
`supervision.max_calls_per_run`, `supervision.call_max_cost_usd`, and
`supervision.delegate_gates` in `.uncle/config`.

The defaults are:

```text
supervision.enabled true
supervision.runner claude
supervision.model sonnet
supervision.effort medium
supervision.max_interventions 2
supervision.steering_timeout_seconds 120
supervision.stage_time_seconds 1800
supervision.stage_tokens 0
supervision.call_timeout_seconds 300
supervision.max_calls_per_run 8
supervision.call_max_cost_usd 0.5
supervision.delegate_gates none
```

Only `supervision.runner claude` is currently supported. Use `/delegate` for
standing dialog delegation, `/app-input` for application input, and phrases
such as “answer this one” or “tell it to” for a single explicit action.

### Authority boundary

Supervisor answers are recorded in `gate-answers.jsonl` as
`supervisor:explicit:<name>` or `supervisor:standing:<name>`. Metrics identify
their usage as usage_scope 'supervisor chat'. Decisions involving signing, publication and waiver
decisions remain with the user.

### Recovery

Recovery can diagnose stopped stages and propose repairs while preserving the
same authority boundary.

These systems operate within Uncle's authority boundaries. Protected approvals, reviewer artifacts, waivers, workflow state, and publication controls remain outside the coding agent's authority.

See the workflow documentation for the detailed supervision, triage, recovery, security, and configuration model.

## Ideas and feedback

Have an idea for Uncle or want to discuss how it should work? Start a [GitHub Discussion](../../discussions).

Found a bug or have a concrete feature request? Open an [issue](../../issues).

**Ideas start in Discussions. Work starts in Issues. Uncle takes it from there.**

---

[Workflow documentation](docs/) · [GitHub integration](GITHUB_INTEGRATION.md) · [Attestations](ATTESTATIONS.md) · [Contributing](CONTRIBUTING.md) · [License](LICENSE)

```
```
