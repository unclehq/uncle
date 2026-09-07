# Contributing to Stagegate

Thanks for taking the time to contribute. This project is small and
opinionated, so the best way to start is to open an issue and describe what you
want to change before writing a lot of code.

## Quick links

- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — community standards
- [`QUICK_START.md`](QUICK_START.md) — run the workflows end-to-end

## Getting started

1. Fork the repository and clone your fork.
2. Make sure you can run the basic syntax check:

   ```sh
   for f in scripts/*.sh; do bash -n "$f"; done
   ```

3. Pick an open issue, or open a new one to discuss your idea.

## Development setup

This project is mostly shell scripts and Markdown. You need:

- `bash` 3.2 or later (macOS system bash is fine)
- `jq` for parsing Claude streaming JSON events
- `claude` and `codex` CLIs, or compatible alternatives configured via
  `WORKFLOW_AGENT_CMD` and `WORKFLOW_REVIEWER_CMD`

No build step is required.

## What to contribute

Good contributions include:

- Bug fixes in the drivers or prompts
- Documentation improvements
- New examples in `examples/`
- Shell completions, issue templates, or CI workflows
- Smaller quality-of-life improvements to the CLI

Avoid:

- Large refactors that change the gate model without prior discussion
- Adding new dependencies
- Cosmetic-only changes not bundled with substantive work

## Coding conventions

- Keep scripts compatible with bash 3.2 (the macOS system bash).
- Use `set -euo pipefail` in new scripts.
- Quote variables that may contain spaces.
- Prefer `printf '%s\n' "$var"` over `echo "$var"` when the value is untrusted.
- Run `bash -n` on every changed script before submitting.
- Keep line lengths reasonable (aim for 88 characters in Markdown, matching the
  Python-style default used elsewhere).

## Testing

Syntax-check every script, then run the suites in `scripts/tests/`:

```sh
for f in scripts/*.sh scripts/lib/*.sh scripts/tests/*.sh; do bash -n "$f"; done
for t in scripts/tests/*-test.sh; do bash "$t" || exit 1; done
```

Every suite is hermetic: no network, no model calls, and no writes outside its
own `mktemp -d`. The ones that exercise a driver run it in a scratch git
repository against stub agent and reviewer CLIs.

If you add a script, include it in the syntax check. If you add behavior to a
driver, add a case to the suite that covers that driver.

## Submitting changes

1. **Open an issue first** for non-trivial changes.
2. Create a feature branch.
3. Make focused commits with clear messages.
4. Ensure `bash -n` passes for all scripts.
5. Update relevant documentation (`README.md`, `QUICK_START.md`, etc.).
6. Open a pull request and reference the issue it closes.

## Commit messages

Use the imperative mood and keep the subject line under 72 characters:

```text
Add --dry-run flag to from-issue.sh
```

If the change is large enough to need context, add a body explaining *why* the
change is needed and *what* it does.

## Getting help

Open a GitHub issue or discussion. For private concerns, email
<me@brian.biz>.
