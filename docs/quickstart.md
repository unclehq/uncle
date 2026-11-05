# Quickstart: build something in one sentence

The fastest way to see what Uncle does is to point it at a one-line
application brief and watch it work.

## macOS / Linux / WSL

```sh
curl -fsSL https://raw.githubusercontent.com/unclehq/uncle/main/install.sh -o install.sh && bash install.sh
uncle --application 'build a groovy 1970s themed calculator react webapp with a groovy 1970s theme background and keyboard support'
```

## Windows (PowerShell)

```powershell
Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/unclehq/uncle/main/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
uncle --application 'build a groovy 1970s themed calculator react webapp with a groovy 1970s theme background and keyboard support'
```

## What you'll see

`--application` turns a one-sentence brief into a `REQUIREMENTS.md` and
starts the new-application workflow: requirements interpretation, a project
plan, an independent adversarial review of that plan, your approval,
implementation, independent test review, a manual checklist, verification,
and a final audit — all visible in the terminal as it happens. You can ask
questions, redirect the current stage, or just watch; see
[Talk to Uncle while it works](../README.md#talk-to-uncle-while-it-works).

Every plan and revision stops for your explicit approval before anything is
implemented. That pause is the point: Uncle keeps a human in the loop at the
decisions that matter, rather than quietly shipping whatever the agent
produced.

## Passing the description on stdin

For a long description, pipe or redirect it instead of quoting it:

```sh
uncle --application < idea.md
```

A bare `--application` reads stdin; on an interactive terminal with nothing
piped it refuses (empty input). Text that begins with `--` must use the `=`
form: `uncle --application="--foo bar"`.

## Unattended by default, `--attended` to review

Runs are unattended by default: every approval gate is skipped and the whole
build runs start to finish without you.

```sh
uncle --application 'build a groovy 1970s themed calculator react webapp with a groovy 1970s theme background and keyboard support'
```

That is the fastest way to a finished result, but it skips the human approval
gates. Add `--attended` (or `UNCLE_ATTENDED=1`) to review each gate yourself;
it needs a terminal and refuses without one. Run attended at least once first
so you know what you're opting out of.

`--unattended` and the legacy `UNCLE_UNATTENDED` and
`WORKFLOW_UNATTENDED` variables are deprecated no-ops that print a
notice on stderr. See [UNATTENDED_DEFAULT_MIGRATION.md](UNATTENDED_DEFAULT_MIGRATION.md).

## Next steps

- [Prerequisites](../PREREQUISITES.md) — required tools, AI clients,
  authentication, and self-hosted model setup.
- [GitHub integration](../GITHUB_INTEGRATION.md) — start from a GitHub issue
  and carry a change through to a pull request.
- [Workflow documentation](../docs/) — the full supervision, triage,
  recovery, and configuration model.
