# GitHub integration

Uncle can turn a GitHub issue into a change request, run the change workflow, and publish the audited result as a pull request with your approval.

## Setup

Install Git and the GitHub CLI (`gh`), then authenticate:

```sh
gh auth login
```

Run `uncle` from the project checkout. PR creation requires a Git repository, a supported GitHub remote, and permission to push and create PRs. Uncle supports a GitHub head remote, optionally with an upstream base remote and a direct fork owned by your account.

See [Prerequisites](PREREQUISITES.md) for the remaining tools and model setup.

## Start from an issue

1. Choose **From GitHub issue** in Uncle's home menu.
2. Enter the issue URL or number. A URL identifies the repository explicitly.
3. Select **change request** for an existing project or **new application** for a new build.
4. Review the generated input and follow the start confirmation.

Uncle reads the issue title and body into `CHANGE_REQUEST.md` or `REQUIREMENTS.md`. Change requests then enter the planning, implementation, verification, and audit workflow. Issue import does not clone the repository; it uses the project directory where you launched Uncle.

An authenticated `gh` fetch supports private issues. Public issues can fall back to `curl`, but that read-only import does not authorize automatic issue closure. Uncle records the originating issue and refuses to replace an unfinished workflow with a different issue.

## Publish a change as a PR

The PR handoff applies to the **change workflow** in a Git checkout, including changes started from a local `CHANGE_REQUEST.md`. Importing an issue as a new application does not use this change-workflow PR handoff.

After the final audit returns `READY` or `READY_WITH_NON_BLOCKING_ISSUES`, Uncle:

1. Shows the audited diff and target repository and branch.
2. Asks for a PR title, work summary, and manual verification steps. The default title comes from the change request's Summary.
3. Asks you to approve committing, pushing, and creating the PR.
4. Commits the audited files plus the audit, pushes without force, and creates the PR.

When starting on the default branch, Uncle creates a feature branch. The PR targets the base repository's default branch. Runs without an originating issue ask you to confirm the base repository.

For an eligible issue imported through `gh`, the PR body includes `Closes owner/repo#number`. Creating the PR leaves the issue open; GitHub closes it when the PR merges into the default branch. Uncle does not automatically merge the PR.

Auto/unattended mode and `WORKFLOW_CLOSE_ISSUE=0` disable the PR handoff. A successful agent stage alone does not authorize publication.

## Sign a commit in another terminal

If commit signing fails during PR handoff, Uncle opens a dialog showing the prepared commit message and a command such as:

```sh
git commit -S -m 'Fix the reported issue'
```

In another terminal, open the same project, review and stage the audited changes, and run the command shown. Complete any signing prompt, then return to Uncle and press **OK / Enter**.

Uncle checks the signature, parent commit, and audited contents before resuming. A different or unsigned commit remains blocked. This dialog handles publication signing failures; GPG errors inside test suites remain test findings.

## Resume or recover

If you decline, close a prompt, or encounter an authentication or publication error, the handoff remains pending. Restart Uncle in the same project to resume. A workflow at `COMPLETE` can still have an unfinished PR handoff.

Uncle records progress in `.uncle/workflow/pr/journal.json`. It checks for an existing PR after an uncertain creation result. If the outcome cannot be established, resolve it before retrying publication. Keep the journal so Uncle can avoid duplicate PRs.

Changes to audited files, the audit, branches, or remote state can require another final audit. Resume only after addressing the reported mismatch.

Without a Git repository, Uncle cannot publish a PR. The issue-backed change workflow instead retains its direct-close path, subject to a matching READY audit and authenticated issue ownership.
