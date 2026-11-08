# Implementation notes

## Step 1

### Files changed

- `scripts/lib/home_preload.py` — Written by isolated step 1; 1

## Step 2

### Files changed

- `scripts/tests/home-preload-test.py` — Written by isolated step 2; 2

## Step 3

### Files changed

- `uncle_tui.py` — Written by isolated step 3; 3

## Step 4

## Post-audit repairs (FA-009, FA-014, FA-002)

- Added the plan-required tests to `scripts/tests/home-preload-test.py` (class `PlanScope`): timeout deadline and timer, cancel-wait bound, creation races, no operator grants, argv/cwd/env hardening, output and size caps. Injecting each of four defects makes a test fail.
- Fixed `uncle_tui.py`: the preload passed `PRELOAD_TIMEOUT_S` as an absolute deadline to `session.turn`, so the turn was already expired and every preload aborted. It now passes `time.monotonic() + PRELOAD_TIMEOUT_S`.
- Fixed `scripts/lib/home_preload.py`: `default_runner` read stdout before waiting, so its timeout never fired on a hung command. A timer now kills it.
- FA-014: `supervisor-test.py` and `attestation-statement-test.py` fail on `main` (a stray `.uncle` line in `.gitignore`; unsigned test commits), and pass on this branch. The test commits now use `--no-gpg-sign`.
- `uncle verify`: the head-tree check strips Uncle's managed `.gitignore` lines the way the release snapshot does; predicate approvals now carry `view_digest`.
- FA-002: MC-401/402 reclassified; the opt-out half of MC-401 was run and observed. The `--noui` half and MC-402's responsiveness remain unverified.
- Known gap: no test drives a stream-level tool-use event into a live session; the tests show only that preload adds no grants.

## Manual checks run without tmux (pty)

- MC-101/MC-200 PASS. MC-106/MC-206 first FAILED: a failed preload wrote "The home agent is unavailable" into the home history at startup. `uncle_tui.py` now suppresses that note while the preload holds the lock; the first operator message still reports it. A regression test covers both.
- MC-102/MC-201: opt-out half observed; the `--noui` wrapper half is still BLOCKED-SETUP.
