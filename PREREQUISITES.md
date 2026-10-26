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
| OpenCode / self hosted | `opencode` | Configure an OpenAI-compatible model endpoint in Uncle, as described below. |

Before starting a workflow, confirm each selected client can run from your terminal and access its model. Hosted providers may require a subscription or funded API account. Uncle does not provide model access.

### Self hosted

You need a running model server, enough server resources for the chosen model, and network access from Uncle to that server. Uncle talks to the server directly over its OpenAI-compatible HTTP API; it does not host the model.

In **Configure → Configure self hosting**, enter:

- **Base URL:** the OpenAI-compatible API root, such as `http://localhost:8000/v1`.
- **API key:** the endpoint's credential. For an unauthenticated server, use a placeholder such as `local`.

The endpoint must support authenticated `GET <Base URL>/models` discovery and chat completions. Select a model for each stage, or apply one to all stages.

The server must support the requested context size and return responses within the configured timeouts. Successful model discovery alone does not prove that inference works.

The model must support tool calls for implementation and file inspection. Uncle runs its own tool loop (read, search, write, edit and shell tools confined to the project) with a fresh conversation per stage, at temperature 0. The requirements stage (`requirements` and `requirements-investigate`) is the exception and runs at temperature 1. Change either with `<stage>.temperature` (or `self-hosted.temperature` for all stages) in `.uncle/config`, or with `WORKFLOW_SELF_HOSTED_TEMPERATURE_<STAGE>` / `WORKFLOW_SELF_HOSTED_TEMPERATURE` in the environment (0 to 2; environment wins over config, a stage's own setting wins over the global one, and workers inherit from their stage).

**Schema enforcement.** When a stage owes a known JSON artifact, its final answer is a request that carries the artifact's JSON schema. Uncle asks the server to enforce it in the strongest form it accepts, and falls back cleanly when a server rejects one: Ollama's native `format`, then OpenAI-style `response_format` (JSON schema), vLLM's `structured_outputs` and `guided_json`, then plain JSON-object mode, then prompt-only. Every answer is also checked against the schema locally, and a workflow document the model writes itself is refused at the write if it does not match. Stages whose answer is prose, such as chat, have no schema and are not constrained.

**Connections.** Uncle keeps one persistent connection per server and reuses it for every request in a stage, reconnecting once if the server closed it while idle. HTTP/2 is used when it can be negotiated: over `https` (via ALPN) when the optional `httpx` and `h2` Python packages are installed. Plain `http` servers speak HTTP/1.1 keep-alive. Most local servers do not accept HTTP/2 without TLS; if yours does (for example Hypercorn), set `WORKFLOW_SELF_HOSTED_HTTP2=h2c`. `WORKFLOW_SELF_HOSTED_HTTP2=off` forces HTTP/1.1.

OpenCode is no longer needed. To return to the OpenCode CLI for a run, set `WORKFLOW_SELF_HOSTED_TRANSPORT=opencode`. Existing self-hosted credentials and model selections migrate automatically; the old `openai/` catalog prefix is removed during migration.

The default model limits are 65,536 context tokens and 8,192 output tokens. Match your server with `WORKFLOW_SELF_HOSTED_CONTEXT_TOKENS` and `WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS`. Set `WORKFLOW_SELF_HOSTED_SECONDS` for the stage timeout (default 3,600 seconds), or `WORKFLOW_SELF_HOSTED_REQUEST_SECONDS` for a separate API timeout. `WORKFLOW_OPENCODE_CMD` selects an alternate CLI executable.

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

Run `uncle` from a writable project directory. Start with `REQUIREMENTS.md`, `CHANGE_REQUEST.md`, or a GitHub issue. A Git repository is optional: you do not need to run `git init`. OpenCode runs from the project directory without requiring a repository.

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
