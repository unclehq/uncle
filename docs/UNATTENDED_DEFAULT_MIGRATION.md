# Unattended is now the default

## What changed

`uncle --application`, `--issue`, `--change-request`, `--housekeeping`, the
TUI, and the drivers (`stagegate.sh`, `change-workflow.sh`, `from-issue.sh`,
`housekeeping-workflow.sh`) now run unattended unless told otherwise. The run
prints `Mode: unattended (use --attended to review each gate)`.

**Scripts that relied on the old default to pause at gates now run straight
through.** Add `--attended` (or `UNCLE_ATTENDED=1`) to keep human gates.

## New

- `--attended`: every gate waits for a person. Without a TTY it exits nonzero
  and starts nothing; it never falls back to unattended. Scripted answers are accepted on stdin
  automatically when no startup option (bare `--application`, bare `--issue`,
  `--change-request`) consumes it.
- `UNCLE_ATTENDED=1`: same as `--attended`.
- `--attended` together with `--unattended` is refused, naming both flags.
- If attended and unattended are requested through different sources (flag and
  env), attended wins.
- The mode is recorded in `.uncle/workflow/mode`; a resumed run reuses it
  unless a flag or env is given, and prints it on resume.
- The upgrade check never prompts when unattended: it prints one line naming
  the newer version and the upgrade command. It prompts only when attended
  with a TTY.
- The TUI starts unattended, shows the mode in its header, and Shift-Tab
  toggles it for the session; `--attended` starts the session attended.

## Deprecated (still accepted, with a one-line stderr notice)

`--unattended`, `UNCLE_UNATTENDED`, `WORKFLOW_UNATTENDED`,
`UNCLE_HOUSEKEEPING_UNATTENDED`. They are now no-ops. **They will be removed
no earlier than two releases after this one.** Drop them from your scripts.

## Unchanged

Unattended semantics are the same: delegated gates are ledgered and the
attestation and PR body still state that nobody reviewed them. Failing tests
still stop the run, issue runs still publish a PR and other runs do not
commit or push, and the housekeeping policy gate runs before any mode decision.

## Rollback

Revert the change. The only new persisted file is `.uncle/workflow/mode`,
which older versions ignore.
