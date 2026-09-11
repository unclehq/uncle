# GitHub integration

Uncle imports GitHub issues and can publish audited changes as pull requests.

## Setup

Install Git and the GitHub CLI, then run `gh auth login`. Launch `uncle` in your project checkout. PRs require a supported GitHub remote and permission to push and create PRs.

See [Prerequisites](PREREQUISITES.md) for other requirements.

## Import an issue

Choose **From GitHub issue**, enter its URL or number, and select **change request** or **new application**. Uncle creates `CHANGE_REQUEST.md` or `REQUIREMENTS.md` from the issue title and body.

Import uses your current project; it does not clone a repository. Public issues can use a read-only `curl` fallback.

## Create a PR

The change workflow offers PR publication after a READY audit. This also works with a local `CHANGE_REQUEST.md`.

1. Review the audited diff and target.
2. Enter a title, summary, and manual verification steps.
3. Approve the commit, push, and PR creation.

Uncle creates a feature branch when needed and pushes without force. Eligible imported issues are linked with `Closes owner/repo#number`; GitHub closes them on merge into the default branch. Uncle does not merge PRs.

Auto/unattended mode and `WORKFLOW_CLOSE_ISSUE=0` disable a new handoff. A previously approved signing handoff can resume despite these settings after validation. New-application workflows do not use it.

## Signing and recovery

When Git commit signing is enabled, Uncle shows one command block that stages all changes, removes `.uncle/workflow` from the index, includes `FINAL_AUDIT.md` even when ignored, and runs `git commit -S` with the approved title. Review the changes, press **c — Copy command**, and run the block in another terminal in the same project. Copying does not execute it. Return and press **Enter** to validate and resume, or **Esc** to cancel and leave the handoff pending. Uncle verifies the signature, audited tree, and sole parent before publication.

Copy requires `pbcopy` on macOS, `wl-copy` on Wayland, or `xclip` (preferred) / `xsel` on X11. A missing or failing helper leaves the dialog open with an error; terminal selection remains available. The CLI prints the same shell-ready block. Arrow keys scroll long signing instructions in the TUI.

Restart Uncle in the same project to resume a pending handoff. Keep `.uncle/workflow/pr/journal.json`; it records progress and helps prevent duplicate PRs. Changes to audited files or repository state may require another audit.

Without Git, Uncle cannot create a PR. The issue remains open; Uncle never closes issues directly.
