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

## Opening the preview in a browser

`--noui` opens the same browser tabs the interactive screen does, for a new
application build (never for a change request, and not for a desktop app such as
Electron or Tauri, which are launched rather than browsed):

* The preview build runs as a driver stage and opens its own first tab, as in
  the interactive screen.
* **Early page.** If a previewable page appears during requirements, planning,
  review, preflight, implementation or repair and the driver is not already
  serving one (for example the preview build was skipped), `--noui` serves it
  and opens a tab. A server the driver already owns is never duplicated.
* **Finished app.** When the build completes, the driver has stopped its own
  preview server, so `--noui` serves the finished project and opens it. That
  server outlives the command, so it expires: `UNCLE_NOUI_PREVIEW_SECONDS`
  (default 3600) sets its lifetime, and the `Preview:` line gives the pid to
  `kill` sooner. A React or Svelte project is handed to its dev server once
  dependencies exist, and the page reloads itself.

Turn this off with `UNCLE_NOUI_PREVIEW=0` (or the driver's own
`WORKFLOW_PREVIEW_OPEN_BROWSER=0`). On a machine with no browser the server still
starts and `.uncle/workflow/logs/preview-server.log` says the tab could not be
opened.

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

