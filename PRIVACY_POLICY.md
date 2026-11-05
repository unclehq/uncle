# Privacy Policy

**Uncle shares nothing.** The Uncle project does not collect, store, sell, rent, or share your data, your code, or any information about you or how you use Uncle. There is no Uncle server that receives anything from your machine.

## What Uncle does not do

- No telemetry, analytics, usage tracking, crash reporting, or advertising identifiers.
- No accounts, sign-up, or Uncle-operated backend.
- No sharing of your data with any third party by Uncle itself.
- No copying of your code, requirements, plans, logs, or credentials anywhere except your own machine.

## Where your data lives

Everything Uncle produces stays on your computer, in your project and its `.uncle/` directory: run state, logs, cost and token records, approvals, and the documents it writes. API keys you configure are kept in your local `.uncle/config` and are never sent anywhere by Uncle.

## Tools you choose to connect

Uncle runs other programs on your behalf, and those programs have their own data practices. Uncle does not control them, and this policy does not cover them:

- **Model runners** you configure (Claude, Codex, Kimi, or a self-hosted endpoint). They receive the prompts and file contents needed for the work you start, and handle them under their own terms and privacy policies.
- **GitHub**, through `git` and the `gh` CLI, when you ask Uncle to read an issue, push a branch, or open a pull request.
- **An update check**, which asks GitHub's public release API for the latest Uncle version. It sends no information about you or your project, and it is skipped when unattended.

If you need nothing to leave your machine, configure a local, self-hosted runner and do not use the GitHub features.

## Changes

If this policy ever changes, the change will appear in this file's history in the repository.

## Contact

Questions: open an issue at https://github.com/unclehq/uncle/issues.
