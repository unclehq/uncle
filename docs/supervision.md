# Recovery and supervision

Uncle includes interactive triage for failed stages and supervision for detecting and correcting problems while work is still running.

Supervision is configured with `supervision.enabled`, `supervision.runner`,
`supervision.model`, `supervision.effort`, `supervision.max_interventions`,
`supervision.steering_timeout_seconds`, `supervision.stage_time_seconds`,
`supervision.stage_tokens`, `supervision.call_timeout_seconds`,
`supervision.max_calls_per_run`, `supervision.call_max_cost_usd`,
`supervision.delegate_gates`, and `supervision.files_allowlist` in
`.uncle/config`.

The defaults are:

```text
supervision.enabled true
supervision.runner claude
supervision.model sonnet
supervision.effort low
supervision.max_interventions 2
supervision.steering_timeout_seconds 120
supervision.stage_time_seconds 1800
supervision.stage_tokens 0
supervision.call_timeout_seconds 300
supervision.max_calls_per_run 80
supervision.call_max_cost_usd 0.5
supervision.delegate_gates none
supervision.files_allowlist package.json,package-lock.json,vite.config.js
```

Supervision works with any runner and any model. `supervision.runner` accepts
`claude`, `codex`, `kimi`, `self-hosted`, `aws-bedrock`, `opencode` and `aider`,
and `supervision.model` is any model identifier the chosen runner accepts (a
token of letters, digits and `. _ / : -`). Uncle passes it to the runner
unchanged, so a model has to exist for that runner: supervision does not keep a
list of models of its own.

Two details depend on the runner:

- `supervision.model sonnet` is the default and is only a Claude selector. With
  `codex` it means "use Codex's configured default model", and with `kimi` it
  means the configured Kimi default; set `kimi:<alias>` to pick a specific Kimi
  model. A model of any other form is ignored by `kimi`.
- `self-hosted`, `aws-bedrock`, `opencode` and `aider` take their model from the
  stage's runner configuration (`uncle` → Configure), so the stage must be
  configured before supervision can use that runner.

Use `/delegate` for standing dialog delegation, `/app-input` for application
input, and phrases such as “answer this one” or “tell it to” for a single
explicit action.

`supervision.files_allowlist` is a comma-separated list of repository-relative
paths that a parallel implementation step may write without the plan having
declared it as that step's owner. Implementation fan-out otherwise refuses to
merge a whole group when any step touches a file it did not claim, because an
unclaimed write usually means the plan's ownership partition was wrong. These
are the recurring exceptions: a step's own setup command (`npm install`
adding a dev dependency) legitimately rewrites `package.json`/`package-lock.json`
from whichever step happens to need a new package, not only the step that
scaffolded them, and a step configuring the dev server or test runner
(adding a test plugin, an alias, a proxy) legitimately rewrites
`vite.config.js` from whichever step needs that configuration, not only the
step that scaffolded the project.

### Authority boundary

Supervisor answers are recorded in `gate-answers.jsonl` as
`supervisor:explicit:<name>` or `supervisor:standing:<name>`. Metrics identify
their usage as usage_scope 'supervisor chat'. Decisions involving signing, publication and waiver
decisions remain with the user.

### Recovery

Recovery can diagnose stopped stages and propose repairs while preserving the
same authority boundary.

These systems operate within Uncle's authority boundaries. Protected approvals, reviewer artifacts, waivers, workflow state, and publication controls remain outside the coding agent's authority.

### Home chat agent

In the TUI home screen, typing free text that is not a slash command hands it
to a home-chat agent. It answers questions and does ad-hoc chores (such as
deleting merged branches) in the repository using its normal tools, instead of
starting a workflow.

The text for a workflow can also come from stdin:
`cat spec.md | uncle --application`. A bare `--application` with no text reads
piped stdin; on an interactive terminal with nothing piped it refuses with an
"empty input" error. Empty input is refused. A value starting with `--` is
treated as the next option, not as text, so text that begins with `--` must use
the `=` form: `uncle --application="--foo bar"`.

See the workflow documentation for the detailed supervision, triage, recovery, security, and configuration model.

## Runner reuse

During a build, native runner processes are pooled by runner, permission side,
model and command profile. Once started, a compatible runner stays alive for
later stages and is terminated when the workflow driver exits. Set
`UNCLE_RUNNER_REUSE=0` to diagnose a runner with the previous one-process-per-stage behavior.
