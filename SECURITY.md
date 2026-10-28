# Security Policy

## Supported versions

Uncle is pre-1.0 and under active development. Security fixes are made
against the `main` branch; there are no maintained release branches yet.

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue.

- Preferred: [GitHub Security Advisories](https://github.com/unclehq/uncle/security/advisories/new)
  for this repository.
- Alternative: email brian@oayecreative.com with a description of the issue,
  steps to reproduce, and any relevant logs or proof-of-concept.

Please do not file a public GitHub issue for suspected vulnerabilities until
a fix has been released.

You should expect an initial response within 5 business days. We will work
with you to confirm the issue, develop a fix, and coordinate disclosure
timing.

## Scope

Uncle drives AI agent CLIs (Claude, Codex, and compatible tools) that are
given Bash, file-write, and network access against your repository. Relevant
report categories include, but are not limited to:

- Prompt-injection or workflow-manipulation paths that let agent-generated or
  reviewer-generated content bypass a human approval gate (see
  `CLAUDE.md`'s gate rules) or cause unsafe commands to run without the
  configured permission mode.
- Ways that a malicious repository, requirements document, or review
  artifact could cause Uncle's driver scripts to execute attacker-controlled
  code, exfiltrate data, or escape the working directory.
- Credential or secret handling issues in `scripts/lib/` or installer
  scripts (`install.sh`, `install.ps1`).
- Supply-chain issues with the installers or release artifacts themselves.

Out of scope: vulnerabilities in the underlying agent CLIs (Claude Code,
Codex CLI, etc.) themselves — please report those to their respective
maintainers. General bugs that don't have a security impact belong in the
normal issue tracker.

## Our commitment

Uncle's entire design is built around not trusting AI-generated output by
default — human approval gates, adversarial review, and verification
re-execution exist specifically because agent output can be wrong or
adversarially steered. We take reports that find gaps in those gates
seriously and will credit reporters (with permission) in release notes once
a fix ships.
