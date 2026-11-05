# Implementation notes

### Files changed

- `uncle` — Bare --noui / UNCLE_NOUI=1 execs scripts/lib/uncle_repl.py instead of refusing; usage text updated; launcher; SB-1, SB-11
- `scripts/lib/uncle_repl.py` — Line REPL: banner, bounded fd line reader, slash commands, Ctrl-C policy, escape-filtered output, exit-code policy; builds only via repl_actions.execute; REPL loop; SB-1..SB-16, I-1, I-4
- `scripts/lib/repl_actions.py` — Single validated executor: re-validates every action with home_actions.parse_reply, maps to allowlisted startup actions, calls uncle_headless.prepare_driver/run (signals installed so SIGINT/SIGTERM kill the build group); executor; I-2, I-3, I-4
- `scripts/lib/repl_chat.py` — Synchronous chat adapter (ChatSession.ask -> reply + validated action); runner in own process group; UNCLE_REPL_RUNNER override for tests; chat adapter; SB-2, SB-3, I-6
- `scripts/lib/home_actions.py` — ISSUE_REQUEST_RE moved here so the REPL and TUI share it; shared pieces; SB-4
- `uncle_tui.py` — Imports ISSUE_REQUEST_RE from home_actions (definition removed); no behavior change; shared pieces; I-3
- `scripts/lib/uncle_headless.py` — Extracted prepare_driver(root, err, env=None); _stream now ends when the driver's stdout hit EOF and the driver exited even if attended stdin is still open (previously waited for a keystroke); shared pieces; I-3, I-5
- `scripts/tests/repl-session-test.py` — Pipe session tests with fake runner/drivers; SIGTERM process test; import test; I-2 defect injection; tests; AC-2,3,4,7,9, I-1, I-2, I-4, I-6
- `scripts/tests/repl-pty-test.py` — pty tests: idle Ctrl-C, Ctrl-C during build, attended gate answered in session, escape byte scan; tests; AC-5, AC-6, I-1, I-5
- `scripts/tests/headless-equivalence-test.py` — Adds a REPL run of the same fake driver and compares artifacts with the one-shot run; tests; AC-8, I-3
- `scripts/tests/launcher-noui-test.sh` — Bare-refusal rows replaced by REPL rows; real launcher REPL rows; error-line-only comparison for unrecognized args; tests; AC-1

### Deviations

- `scripts/lib/uncle_headless.py`: Besides the planned prepare_driver extraction, _stream's loop-exit condition was changed (EOF plus driver exited) because an attended session build otherwise hung after the driver finished until another key was typed; found by repl-pty-test.py.

### Unresolved concerns

- No live claude run was performed; chat is exercised only with a fake runner emitting stream-json. The real permission_denials fixture from the plan was not recorded.
- Planned defect-injection runs for I-3 and I-5 were not executed; only I-2 (validation removed) is injected inside repl-session-test.py.
- /triage and /do print a TUI-only notice; /resume and /clear report TUI-only; /stop reports no build running (builds are synchronous so a stop is Ctrl-C).
- scripts/tests/no-housekeeping-test.py fails on prompts/home-agent.md, a file this change does not touch (treated as pre-existing).
- readline is imported on a tty for line editing; the pty byte scan showed no alt-screen or cursor-addressing escapes.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | uncle launcher branch execs scripts/lib/uncle_repl.py; launcher-noui-test.sh updated | bash scripts/tests/launcher-noui-test.sh: 36 ok, 0 FAIL (real bare --noui and UNCLE_NOUI=1 exit 0 with banner; --noui --noinput exits 2) |
| AC-2 | IMPLEMENTED | scripts/lib/uncle_repl.py, repl_chat.py: reply printed, runner failure one line, session survives | python3 scripts/tests/repl-session-test.py exit 0 (free-form reply, runner failure rows pass) |
| AC-3 | IMPLEMENTED | scripts/lib/repl_actions.py single executor with parse_reply validation | repl-session-test.py: issue and create_app builds run only through executor; smuggled field and unsupported action refused with no driver; validation-removed injection detected |
| AC-4 | IMPLEMENTED | uncle_repl.py LineReader (1 MiB bound), Out (EscapeFilter), exit-code policy | repl-session-test.py: blank lines, long line rejected, order kept, attended piped refusal exit 2, no escapes; exit 0 |
| AC-5 | IMPLEMENTED | uncle_repl.py Ctrl-C handling; repl_actions installs run() signal handling | python3 scripts/tests/repl-pty-test.py exit 0 (idle Ctrl-C cancel then quit, Ctrl-C during build returns to prompt with exit 130 and no child, no cursor/alt-screen bytes) |
| AC-6 | IMPLEMENTED | uncle_repl.py passes stdin fd to run(); uncle_headless._stream exit fix | repl-pty-test.py: gate answer typed in the session reached the driver, UNCLE_ATTENDED_STDIN=1, session exits 0 |
| AC-7 | IMPLEMENTED | repl_actions.py install_signals=True; uncle_repl.py SIGTERM handler | repl-session-test.py: SIGTERM mid-build exits 143 with no surviving child; pty test: no child after Ctrl-C |
| AC-8 | IMPLEMENTED | headless-equivalence-test.py REPL run; prepare_driver shared | python3 scripts/tests/headless-equivalence-test.py exit 0 with no FAIL lines (REPL artifacts equal one-shot; no curses import) |
| AC-9 | IMPLEMENTED | uncle_repl.py slash(): /help /quit /exit /stop /resume /clear /issue /triage /do /mode /settings | repl-session-test.py: help, usage errors, settings, quit stops reading, unknown command exit 2, /mode attended pass |
| AC-10 | IMPLEMENTED | No change to existing behavior beyond the planned scope | Targeted: headless-run-test.py exit 0, launcher-noui-test.sh green; no-housekeeping-test.py fails on prompts/home-agent.md (untouched file). Full suites left to the driver. |
