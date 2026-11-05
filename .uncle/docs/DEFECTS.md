# Defects

## MC-102

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-102
- **Actual result:** Needs interactive TUI typing and menu inspection by a person; not performed. Person: operator, at a real terminal with a logged-in runner.

## D-1

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-104
- **Actual result:** Needs interactive TUI and claude agent; also depends on MC-103, which is not in the checklist (grouping NOT DECLARED). Not performed.

## MC-105

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-105
- **Actual result:** Needs a person to decline a live tool approval prompt in the TUI. Not performed.

## MC-107

- **Status:** NOT RUN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-107
- **Actual result:** Only `uncle --noui` without an action was observed (exit 2, 'needs a startup action'). No full noui/unattended run, no TUI start with legacy config; not executed here (costly live agent runs).

## MC-201

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-201
- **Actual result:** Needs interactive TUI with a logged-in claude runner. Not performed.

## MC-202

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-202
- **Actual result:** Needs live approval prompt interaction. Not performed.

## MC-206

- **Status:** NOT RUN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-206
- **Actual result:** Not executed: requires live agent runs in noui and unattended modes. Code-level coverage: driver python suite includes no-housekeeping-test and headless-run-test, but driver results.tsv shows exit 1 for the suite commands (pre-existing failures per green-check.md) so they are not citable as a pass.

## MC-301

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-301
- **Actual result:** Needs interactive TUI and live claude agent. Not performed.

## MC-302

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-302
- **Actual result:** Needs live approval prompts. Not performed; depends on MC-301.

## MC-303

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-303
- **Actual result:** Needs live TUI confirmation prompts. Not performed; depends on MC-301.

## MC-305

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-305
- **Actual result:** Flag part observed: `uncle --housekeeping` exit 1 as unknown argument, usage free of housekeeping. TUI slash commands and Configure menus need a person; not performed.

## MC-402

- **Status:** BLOCKED-HUMAN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-402
- **Actual result:** Needs interactive TUI and menu inspection. Not performed.

## MC-406

- **Status:** NOT RUN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-406
- **Actual result:** Not executed: only the no-action `--noui` refusal (exit 2) was observed; no unattended run or piped --application run performed.

## MC-407

- **Status:** NOT RUN
- **Evidence:** see Findings
- **Expected result:** per checklist MC-407
- **Actual result:** Not executed (optional, Required NO); needs TUI launch with legacy config.
