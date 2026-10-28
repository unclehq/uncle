# Where Markdown still reaches an agent, and what to convert next

Rule being applied (see [plan-model.md](plan-model.md)): agents and LLMs exchange JSON only; Markdown is rendered from
JSON for people. This inventory was taken from a scan of `prompts/`, `scripts/*.sh` and `scripts/lib/` on 2026-10-27, plus
what the noinit and calculator-local runs showed. It lists what is done, what is built but switched off, and what is open.

## Done and on by default

| Area | What is JSON now |
|---|---|
| Worker to driver packets | Section workers, edit writers, resolvers, preflight, review, checklist and audit workers deliver `uncle.artifact/v1` packets (schema-forced where the runner allows). |
| Project plan authoring (new application) | Section workers write typed blocks; the outline is a JSON packet; the driver assembles the model and stores it beside the plan. `WORKFLOW_PLAN_BLOCKS=0` reverts. |
| Updated plan | Writers and resolvers edit the plan model by id (`ops`). `WORKFLOW_UPDATED_PLAN_OPS=0` reverts. Review findings and specialist corrections reach the writers as JSON, not Markdown tables. |
| Updated change plan | Same ops pipeline, on the change plan's model. |

## Built, switched off (needs a live run before it can be the default)

| Switch | What it does | What to compare |
|---|---|---|
| `WORKFLOW_CHANGE_PLAN_BLOCKS=1` | The combined change-planning pass writes `change_plan` as typed blocks (`sections`) instead of a `narrative` string. The bundle publisher renders the narrative and stores `CHANGE_PLAN.model.json`. Hosted runners only. | Whether the planning agent writes valid blocks without a retry pass; the plan's quality against a narrative run. |
| `WORKFLOW_AGENT_PLAN_VIEW=1` | The adversarial-review workers read the plan as JSON (the model, commands and protected paths, no Markdown narrative) instead of the canonical `PROJECT_PLAN.json`. | Finding quality and ids cited, against the default. |

## Open, in the order I would do them

1. **Single-pass project-plan fallback.** One agent writes the whole plan as Markdown (`prompts/project-plan.md`). Same conversion as the
   sections: a whole-plan block packet with free headings, rendered by the driver. Smallest remaining step; only runs when the sectioned
   plan fails.
2. **Requirements interpretation.** The deliverable is a `narrative` string. It feeds every later stage, so it is the next most valuable
   document to turn into typed rows (requirements, acceptance obligations, assumptions).
3. **Reviewers and checklists as consumers.** Switch the remaining stages that read the plan (checklist workers, test review, final audit,
   preflight) to the agent view, one stage per live run, as for adversarial review.
4. **Other narrative deliverables.** Preflight report, test review, baseline report, change spec: each is a `narrative` plus a few fields. They
   need row kinds (and an importer for old runs) before they can become blocks.
5. **Replace the Markdown parsers.** These read the plan as text and should read the model: `plan-scope.sh` (Owns lines),
   `plan-executability.py`, `plan_context.py`, `step_groups.py`, `plan_parallelism.py`, `plan_ownership_gap.py`,
   `acceptance_context.py`, `green-check.sh`, `document-layout.sh`. They keep working while the narrative is rendered from the model.
6. **Remove `narrative` from agent-facing JSON** once nothing reads it; it stays as the human view.

## What I could not verify here

Every switch above is covered by stub-driven tests only. Whether a model writes good blocks, or reads the agent view as well as the
Markdown, is shown only by a live run. Local models are the least certain: their grammar is fixed per packet kind, so limits such as
"this worker may only use these row kinds" are enforced by the prompt, not the grammar, and the change-plan blocks switch does not
apply to them at all.

## Markdown the drivers still build for people (not for agents)

`build_timing.py`, `artifact_json.py` renderers, `document-layout.sh`, `from-issue.sh`, `performance-report.sh`, `test_report.py`,
`repair_check.py`, `implementation_notes.py`, `final-audit-context.py`, `checklist_batch.py`, `checklist_report_fallback.py`. These render
reports for the human gates and are correct as they are; the thing to check, stage by stage, is that no agent is later told to read them.

## Found in the third noinit run (not a Markdown problem)

The run reported COMPLETE, but only because an unattended run skipped 14 blocking audit findings. The cause of nearly all of them:
`npm ci` was the plan's install fallback, a new project has no `package-lock.json`, and no implementation step may install, so
the first green-check command failed and `node_modules` never existed (5 of 6 commands, no test or mutation ever ran).

Fixed: `scripts/lib/install_command.py` rewrites `npm ci` to `npm install` (and drops `--frozen-lockfile` for yarn and pnpm) in the
green-check command list when the project has no lockfile, prints what it changed and records it in
`.uncle/workflow/green-check.rewrites`. The plan prompts and the commands worker are told to use `npm install` for a new project.

Still open from that run: checklist workers are denied `shasum`, `lsof` and `npm run start` (6 of 13 manual checks blocked); step 1
replaced an existing `index.html` against the plan's merge-in-place rule and wrote `launch.json` for port 5173 while the start script
serves 4173; an unattended run still ends in COMPLETE over skipped blocking findings; plan prose cross-references (obligation O-6
says M-1..M-15, the table lists M-1..M-18) are not checked.

## Found in the fifth noinit run (green check never ran)

Run with the decide-and-edit updated plan, the split project-plan workers and parallel sandboxes: 228 s to the green check
(project plan 65 s, updated plan 33 s, implementation 55 s). It stopped in REPAIR before running any check:
`VERIFICATION_INTEGRITY.md`: "Missing protected verification path: package-lock.json".

Two defects, both fixed:
1. The plan listed `package-lock.json` as a protected verification path. It does not exist in a new project and the plan's own install
   command creates it, so it can be neither hashed before the install nor unchanged after it. `install_command.py unprotect` now drops
   a lockfile that does not exist from the protected paths when the first snapshot is taken (an existing repository's lockfile stays
   protected), and the plan writers are told not to list one.
2. `parallel_checks.py` re-checks the protected inputs itself but was not given the list of paths allowed to be absent (the serial guard
   was), so any protected path that legitimately did not exist yet read as "Missing". `green-check.sh` now passes it.

To retry that project: remove `.uncle/workflow/verification.*` (and the failed repair state) and resume, or rerun from the plan.

Option A on this run: 19 deciding writers (16 Accepted, 2 Partially accepted, 1 Rejected), 6 resolver groups, the reconciler added 4 edits,
none left out. The longest implementation step (56 s) wrote 11 KB of mutation-runner code; time follows output size, so a plan whose
outline puts two large files in one step has a long pole the driver does not split.

