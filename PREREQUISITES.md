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
| Aider / self hosted | `aider` | Configure an OpenAI-compatible model endpoint in Uncle, as described below. |

Before starting a workflow, confirm each selected client can run from your terminal and access its model. Hosted providers may require a subscription or funded API account. Uncle does not provide model access.

### Aider / self hosted

You need a running model server, enough server resources for the chosen model, and network access from Uncle to that server. Aider is the client; it does not host the model.

In **Configure → Configure Aider / self hosting**, enter:

- **Base URL:** the OpenAI-compatible API root, such as `http://localhost:8000/v1`.
- **API key:** the endpoint's credential. For an unauthenticated server, use a placeholder such as `local`.

The endpoint must support authenticated `GET <Base URL>/models` discovery and chat completions. Uncle lists discovered models with the `openai/` prefix. Select one for each Aider stage, or apply it to all stages.

The server must support the requested context size and return responses within the configured timeouts. Successful model discovery alone does not prove that inference works. Aider 0.86.2 has been integration-tested with Uncle.

## GitHub access

For GitHub issue workflows, authenticate and check access:

```sh
gh auth login
gh auth status
```

Your account needs read access to the source issue and permission to close it if the workflow will do so. Local requirements and change-request workflows do not need a GitHub login.

## Project setup

Run `uncle` from a writable project directory. Start with `REQUIREMENTS.md`, `CHANGE_REQUEST.md`, or a GitHub issue. A Git repository is optional: you do not need to run `git init`. Uncle automatically disables Aider's Git integration outside a repository.

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
