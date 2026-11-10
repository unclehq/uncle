# Change Request

Issue 230

Seeded from [unclehq/uncle#230](https://github.com/unclehq/uncle/issues/230).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

One refused model call throws away the whole parallel project plan, and a host spending stop (HTTP 402) is reported as a bad Base URL or key; #213 was closed with no change

## Motivation

## Summary

On a hosted, headless run with a per-task spending limit, the host refused one of Uncle's project-plan model calls with HTTP 402 `budget_reached`. Three things then went wrong in Uncle:

1. **One refused call threw away the whole parallel plan.** The bounded section scheduler waits for the other workers to finish, which means paying for their calls, then returns failure. The driver deletes the sections and writes the plan again in a single pass. Most of the run's model spend so far went into the discarded sections.
2. **The spending stop is reported as a configuration problem:** `Model API request failed (HTTP 402: {"code":"budget_reached",…}); check the Base URL, API key and model`. Nothing in Uncle reads the 402 body or the host's remaining-budget headers.
3. **#213 asked for exactly this and was closed as completed on 2026-11-10 at 00:05 UTC, but no change implements it.** At `main` `5a5cd30`, nothing under `scripts/` reads `budget_reached`, `balance_exhausted` or any `x-seren-budget-*` header (`grep -rn` returns nothing). No commit mentions #213, `402` or `budget_reached`. The nearest commit, `3a20810` (#212), adds Uncle's own `--max-budget-usd` cap (`scripts/lib/budget.py`), which is a different limit.

The host had its own bug, which it is fixing separately: it held too much money for each call in flight, so the stop came early. Even with that fixed, a long build on a host with spending limits will reach a real limit, and Uncle has to handle the stop.

## What happened (2026-11-10, UTC)

Self-hosted runner pointed at the host's OpenAI-compatible endpoint, headless (no terminal in the sandbox), project-plan sections on (the default), task limit $6.00. Hosted mode (#211, `688d219`) sets no concurrency limit, so unless the host's script sets one, the self-hosted default of 24 calls at once applies. At least five calls were running together when the host refused one.

| Time | What happened |
|---|---|
| 08:05:29 | Build started. |
| 08:07:52–08:08:58 | 17 model calls recorded within 66 seconds. 14 of them read fewer than 1,100 cached tokens and wrote 8,166–12,059 new ones, which fits the 14 phase-2 section workers starting together. |
| about 08:08:29 | The host refused one call: `HTTP 402 {"code":"budget_reached","scope":"task","limit_atomic":6000000,"used_atomic":5310221,"suggested_increase_atomic":60000}` (amounts in millionths of a US dollar). |
| 08:08:36–08:09:02 | The workers already running finished. By then Uncle had spent $2.28 in this build. |
| 08:10:31–08:12:41 | Single-pass plan, after the fallback: $0.55. |
| 08:13:30 | Uncle exited 1 on a plan check (#231). The host's build script printed `FAILED: Uncle did not finish cleanly (exit 1). Not publishing.` |

## Code paths (main `5a5cd30`)

Blame is `git blame -w`.

| Where | What it does | Last changed by |
|---|---|---|
| `scripts/lib/unit_scheduler.py:65-81` (`capacity`) | With no `max-concurrency` setting, the self-hosted runner allows 24 model calls at once (`:77-78`); other runners return 0, meaning no limit. | `f6415d5bf` 2026-10-31 |
| `scripts/lib/model-jobs.sh:40-52` (`workflow_model_capacity`) | Passes that capacity to the plan stage. | `f6415d5bf` 2026-10-31 |
| `scripts/lib/project_plan_sections.py:82-89` (`PHASES`, `GATE`) | 8 workers in phase 1 (`outline behaviors handling checks decisions restrictions limits bounds`), 14 in phase 2 (`design state domain components flow steps sequence invariants guards tests defects obligations commands closing`). | `82fbc92a9` 2026-10-27, `68a94e53b` 2026-10-28, `8c5257472` 2026-10-28, `0ca7c3b56` 2026-10-31 |
| `scripts/stagegate.sh:4464-4486` (`project_plan_sections_enabled`) | Sections are on by default (`WORKFLOW_PROJECT_PLAN_SECTIONS` defaults to `1`), whatever the brief's size. | `29bb94995` 2026-10-28 ("Restore project-plan sections (subagent fan-out) as the default"), `b3ef425f0` 2026-10-28 |
| `scripts/stagegate.sh:4342-4396` (`run_project_plan_sections_bounded`) | Starts workers up to the capacity; phase 2 joins once the gate workers finish, so up to 22 can run together. On any failure it waits for every running worker, then returns 1 (`:4374-4378`). Finished sections are not kept for a resume. | `c22b6cb09` 2026-10-30, `0ca7c3b56` 2026-10-31, `f6415d5bf` 2026-10-31 |
| `scripts/stagegate.sh:4398-4462` (`run_project_plan_sections`) | The unbounded version, used when capacity is 0, with the same any-failure-returns-1 rule (`:4429-4433`, `:4438-4442`). | `82fbc92a9`, `68a94e53b`, `c22b6cb09`, `666902f1a`, `0ca7c3b56`, `f6415d5bf` |
| `scripts/stagegate.sh:4557-4570` | "Any failure -- a worker, a section out of its lane, an assembled plan the validators refuse -- leaves no investigation behind and the single-pass plan runs as it always did." A spending stop is handled like any other failure, so the single pass runs into the same limit. | `ed8609fb9` 2026-09-23, `82fbc92a9` 2026-10-27, `b3ef425f0` 2026-10-28 |
| `scripts/lib/self_hosted_http.py:930` (`RETRYABLE_STATUS`) | 402 is not retried. That part is right. | |
| `scripts/lib/self_hosted_http.py:1330-1332` and `:1428-1430` | A non-`REJECTED` HTTP error, including 402, becomes `ValueError('Model API request failed (HTTP %d%s); check the Base URL, API key and model')`. | `31063570c` 2026-10-25, `69ada3524` 2026-10-30, `a0ef1e24d` 2026-11-08 |
| `scripts/lib/supervisor.py:406-412` (`_EXTERNAL_CAPACITY`) | The "provider or session limit" pattern matches 429, quota, rate and session limits, but not 402, `budget_reached` or `balance_exhausted`. A spending stop under the TUI is diagnosed like a bug. | `a539b7130` 2026-09-20 |

## Fix

1. **Recognize a spending stop.** In `self_hosted_http.py`, turn HTTP 402 whose JSON body has `code` `budget_reached` (with `scope`, `limit_atomic`, `used_atomic`, `suggested_increase_atomic`) or `balance_exhausted` (with `balance_atomic`) into a typed `SpendingStop`, not a `ValueError` about the Base URL.
2. **Stop cleanly and keep the work.**
   - In both section schedulers, on a `SpendingStop`: start no new workers, let running ones finish, keep every finished section, and return a distinct status.
   - The stage then skips the single-pass fallback, writes `spending_limit` to `stop-reason` with the host's figures, and exits with its own exit code.
   - A resume after the host raises the limit reuses the finished sections and runs only the missing ones.
3. **Say what happened.** Print one line the host's chat can pass on, for example `Stopped: the task spending limit ($6.00) was reached; about $0.06 more lets the next step start.` Add 402, `budget_reached` and `balance_exhausted` to `_EXTERNAL_CAPACITY`.
4. **Read the host's budget headers (#213).** Each reply carries `x-seren-budget-task-remaining-atomic` and the related headers. Start no more parallel workers than the remaining task budget allows at the stage's typical per-call cost, and stop before a call the host would refuse.
5. Reopen #213, or note in it that this issue replaces it.

## Tests to add

- `self-hosted-spending-stop-test.py`: a fake server answers one call with the 402 body above. The stage raises `SpendingStop`, not `ValueError`, and the message names the limit and the suggested amount.
- Section scheduler test (bounded and unbounded): with 14 workers, one gets a `SpendingStop`. No new worker starts after it, finished sections stay on disk, the single-pass fallback does not run, `stop-reason` is `spending_limit`, and the exit code is the new one.
- Resume test: after the stop, a resume with the server accepting calls runs only the sections that hadn't finished.
- `supervisor` test: `external_capacity_failure('HTTP 402: {"code":"budget_reached"}')` is true.

## Related

- #213: closed as completed, with no change.
- #212: Uncle's own per-stage budget cap (`3a20810`), a different limit.
- #231: the plan check that ended this build after the fallback.

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
