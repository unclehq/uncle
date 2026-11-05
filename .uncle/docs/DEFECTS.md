# Defects

## None

- **Status:** NOT RUN
- **Evidence:** grep of scripts/tests/repl-session-test.py lines 131-165 and scripts/tests/repl-pty-test.py lines 89-134. I did not execute these tests and did not read their results from the green-check.
- **Expected result:** Declining keeps the build running; confirming stops it first and exits; SIGTERM exits 143; no child processes remain.
- **Actual result:** Not performed live. A real build needs a real agent runner and an interactive PTY, and the worker contract forbids rerunning driver tests. The existing automated tests appear to cover parts of this row: repl-session-test.py asserts SIGTERM mid-build exits 143 and leaves no child, and repl-pty-test.py asserts /quit during a build exits 130. I did not find a decline-then-confirm /quit sequence in the grep output.

## None

- **Status:** NOT RUN
- **Evidence:** grep of scripts/tests/repl-session-test.py lines 100-120. Nothing was executed.
- **Expected result:** Junk declines replacement; yes archives the old brief under .uncle/brief-history and proceeds; /mode reflects the new mode for later builds.
- **Actual result:** Not performed live. The grep found /mode and /mode attended checks in repl-session-test.py. It found no 'maybe' answer and no brief-history assertion, so the brief-replacement confirmation path was not shown as covered.

## None. Setup needed: a real attended build run with the real driver (to inspect the gate attestation record) and a model runner that emits gate-like text (to confirm it cannot answer a gate).

- **Status:** BLOCKED-SETUP
- **Evidence:** Temporary scripts /tmp/mc203/t.py and /tmp/mc203/u.py. Transcript A: 'Human gate: approve? [y/N]' then 'got:[yes]' then 'Workflow complete.'. Transcript B: '^D' then 'EOF at gate: declined' then 'uncle --noui: driver exited with status 3'. Run C output: 'mode: unattended', 'building', 'Workflow complete.', 'mode: unattended', help text, exit 0.
- **Expected result:** One typed line consumed per gate and recorded as human; EOF at a gate declines/stops and never approves; later piped lines run as normal prompts in order after the build; model output never answers a gate.
- **Actual result:** A: the driver received exactly `yes` (answer file = yes), the build completed, exit 0. B: Ctrl-D made the driver's read fail, so it declined ('EOF at gate: declined'); the REPL reported 'driver exited with status 3', no answer was written, and nothing was approved. C: the piped `/mode`, `/help` and `/quit` lines ran in order after the build completed, exit 0. Not observed: (1) the real build gate attestation record showing the answer recorded as human (the fake driver writes none; the existing pty test only confirms UNCLE_ATTENDED_STDIN=1 is set); (2) model output attempting to answer a gate (no real or fake model runner was exercised). Piping into an attended build is refused by design (exit 2, 'needs an interactive terminal').

## None logged. The check is only partly covered: the curses home screen and issue-request recognition were verified, but the /help slash command and a home-chat reply were not observed. Rerun with '/help' typed before the issue request, or with a stubbed issue launcher, to cover them.

- **Status:** FAIL
- **Evidence:** Captured pty stream (~11.7KB) showing the curses home screen, then 'issue #1 User: build issue 1', 'Preparing worktree (new branch 'uncle/help')', 'Created worktree ... on branch uncle/help', 'Wrote .uncle/docs/CHANGE_REQUEST.md', 'Starting the change workflow from this issue'. No Traceback or ImportError text.
- **Expected result:** TUI renders normally with curses, home chat replies, and the issue request is still recognized as before; no import or startup errors appear.
- **Actual result:** Curses TUI home screen rendered (menu: New application / From GitHub issue / Change request / Resume / Configure / Quit, logo, chat prompt 'Describe an app or a change…', status 'claude-sonnet-5-5 (low) · Chat ready'). 'build issue 1' was recognized as an issue request: the TUI switched to an 'uncle issue #1' build view, printed 'Preparing worktree', created a worktree and branch, 'Wrote CHANGE_REQUEST.md', 'Starting the change workflow from this issue', and listed the stage panel. No import or startup errors appeared in the capture. The '/help' slash command output was not observed separately: the build view had taken over the screen, and the capture shows no /help-specific reply. A free-form home-chat reply was also not observed, because the first input launched a build. Side effect: this live run created a real sibling worktree (uncle-issue-165-issue-1) and branch uncle/help. I killed the process and removed both afterwards; git worktree list showed them gone.
