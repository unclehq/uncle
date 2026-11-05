# Change spec: issue 165 bare `--noui` interactive session

Omitted sections: Performance (none stated); Migration (no persisted format change); Prototype isolation (not a prototype)

## 1. Change type
Feature (modifies #160 behavior row N-6).

## 2. Problem statement
No way to converse with Uncle and start builds without curses. Bare `--noui` is refused.

## 3. Current behavior
B-2 in the baseline: exit 2 with an error.

## 4. Desired behavior
Bare `--noui` (or `UNCLE_NOUI=1`) starts a line-based REPL: banner (project, build mode, how to quit), prompt `uncle> `, plain-text replies, validated home actions that start builds with `--noui`-style progress, slash commands, clean quit paths.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | MODIFY | `uncle --noui` bare / `UNCLE_NOUI=1 uncle` | Refused, exit 2 | Banner + `uncle> ` prompt; EOF with no input exits 0 | launcher + pipe tests |
| SB-2 | ADD | Free-form line | n/a | Reply printed as plain text; prompt returns | pipe test, fake runner |
| SB-3 | ADD | Runner unavailable/error | n/a | One-line error; session survives | pipe test |
| SB-4 | ADD | `build issue N` (ISSUE_REQUEST_RE) | TUI only | Validated `github_issue` start; progress prints; prompt returns; failure reason printed | session + equivalence test |
| SB-5 | ADD | NL create-app request | TUI only | Brief drafted via validated `create_app`, build starts | session test with fake runner |
| SB-6 | ADD | Line typed while build runs | n/a | Held until prompt returns or consumed as the gate answer; never dropped | session + gate test |
| SB-7 | ADD | `/quit`, `/exit`, EOF | n/a | Running build stopped first (confirm if attended tty); no child left | pty + process test |
| SB-8 | ADD | Ctrl-C at idle prompt | n/a | Cancels line; second consecutive Ctrl-C quits | pty test |
| SB-9 | ADD | Ctrl-C during build | n/a | Build stopped, resumable state, prompt returns; not marked complete | pty test |
| SB-10 | ADD | Piped stdin | n/a | Lines run in order; exit code = last build result, refusal -> 2, else 0 | pipe test |
| SB-11 | PRESERVE | `--noui --noinput` | exit 2 | Unchanged | launcher test |
| SB-12 | PRESERVE | One-shot `--application/--issue/--change-request` | One run, exit | Unchanged | existing tests |
| SB-13 | ADD | Output not a tty | n/a | Plain lines, no escapes, no prompt decoration | pipe test |
| SB-14 | ADD | Slash commands `/help /quit /exit /stop /resume /clear /issue N /run /runstage /triage /do /mode`, `/settings` | TUI only | Plain-text equivalents; invalid usage prints usage; `/settings` prints values read-only | session tests |
| SB-15 | ADD | Banner / `/mode` / `--attended` | n/a | Banner shows mode started builds use; `/mode attended|unattended` changes it for later builds | session test |
| SB-16 | ADD | Existing brief + create request | TUI proposes replacement | Replacement asked on the same input; yes archives previous file; EOF/no declines | session test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | NEW | Session never imports/starts curses; no cursor-control/alt-screen bytes | REPL | module imports; EscapeFilter on output | import test + pty byte scan |
| I-2 | NEW | Every action goes through `home_actions.parse_reply` validation and the shared executor; model never starts a driver | REPL | single executor function | unit test + defect injection |
| I-3 | NEW | Same artifacts/state/attestation as TUI/one-shot for the same fixture | builds from REPL | shared `prepare_driver` + `uncle_headless.run` | equivalence test |
| I-4 | NEW | No child left running at session exit or SIGTERM | REPL | `run()` killpg + session signal handler | process test |
| I-5 | NEW | Gate answered in session recorded human; delegated stays delegated | gates | `UNCLE_ATTENDED_STDIN` path unchanged | gate test |
| I-6 | NEW | One conversation history; not replayed into driver prompts | REPL | history lives in chat adapter only | unit test |
| EI-1..EI-5 | EXISTING | Per baseline section 5 | unchanged paths | unchanged | existing suites |

No RELAXED or REMOVED invariants.

## 7. Compatibility
One-shot exit codes, flags, env, and TUI behavior unchanged. Launcher test rows asserting bare-noui refusal are replaced (authorized by the request, #160 N-6).

## 8. Error and failure behavior
Runner failure, refused action, issue not found: print reason, keep session. Attended with non-tty stdin: build refused with the existing message, session continues, final exit 2. Over-long lines are bounded (1 MiB) and rejected with a message. Blank lines ignored.

## 10. Security
Model output only reaches execution through the validated allowlist; text printed is escape-filtered; attachments and project root rules as in TUI; no new permission-bypass flags.

## 12. Rollback
Revert the launcher branch to re-enable the refusal; new modules are inert otherwise.

## 14. Non-goals
TUI replacement, panes/mouse, #164 capabilities, JSON protocol, `/set` editing, `--housekeeping`.

## 15. Assumptions
`/date` omitted (does not exist). `/settings` prints values read-only.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Bare `uncle --noui` and `UNCLE_NOUI=1 uncle` start the REPL (banner, `uncle> `), exit 0 on EOF; `--noui --noinput` still exits 2; one-shot forms unchanged. | Updated launcher-noui-test.sh plus new launcher REPL rows; existing headless tests pass. |
| AC-2 | A free-form line yields a plain-text reply and the prompt returns; runner failure prints one line and the session survives. | Pipe session test with fake runner. |
| AC-3 | `build issue N` and NL create-app requests start builds only through the validated action executor; a defect-injected REPL that runs a driver directly fails the I-2 test. | Session test and defect-injection run recorded in test report. |
| AC-4 | Piped scripts run lines in order, handle blank lines, EOF and very long lines, and exit with the last build result (refusal 2, else 0); output has no escape sequences. | Pipe tests with exact stdout and exit codes. |
| AC-5 | On a pty: Ctrl-C at idle cancels the line and a second quits; Ctrl-C during a build stops it (interrupted state) and returns to the prompt; no cursor-control/alt-screen bytes appear. | pty test. |
| AC-6 | An attended gate during a session build is answered from the same input and recorded as human; chat input is held until the gate resolves. | pty gate test with fake driver. |
| AC-7 | After `/quit`, EOF, and SIGTERM no child process remains; /quit during a build stops it first. | Process-inventory test. |
| AC-8 | The same fixture build from TUI, REPL, and one-shot yields the same artifacts and attestation fields; the REPL never imports curses. | Extended headless-equivalence test and import test. |
| AC-9 | Slash commands /help /quit /exit /stop /resume /clear /issue /run /runstage /triage /do /mode /settings behave as plain text with usage on invalid input; banner shows the build mode and /mode changes it. | Session tests. |
| AC-10 | Existing shell and Python suites show no new regressions versus the baseline. | bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh. |

