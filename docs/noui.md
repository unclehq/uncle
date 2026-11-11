# Running without the TUI (`--noui`)

For ssh sessions without a pty, `docker run` without `-t`, and CI, pass
`--noui` (or set `UNCLE_NOUI=1`). Uncle runs the driver directly, streams its
output as plain text with a `[+HH:MM:SS]` elapsed prefix (no escape sequences),
prints the finished-build summary, and exits with a code you can script on:

| Exit | Meaning |
|---|---|
| 0 | The run completed (completion banner seen) |
| 1 | The driver failed (its own exit code is printed on stderr) |
| 2 | Refused before starting (nothing is written): no startup action or more than one, empty startup text, `--noinput` combined with `--noui`, `--attended` without `--noui`, `--attended` without a tty on stdin, or `--attended` combined with `--change-request` |
| 3 | Stopped at a human gate or a signing handoff (the gate is named on stderr), or EOF/blank input at an attended gate |
| 128+n | Stopped by SIGINT (130) or SIGTERM (143); the driver's process group is stopped too (SIGKILL after a 10 s grace; a second signal kills it immediately) |

Precedence when several apply: signal (130/143) > gate or signing stop (3) >
driver nonzero or failed check (1) > 0.

## Preview and App lines

During an `--application` build, `--noui` prints a `Preview:` line announcing
the preview URL as soon as one is available, and an `App:` line with the
finished application's location at the end. Both carry the `[+HH:MM:SS]`
elapsed prefix, contain no escape sequences, and are never written inside a
partially written driver line. They do not change the exit code.

Only the exact value `UNCLE_NOUI=1` enables `--noui`; any other value (unset,
empty, `0`, `true`) is ignored and the launcher behaves as before.

Without `--attended`, `--noui` never reads stdin and never answers a human gate:
it stops, records nothing as approved, names the gate on stderr and exits 3.
Output values of environment variables whose names contain `KEY`, `TOKEN`,
`SECRET` or `PASSWORD` are masked.

`--noui` never shows the menu, so give it a startup action such as
`--application`. `--attended` works only if stdin is a real terminal; there,
EOF or a blank answer at a gate means not approved (exit 3). Under
`--noui` the desktop launch is skipped and recorded in `desktop-launch.json`
(`decision=skipped`, `reason=noui`). `--noinput` is a different feature and is
unchanged. Uncle never signs commits on your behalf here: when a signature is
needed it prints the git command for you to run.

`--change-request` reads all of stdin (UTF-8, at most 1 MiB, no NUL or control characters), writes it unchanged (CRLF becomes LF) to `CHANGE_REQUEST.md`, and starts the change workflow. It refuses to overwrite an existing `CHANGE_REQUEST.md` and cannot be combined with `--application` or `--issue`. Treat piped text as untrusted input to tool-using agents, especially in the default unattended mode.

