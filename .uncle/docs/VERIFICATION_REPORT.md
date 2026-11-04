# Verification report

## Findings

### MC-101

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-102

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-103

- **Action:** Ran worktree `uncle --application demo --attended </dev/null` and `UNCLE_ATTENDED=1 uncle --application demo </dev/null` in empty /tmp/mc dirs, with inherited UNCLE_* runtime vars unset, 20s timeout.
- **Expected result:** Both exit 1 with the no-TTY refusal; nothing created.
- **Actual result:** Both exit=1, stderr was the exact refusal text, stdout empty, scratch dirs empty (ls -A).
- **Defects:** None

### MC-104

- **Action:** Only the first half ran: `--attended --unattended` gave exit 1 and the contradiction message, nothing created. The second half (`--unattended` alone) starts a live run and was not executed.
- **Expected result:** Both halves.
- **Actual result:** Half observed; check not complete.
- **Defects:** None

### MC-105

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-106

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-108

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-200

- **Action:** First half: `UNCLE_ATTENDED=1 uncle ... </dev/null` refused correctly. The `--change-request demo` invocation failed with `Error: --change-request text cannot be empty`, so the intended refusal was not observed.
- **Expected result:** Both refuse with the no-TTY message.
- **Actual result:** Second half not observed (invocation form wrong, not a verdict on the app).
- **Defects:** None

### MC-201

- **Action:** `uncle` and stagegate.sh printed the contradiction message. change-workflow.sh printed `Plan executability: another workflow holds this checkout` and not the contradiction message.
- **Expected result:** All three entry points refuse.
- **Actual result:** change-workflow.sh not observed refusing; possibly blocked by this workflow's lock.
- **Defects:** None

### MC-202

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-203

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-204

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-206

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-301

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-302

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-303

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-304

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-305

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-401

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-402

- **Action:** Ran no-TTY `--attended` and `--attended --unattended` (same method as MC-103/MC-104a).
- **Expected result:** Refusals, exit nonzero, no .uncle/workflow/mode.
- **Actual result:** exit=1 each; stderr matched both refusal texts; scratch dirs empty.
- **Defects:** None

### MC-403

- **Action:** None performed; a run of `--unattended` starts a live agent run.
- **Expected result:** One deprecation notice on stderr, stdout unchanged.
- **Actual result:** Not observed.
- **Defects:** None

### MC-404

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-405

- **Action:** None performed.
- **Expected result:** See checklist.
- **Actual result:** Needs a live unattended issue or change run to completion with PR/report; not performed.
- **Defects:** None

### MC-406

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-407

- **Action:** None performed.
- **Expected result:** See MANUAL_CHECKLIST.md.
- **Actual result:** Needs a real interactive terminal (TTY/TUI) and a live agent run; none available to this headless worker.
- **Defects:** None

### MC-408

- **Action:** None performed.
- **Expected result:** See checklist.
- **Actual result:** Needs a newer published version available plus a terminal. Action: stage a newer version fixture and run in a TTY.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-102 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-103 | YES | PASS | terminal output /tmp/mc |
| MC-104 | YES | NOT RUN | not executed or only partly executed |
| MC-105 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-106 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-108 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-200 | YES | NOT RUN | not executed or only partly executed |
| MC-201 | YES | NOT RUN | not executed or only partly executed |
| MC-202 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-203 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-204 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-206 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-301 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-302 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-303 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-304 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-305 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-401 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-402 | YES | PASS | terminal output /tmp/mc |
| MC-403 | YES | NOT RUN | not executed or only partly executed |
| MC-404 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-405 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-406 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-407 | YES | BLOCKED-HUMAN | requires real TTY/person |
| MC-408 | YES | BLOCKED-SETUP | newer version fixture needed |
