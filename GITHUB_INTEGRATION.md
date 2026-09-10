# GitHub integration

Uncle imports GitHub issues and can publish audited changes as pull requests.

## Setup

Install Git and the GitHub CLI, then run `gh auth login`. Launch `uncle` in your project checkout. PRs require a supported GitHub remote and permission to push and create PRs.

See [Prerequisites](PREREQUISITES.md) for other requirements.

## Import an issue

Choose **From GitHub issue**, enter its URL or number, and select **change request** or **new application**. Uncle creates `CHANGE_REQUEST.md` or `REQUIREMENTS.md` from the issue title and body.

Import uses your current project; it does not clone a repository. Public issues can use a read-only `curl` fallback, which does not authorize automatic issue closure.

## Create a PR

The change workflow offers PR publication after a READY audit. This also works with a local `CHANGE_REQUEST.md`.

1. Review the audited diff and target.
2. Enter a title, summary, and manual verification steps.
3. Approve the commit, push, and PR creation.

Uncle creates a feature branch when needed and pushes without force. Eligible imported issues are linked with `Closes owner/repo#number`; GitHub closes them on merge into the default branch. Uncle does not merge PRs.

Auto/unattended mode and `WORKFLOW_CLOSE_ISSUE=0` disable this handoff. New-application workflows do not use it.

## Signing and recovery

If signing fails, a dialog shows the commit command and message. Stage the audited changes and run that `git commit -S -m '…'` command in another terminal. Return and press **OK / Enter**. Uncle verifies the signature and contents before continuing.

Restart Uncle in the same project to resume a pending handoff. Keep `.uncle/workflow/pr/journal.json`; it records progress and helps prevent duplicate PRs. Changes to audited files or repository state may require another audit.

Without Git, Uncle cannot create a PR. An eligible issue-backed change can instead close its issue directly after a matching READY audit.
