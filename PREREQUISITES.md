# Prerequisites

Uncle needs a supported shell, its command-line dependencies, and at least one configured AI client. The installer installs Uncle's package dependencies. It does not install or authenticate AI clients, host models, or install your project's tools.

## Operating system

| Platform | Requirements |
|---|---|
| macOS | Homebrew and a terminal. The installer supplies Git, Python, jq, and gh; macOS supplies Bash and curl. |
| Debian / Ubuntu | apt and permission to install packages with sudo. The installer supplies the declared dependencies. |
| Windows with WSL | A Debian/Ubuntu WSL environment. Install Uncle and its clients inside WSL. |
| Native Windows | Scoop, Git for Windows, and Python. The Scoop package supplies Git, Python, jq, and gh. PowerShell launches Uncle through Git Bash. |

For the full-screen UI on native Windows, install curses support in the Python environment used by Uncle:

```powershell
python -m pip install windows-curses
```

If Windows opens the Microsoft Store instead of Python, disable the conflicting Python app execution aliases or correct your `PATH`.

## Command-line tools

These commands must be available to the shell that runs Uncle:

| Tool | Purpose |
|---|---|
| Bash 3.2+ | Runs workflows and adapters. |
| Python 3.9+ | Runs the UI and workflow helpers. Homebrew installs Python 3.13. AI clients may require a newer Python version. |
| Git | Tracks project changes and review diffs. |
| jq | Processes agent events and metrics. |
| curl and trusted CA certificates | Downloads packages and accesses HTTPS services. |
| gh | Reads GitHub issues and performs authorized issue actions. Authentication is needed for private repositories and issue closing. |

The full-screen UI also needs a working Python `curses` module and an interactive terminal. Agent executables must be on `PATH` in that same environment.

## AI clients

Install and configure every client selected in **Configure → Configure stages**. You do not need all five.

| Runner | Required executable | Setup |
|---|---|---|
| Cline | `cline` | Configure its provider, credentials, and model access. Cline is Uncle's default runner. |
| Claude | `claude` | Authenticate the Claude Code client. |
| Codex | `codex` | Authenticate the Codex client. |
| Kimi | `kimi` | Authenticate the Kimi client. |
| Self hosted | `opencode` | Configure an OpenAI-compatible model endpoint in Uncle, as described below. |

Before starting a workflow, confirm each selected client can run from your terminal and access its model. Hosted providers may require a subscription or funded API account. Uncle does not provide model access.

### Self hosted

You need a running model server, enough server resources for the chosen model, and network access from Uncle to that server. Uncle talks to the server directly over its OpenAI-compatible HTTP API; it does not host the model.

In **Configure → Configure self hosting**, enter:

- **Base URL:** the OpenAI-compatible API root, such as `http://localhost:8000/v1`.
- **API key:** the endpoint's credential. For an unauthenticated server, use a placeholder such as `local`.

The endpoint must support authenticated `GET <Base URL>/models` discovery and chat completions. Select a model for each stage, or apply one to all stages.

The server must support the requested context size and return responses within the configured timeouts. Successful model discovery alone does not prove that inference works.

The model must support tool calls for implementation and file inspection. Uncle runs its own tool loop (read, search, write, edit and shell tools confined to the project) with a fresh conversation per stage, at temperature 0. The requirements stage (`requirements` and `requirements-investigate`) is the exception and runs at temperature 1. Change either with `<stage>.temperature` (or `self-hosted.temperature` for all stages) in `.uncle/config`, or with `WORKFLOW_SELF_HOSTED_TEMPERATURE_<STAGE>` / `WORKFLOW_SELF_HOSTED_TEMPERATURE` in the environment (0 to 2; environment wins over config, a stage's own setting wins over the global one, and workers inherit from their stage).

**Reasoning effort (direct HTTP).** Requests send the stage's effort as `reasoning_effort`. The existing `WORKFLOW_EFFORT_<STAGE>` override wins, followed by the runner's explicit effort argument, `<stage>.effort`, the inherited parent stage's effort, global `effort`, then `low`. Workers inherit their parent; requirements and plan-section workers inherit `project-plan`. Uncle's `none` and `minimal` map to `low`, `medium` stays `medium`, and `high`, `xhigh`, and `max` map to `high`. This portable mapping does not disable model thinking. Set `self-hosted.reasoning-effort off` in `.uncle/config`, or `WORKFLOW_SELF_HOSTED_REASONING_EFFORT=off`, to omit the field and use the server default. The switch defaults to `on`; the environment wins. Unsupported fields are retried without effort, independently of schema enforcement, and remembered per Base URL for the lifetime of the runner process. A server may accept but ignore the hint, including Ollama's native schema endpoint.

Recommended starting settings are `low` for mechanical extraction, section formatting, checklist assembly and requirements investigation; `medium` for architecture and implementation; and `high` for adversarial review, repair and final audit. These are recommendations, not new automatic stage overrides: existing stage config and environment settings remain authoritative. For example, set `project-plan.effort medium`, `implementation.effort medium`, `adversarial-review.effort high`, `repair.effort high`, and `final-audit.effort high`. Use `WORKFLOW_EFFORT_REQUIREMENTS_INVESTIGATE=low` to override the inherited planning setting for requirements alone. Validate quality and latency on your model before raising every stage to high.

**Extra request options (direct HTTP).** Uncle stays model-agnostic: to supply
server-specific fields, set `self-hosted.request-options <json object>` for all
self-hosted stages, or `<stage>.request-options <json object>` for one stage in
`.uncle/config`. The default is no options. The value must be a single-line JSON
object of at most 4,096 UTF-8 bytes; invalid values fail stage startup. Quoted
`#` characters and whitespace inside JSON strings are preserved; an unquoted
`#` starts a trailing config comment.

Precedence is `WORKFLOW_SELF_HOSTED_REQUEST_OPTIONS_<STAGE>`, then
`WORKFLOW_SELF_HOSTED_REQUEST_OPTIONS`, then `<stage>.request-options`, then
`self-hosted.request-options`. Uppercase the stage name and replace dashes with
underscores for its environment variable. Derived stages look up their own
name, then the existing model/effort parent mapping within each level:
`project-plan-section-*` and requirements inherit `project-plan`, review and
other workers inherit their parent, and investigation stages inherit their
configured stage. Preview parts inherit preview's selected model stage.
Each selected object **replaces** the less-specific object; `{}` opts out.
For example, a global environment override wins over a stage's config `{}`;
use the stage environment variable to opt out in that case.

Options apply to tool turns, closing answers, schema/reviewer requests, and
retries. When both existing and supplied top-level values are objects, Uncle
merges their immediate members, with supplied members winning (no recursive
merge). Otherwise, an existing Uncle value wins. These top-level keys are
protected and rejected at config read: `model`, `messages`, `tools`,
`tool_choice`, `stream`, `stream_options`, `response_format`,
`structured_outputs`, `guided_json`, `format`, `options`, `max_tokens`,
`max_completion_tokens`, `max_output_tokens`, and `num_predict`. This preserves
schema enforcement and token limits, including Ollama's native containers.

A 4xx error naming an applied option key (including a nested key) triggers one
retry without options. A generic 400 triggers a probe without options; Uncle
disables them only if that otherwise-identical request succeeds. Rejections
are remembered per Base URL for the runner process, independently of effort
and schema support. The stage log records applied top-level key names and one
warning when options are disabled, without recording option values. This
setting does not affect Claude, Codex, Kimi, or Cline.

For DeepSeek on vLLM, a server-specific example is:

```text
self-hosted.request-options {"chat_template_kwargs":{"thinking":false}}
adversarial-review.request-options {}
```

For Qwen servers that accept `enable_thinking`, use this instead:

```text
self-hosted.request-options {"chat_template_kwargs":{"enable_thinking":false}}
```

As a starting recommendation, turn thinking off for mechanical stages:
requirements, project-plan, preview-build, updated-plan, preflight,
execute-checklist, and implementation for small changes. Leave the server's
thinking behavior enabled for judgment stages: adversarial-review, repair,
test-review, and final-audit. This is a recommendation, not a default; `{}`
leaves the server's behavior unchanged rather than forcing thinking on. For
example, this DeepSeek configuration uses explicit stage choices:

```text
self-hosted.request-options {}
requirements.request-options {"chat_template_kwargs":{"thinking":false}}
project-plan.request-options {"chat_template_kwargs":{"thinking":false}}
preview-build.request-options {"chat_template_kwargs":{"thinking":false}}
updated-plan.request-options {"chat_template_kwargs":{"thinking":false}}
preflight.request-options {"chat_template_kwargs":{"thinking":false}}
execute-checklist.request-options {"chat_template_kwargs":{"thinking":false}}
implementation.request-options {"chat_template_kwargs":{"thinking":false}}
adversarial-review.request-options {}
repair.request-options {}
test-review.request-options {}
final-audit.request-options {}
```

**Tool turns and input context (direct HTTP).** The model is prompted to request independent reads/searches together. Every tool call in an assistant message executes in order, including calls after a tool error, before the next model request; writes and shell commands retain their ordering and permissions. Affirmative read directives with backtick-quoted paths can supply small text files and authoritative `.uncle/workflow/documents/*.json` inputs at stage start. Prefetch shares the read cache's 24 KiB result/context bounds, excludes secrets and symlinks, and does not enumerate the repository. Already embedded or cached inputs are not duplicated. Cached ranges remain explicit and changed files are invalidated; supplied context never replaces verification. `self-hosted.prefetch` / `WORKFLOW_SELF_HOSTED_PREFETCH` default to `on`; `off` disables prefetch, and the existing `WORKFLOW_READ_CACHE=0` also disables it. Environment settings win over config. Leading `<think>...</think>` blocks and separately returned `reasoning_content` / `reasoning` are kept out of answers and outgoing history; a reasoning field is replayed only if the server explicitly rejects a continuation because it requires that field. Other runners are unaffected.

**Schema enforcement.** When a stage owes a known JSON artifact, its final answer is a request that carries the artifact's JSON schema. Uncle asks the server to enforce it in the strongest form it accepts, and falls back cleanly when a server rejects one: Ollama's native `format`, then OpenAI-style `response_format` (JSON schema), vLLM's `structured_outputs` and `guided_json`, then plain JSON-object mode, then prompt-only. Every answer is also checked against the schema locally, and a workflow document the model writes itself is refused at the write if it does not match. Stages whose answer is prose, such as chat, have no schema and are not constrained.

**Planning concurrency.** Self-hosted project-plan sections and updated-plan edit
writers run with at most four workers per pool. Set `self-hosted.stage-jobs 1`
in `.uncle/config`, or `WORKFLOW_SELF_HOSTED_STAGE_JOBS=1`, for a server that
serves one request at a time. Values 1–8 are accepted; the environment overrides
the config and invalid values warn and use 4. This changes only self-hosted
planning; Claude, Codex, Kimi and Cline retain their existing scheduling.
Project-plan sections wait for their outline when needed, retain one retry,
and assemble in canonical order. Updated-plan reviews with at least five
findings use two findings per writer; conflicting edits still go through the
resolver and all publication checks remain in place. Failed batches fall back
to the compact writer after workers finish. One worker keeps the
single compact updated-plan call. The existing
`WORKFLOW_UPDATED_PLAN_PARALLEL_THRESHOLD` (5) and
`WORKFLOW_UPDATED_PLAN_PARALLEL_SLICE` (2) adjust that split;
`WORKFLOW_UPDATED_PLAN_COMPACT=0` selects the existing full panel path.
The worker limit includes section retries and edit-writer/resolver retries;
it is per pool, not a server-wide cap. Preview work, other existing panels,
and optional candidate racing can add concurrent requests. No new API fields
or server-specific features are required.

**Connections.** Uncle keeps one persistent connection per server and reuses it for every request in a stage, reconnecting once if the server closed it while idle. HTTP/2 is used when it can be negotiated: over `https` (via ALPN) when the optional `httpx` and `h2` Python packages are installed. Plain `http` servers speak HTTP/1.1 keep-alive. Most local servers do not accept HTTP/2 without TLS; if yours does (for example Hypercorn), set `WORKFLOW_SELF_HOSTED_HTTP2=h2c`. `WORKFLOW_SELF_HOSTED_HTTP2=off` forces HTTP/1.1.

OpenCode is no longer needed. To return to the OpenCode CLI for a run, set `WORKFLOW_SELF_HOSTED_TRANSPORT=opencode`. Existing self-hosted credentials and model selections migrate automatically; the old `openai/` catalog prefix is removed during migration.

The default model limits are 65,536 context tokens and 8,192 output tokens. Match your server with `WORKFLOW_SELF_HOSTED_CONTEXT_TOKENS` and `WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS`. One tool-loop turn is capped at 32,768 output tokens (`WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS`); a stage that writes its whole delivery in one turn needs room for it, and a turn that reaches the cap fails as incomplete. Set `WORKFLOW_SELF_HOSTED_SECONDS` for the stage timeout (default 3,600 seconds), or `WORKFLOW_SELF_HOSTED_REQUEST_SECONDS` for a separate API timeout. `WORKFLOW_OPENCODE_CMD` selects an alternate CLI executable.

### Candidate racing (multiple concurrent requests)

Racing is **off by default**: each self-hosted stage runs one request. Self-hosted
stages now enforce their JSON schema at the server, so malformed answers are
rare enough that four concurrent copies of every stage are not worth their cost.
It remains available: Uncle can race several isolated candidates per stage
attempt and promote the first to pass validation, to absorb an occasional
malformed, stalled, or slow response from a local model. This applies only to `self-hosted`-runner stages; it never
adds concurrent requests for `claude`, `codex`, `kimi`, or `cline`.

`WORKFLOW_SELF_HOSTED_CANDIDATES` sets how many candidates race per stage
attempt (default 1, no racing); a per-stage override is available as
`WORKFLOW_SELF_HOSTED_CANDIDATES_<STAGE>`. Setting it to `1` restores the
default single-candidate behavior. To turn racing on, use a value above 1. These environment variables apply for
that invocation only; to persist a lower count across runs, set it in
`.uncle/config` instead, the same way as any other per-stage setting, in
this order of precedence: `<stage>.candidates 2` for one specific stage,
else `self-hosted.candidates 2` to apply it to every self-hosted stage,
else the default of 1. A stage without its own config row for runner and
model -- a lens like `adversarial-review-worker-requirements`, or
`preview-build`, which inherits whichever stage is first configured with a
model -- inherits its candidate count the same way, but a `.candidates` row
set directly on that stage's own name still wins over what it inherits: set
`preview-build.candidates 2` to change only preview builds even if the
stage they inherit their model from stays at 1. The environment variables
still win over any config setting.

Your model server must be able to serve that many concurrent requests. A
server sized for one request at a time will see the extra concurrency as
contention -- slower responses, or a request timing out -- which surfaces
as an ordinary per-candidate failure (the stage still succeeds as long as
at least one candidate finishes and validates; it fails, with per-candidate
diagnostics, only if all of them do not). If your stages routinely need
more than one retry under racing, lower `WORKFLOW_SELF_HOSTED_CANDIDATES`
or increase your server's concurrent-request capacity.

## Repairing failing verification

After implementation the driver runs the plan's verification commands itself (for example `npx playwright test`). Automatic repair is off by default (`WORKFLOW_AUTO_REPAIR_ATTEMPTS=0`): a failing command, or a failing test-review row, is carried to the final audit as unresolved evidence and the run keeps going (`WORKFLOW_CONTINUE_ON_TEST_FAILURE`, on by default; with it off, the run stops and asks the owner). Set `WORKFLOW_AUTO_REPAIR_ATTEMPTS` to a number to send failures to a repair stage that many times first (never more than `WORKFLOW_MAX_REPAIRS`, default 4).

## GitHub access

For GitHub issue workflows, authenticate and check access:

```sh
gh auth login
gh auth status
```

Your account needs read access to the source issue and permission to close it if the workflow will do so. Local requirements and change-request workflows do not need a GitHub login.

## Project setup

Run `uncle` from a writable project directory. Start with `REQUIREMENTS.md`, `CHANGE_REQUEST.md`, or a GitHub issue. A Git repository is optional: you do not need to run `git init`. Self-hosted runs from the project directory without requiring a repository.

Without a repository, review the project files directly; Uncle cannot produce Git change diffs. In a repository, keep unrelated work committed or stashed so review diffs are clear. The Git command-line tool remains an installer dependency.

Install the project's own prerequisites: language runtimes, compilers, test frameworks, browsers, databases, or external services. These depend on the project and are not bundled with Uncle. Human checks need a person with the required access; independent review needs an identified reviewer.

Preflight checks these capabilities. A skipped prerequisite is a recorded waiver, not evidence that the capability works.

## Quick check

In the environment where you will run Uncle:

```sh
uncle --help
bash --version
python3 --version
git --version
jq --version
curl --version
gh --version
```

On native Windows, use `python --version` if `python3` is unavailable. Also check your selected AI client's `--help` and authentication before starting a workflow.

[Install and use Uncle](README.md) · [Workflow reference](scripts/README.md) · [Packaging](packaging/README.md)
