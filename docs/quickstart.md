# Quickstart: build something in one sentence

The fastest way to see what Uncle does is to point it at a one-line
application brief and watch it work.

## macOS / Linux / WSL

```sh
curl -fsSL https://raw.githubusercontent.com/unclehq/uncle/main/install.sh -o install.sh && bash install.sh
uncle --application 'build a groovy calculator react webapp with keyboard support'
```

## Windows (PowerShell)

```powershell
Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/unclehq/uncle/main/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
uncle --application 'build a groovy calculator react webapp with keyboard support'
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

## Running it unattended

Add `--unattended` to skip every approval gate and let the whole build run
start to finish without you:

```sh
uncle --application 'build a groovy calculator react webapp with keyboard support' --unattended
```

This is the fastest way to get straight to a finished result, but it also
means skipping the human approval gates that are the actual point of Uncle.
Run the interactive version at least once first so you know what you're
opting out of.

## Next steps

- [Prerequisites](../PREREQUISITES.md) — required tools, AI clients,
  authentication, and self-hosted model setup.
- [GitHub integration](../GITHUB_INTEGRATION.md) — start from a GitHub issue
  and carry a change through to a pull request.
- [Workflow documentation](../docs/) — the full supervision, triage,
  recovery, and configuration model.
