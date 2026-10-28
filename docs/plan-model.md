# Structured plan model

Status: **phase 0 spec, decisions made** (see the end). **Phase 1 is built**: `scripts/lib/plan_model.py`
and `scripts/tests/plan-model-test.py`. **Phase 2 is built and ran once on hosted Claude** (noinit, 2026-10-27). **Phase 3 is built for the
new-application project plan** (section workers write typed blocks; the outline is JSON; the driver assembles the
model) but has not run against a real model; the change workflow's plan authoring is not ported. Phases 4 and 5
are not started.

## Principle

Agents and LLMs exchange JSON, never Markdown. Every artifact one agent hands to another, every payload a
prompt embeds (plan, review findings, worker packets, reports), and every reply is a JSON object checked
against a schema. Markdown exists only as a view rendered from that JSON for people (the approval gates and
the `.uncle/docs/*.md` files). No agent reads or writes it, and no driver parses it. Instruction text in a
prompt stays natural language; the data inside it is JSON.

Corollary for values: a field holds plain text. Markdown syntax (backticks around paths, bold titles, pipe
escaping, table padding) is added by the renderer, so a model never has to produce or preserve it.

## Why

A plan is one JSON field, `narrative`, holding a Markdown string. Models change it by quoting text
(`replace_text`), naming a heading, or inserting a section, and each of those can miss: a quote that is
not in the plan, a subsection title used as a section, content that is not a `## ` section. The driver
now repairs, retargets, retries and leaves out what it cannot place (`updated_plan_edits.py`), which keeps
runs alive but treats a symptom. Measured on the calculator-local run: 17 of 30 writer edits were inside
a line that begins with a plan ID, 3 of the 6 unplaceable edits were test rows an ID would have addressed,
and `C-1` begins four lines of one section (the table row plus data-flow lines), so line-start IDs alone
are not unique.

The fix is to make the plan data. A model then names a thing that exists (an id) and a field, and the
runner's grammar can enforce that the id exists.

## Goals and non-goals

Goals
- Plan edits address blocks by id. No quoted text, no heading matching, no line numbers.
- The per-call schema lists the ids and columns that exist, so a wrong target cannot be written.
- Overlap between writers is exact (same id, same field), not substring matching.
- Markdown is rendered from the data, deterministically, for humans only.
- Every stage that reads the plan (review, implementation, checklists, audits) receives plan JSON, whole or
  as a scoped view, not Markdown.
- Every existing plan, including those already on disk, loads into the model.

Non-goals
- Changing what a plan must contain (the section list, traceability rules, `Owns:` semantics).
- `verification_commands` and `protected_verification_paths` stay separate top-level fields as today.

## Data model

`kind: plan` (and `change-plan`) gains `sections`. When `sections` is present it is authoritative and
`narrative` is derived from it on every write, as the human view only: no prompt embeds it and no agent is
asked to read or write it. A plan with only `narrative` (every plan before this change) is imported on load.

```
plan.sections[]  = { id, heading, blocks[] }
```

- `id`: stable, assigned once, never renumbered (`s1`, `s2` ... next unused number for a new section).
- `heading`: the title without the `##` marks, e.g. `6. Observable behaviors`. A rename is an edit to
  this field; the id is what edits address.
- The preamble (`# Project plan`) is `plan.title`.

Blocks (every block has an `id`; `kind` selects the rest):

| kind | fields | renders as |
|---|---|---|
| `prose` | `text` (plain text, paragraphs separated by a blank line) | paragraphs |
| `heading` | `level` (3-6), `text` (without the `#` marks) | `### 10.2 Test file inventory` |
| `rows` | `row_kind` (one of the row kinds below), `rows[{id, ...fields}]` | pipe table with that kind's column titles |
| `table` | `columns[]`, `rows[{id, cells[]}]` | pipe table; only for a table that matches no row kind |
| `list` | `ordered`, `items[{id, depth, text, number?, style?}]` | `- ` or `1. ` items; `number` keeps a numbered item's number (a list may start at 0), `style` marks a numbered item inside a bullet list or the reverse |
| `steps` | `items[{id, number, title, text, owns[], depends_on[]}]` | the Implementation order list |
| `code` | `lang`, `text` | fenced block |
| `raw` | `text` | anything the importer could not classify, verbatim |

Ids
- Where the plan already has one, it is the id: a typed row's id field (`T-33`, `C-3`). Block ids and
  row/item ids are one namespace per plan; the importer reports a duplicate definition (two rows `T-33`).
  Cross-references (`C-1 -> C-3: ...` in a list or prose, or the `requirements` field of a row) are text
  or id lists, never definitions, so they cannot collide with the row that defines the id.
- A list item that begins with an ID keeps a generated id and the ID stays in its text; only typed rows
  define ids.
- Real plans do reuse an id across kinds: in calculator-local, component `C-1` and concurrency concern `C-1`.
  The importer keeps the first definition's id and addresses the second as `<block id>/<id>`, with the id it
  displays kept in `label`. Newly written plans must use plan-wide unique ids, which the validator enforces.
- Everything else gets a generated id, `<section id>.<n>` (`s4.7`), assigned at import in document order and
  stored. New blocks take the next unused number in their section. Ids are never reused after a delete.
- Steps are addressed by `step-<number>` as written in the plan; `depends_on` holds step numbers.

## Row kinds

A typed row block holds rows of one kind. Each kind has fixed field names, so a model writes `result`,
never "Observable result" or "Expected result", and the grammar lists the fields statically. Fields are
plain text unless marked `[]` (an array of strings, joined with `, ` when rendered). The first field is
the row id unless the kind is keyed otherwise.

| row_kind | fields (rendered column title) |
|---|---|
| `behavior` | id (ID), trigger (Trigger), result (Observable result), failure (Failure behavior), requirements[] (Requirement IDs), verification (Verification) |
| `invariant` | id, statement (Invariant), scope (Scope), enforcement (Enforcement point), test (Automated test), impact (Violation impact) |
| `failure` | id, scenario (Failure scenario), symptom (Observable symptom), handling (Handling), requirements[] |
| `concurrency` | id, concern (Concern), mechanism (Mechanism), rationale (Rationale) |
| `component` | id, name (Name), files[] (File(s)), responsibility (Responsibility), state (Key props/state), depends_on[] (Dependencies) |
| `state_field` | field (Field, the key), type (Type), initial (Initial value), description (Description) |
| `automated_test` | id, name (Test name), assertion (Assertion), requirements[] |
| `obligation` | id, obligation (Obligation), assertion (Observable assertion and independent oracle), evidence (Evidence) |
| `manual_check` | id, check (Check), assertion (Observable assertion), prerequisites (Prerequisites), evidence (Evidence to retain), requirements[] |
| `mutation` | id, mutation (Mutation), test (Targeted test), expected (Expected result) |
| `restriction` | id (R-ID), source_kind (source_kind), source (Source), requirements[] (Reqs), property (Property), mechanism (Mechanism), rationale (Rationale), cap (CAP), phase (Phase), evidence (Evidence) |
| `decision` | id, decision (Decision), reason (Reason) |
| `traceability` | requirement (Requirement, the key), behaviors[], invariants[], components[], tests[] (Automated test), manual[] (Manual check) |
| `change_impact` | component (Component, the key), change (Planned change), reason, risk (Regression risk), coverage (Test coverage) |

Because requirement, behavior, invariant, test and component references are id arrays, the validator can
check that every referenced id is defined, which a Markdown plan cannot do.

The importer maps a legacy table to a kind by its header words (normalized, with synonyms such as
"Expected result" for `result`); a header that matches no kind stays a generic `table`. Optional fields a
legacy table lacks are empty strings; fields a table has beyond the kind (e.g. `Source` on a 3-column
behavior table) are kept in an `extra` object on the row and rendered as extra columns, so nothing is lost.

## Rendering (canonical form)

`render(plan)` is a pure function and the only writer of `narrative`.
- Sections in order, `heading`, blank line, blocks separated by one blank line. One blank line between
  sections, file ends with a single newline (same as `join_sections` today).
- Tables are not column-padded: `| a | b |` with a `|---|---|` separator; the renderer escapes `|` and
  newlines in cells. A typed block uses its kind's column titles, plus one column per `extra` key.
- Steps: `N. **Title** — text`, then `   Owns: ` + comma-separated backticked paths, then
  `   Depends on: N, M` when non-empty. The form `plan-scope.sh` parses today, kept so the human view and
  the legacy parsers agree until phase 4 removes them.
- `code` blocks are emitted verbatim. `raw` blocks (legacy import only) are emitted verbatim.

Round-trip contract: the model is the source of truth, so the direction that must be lossless is
`import(render(model)) == model` (a plan someone approved as Markdown comes back as the same data). The
reverse, `render(import(md))`, holds for legacy plans only up to normalization (table padding, blank-line
runs, markup the importer strips from values such as backticks around a path), and the round-trip test
reports it per plan. Anything the importer cannot place in a typed block becomes `raw`, so import is
total; the test reports how much of each plan is `raw`.

## Import rules (Markdown to model)

This is for legacy plans and plans a person edited as Markdown; model-written plans never pass through it.
It also strips markup into plain values (backticks around `Owns:` paths, `**Title**` to `title`).

1. Split on `## ` headings (`plan_patch.split_sections`). Text before the first is `title`.
2. Within a section, walk lines: `### ` and deeper start a `heading` block; a fenced region is `code`;
   a pipe table with a header and separator row is a typed `rows` block when its header matches a row kind
   (see Row kinds), else a generic `table`; consecutive
   `- `/`* `/`N. ` lines are a `list` (continuation lines join the item); in a section whose heading
   contains `Implementation` a numbered list whose items end with `Owns:` is `steps`; remaining runs are
   `prose`; unclassifiable runs are `raw`.
3. Sections the plan has beyond the required list (e.g. `## Decision Record`, `## Restriction
   Inventory`) import like any other.

## Operations

A patch is `{ "ops": [...] }`. Each op names ids that exist (or, for inserts, an anchor id that exists).
A runner with grammar enforcement lists the allowed ids in the schema; the driver validates the rest.

| op | fields | effect |
|---|---|---|
| `set_fields` | `id`, `fields{name: value}` | changes only the named fields of one row (names are the row kind's fields) |
| `set_text` | `id`, `text` | prose block, list item, or step body |
| `set_step` | `id`, any of `title`, `text`, `owns`, `depends_on` | changes those step fields |
| `insert_row` | `block`, `after` (row id, or null for first), `row{id, ...fields}` | adds a row of that block's kind |
| `insert_item` | `list`, `after`, `id`, `text` | adds a list item or step |
| `insert_block` | `section`, `after` (block id or null), `block` | adds a block |
| `delete` | `id` | removes a block, row, item or step |
| `replace_section` | `section`, `blocks[]` | replaces a section's blocks (the existing `edit_sections`) |
| `insert_section` | `after` (section id), `heading`, `blocks[]` | adds a section |
| `set_heading` | `section`, `heading` | renames a section |

Conflicts (what makes two edits overlap, replacing substring matching):
- same `id` (and the same field for `set_fields`);
- `delete` of an id with any other op on it;
- `replace_section` with any op on a block of that section;
- two inserts after the same anchor (order would be ambiguous), unless identical.
Identical ops from two writers are one op. A conflicting group goes to a resolver, who sees the current
value of that one id and answers with one op.

After applying all ops the validator runs: ids unique, `depends_on` numbers exist and are acyclic, `owns`
paths non-empty for steps, required sections present, every `set_*`/`delete` target existed. A violation
names the op, so the same targeted retry used today applies.

## Compatibility and migration

- `uncle.artifact/v1` and `kind` are unchanged; `sections` is additive. During the migration a consumer not
  yet ported still reads `narrative` (the rendered view); that is a temporary bridge, not the design.
- Legacy ops (`replace_text`, `replace_item`, `edit_sections`, `insert_sections`) are still accepted when
  the plan has only `narrative`, and are applied to the rendered text. Once a plan has `sections` they
  are rejected with a message naming the op that replaces them.
- Importing is idempotent and runs on load, so runs already in progress upgrade on `/resume`.
- Approval and prompt hashes are over the rendered Markdown, which the round-trip contract keeps stable.
  (Not verified yet: confirm which gates hash which bytes before phase 1 changes any writer.)

## Phases

0. This spec. Approval gate.
1. `scripts/lib/plan_model.py`: import, render, validate, apply ops, conflicts, plus round-trip tests on
   every saved plan (calculator-local, noinit, uncle-issue-113, repo fixtures).
2. Edit pipeline: updated-plan writers, resolvers and the single-call fallback emit ops; per-call schemas list
   ids; `updated_plan_edits.py` conflict detection moves to ops; quote repair/retarget/leave-out stay as the
   fallback for legacy plans.
3. Authoring: project-plan section workers, outline and the single-pass fallback emit blocks; the change
   workflow's change-plan and updated-change-plan.
4. Agents read JSON, required by the principle: every prompt that embeds the plan (adversarial review,
   updated plan, implementation, preflight, test review, checklists, final audit, and the change-workflow
   equivalents) embeds plan JSON or a scoped view of it; and the Markdown parsers read the model instead
   (`plan-scope.sh`, `plan-executability.py`, `plan_context.py`, `step_groups.py`, `plan_parallelism.py`,
   `plan_ownership_gap.py`, `acceptance_context.py`).
5. Same for the other payloads prompts carry as Markdown today (findings tables, worker packets, reports):
   audit each stage for data passed as Markdown or free text and make it a schema-checked JSON object.
6. Remove dead paths and `narrative` from every prompt; it remains only as the human view.

Gate between 2 and 3: run one real local-model updated-plan and compare retry count and wall time with
the calculator-local baseline before committing to model-written blocks.

## Acceptance criteria

- Every saved plan round-trips; the report lists the share of `raw` per plan and it is below 5% of lines.
- Replaying the calculator-local writer output as ops merges all 8 overlap groups with no retry and no
  left-out edit.
- No prompt embeds plan Markdown and no stage reads the plan through a Markdown regex (phase 4); a test
  scans the prompts and drivers for both.
- Every stage reply is a schema-checked JSON object (phase 5 audit).
- Existing tests pass or have equivalents.

## Risks

- Models may write blocks worse than prose; measured at the 2-to-3 gate, not assumed.
- Grammar size grows with the number of ids; local server limits unknown. Tiered fallback: enumerate ids
  where the server accepts it, validate in the driver where it does not.
- Prose with no id is edited by whole-block replacement, coarser than a snippet edit.
- Plan JSON in prompts costs more tokens than Markdown tables; scoped views (only the sections a stage
  needs) keep that in check and must be designed per stage.
- Phase 4 touches every stage's prompt, so it is the largest piece and needs its own sub-plan per stage.

## Decisions made

1. `narrative` stays on disk as the derived, human-only view for the `.uncle/docs` files.
2. Typed row blocks (the Row kinds above), with a generic `table` only for tables that match no kind.
3. People do not hand-edit the Markdown plan (for now). The Markdown importer therefore serves legacy
   plans and runs already in progress, not an ongoing edit path, and the gates need not re-import Markdown.

## Phase 1 results

Measured on the 16 plans saved on this machine (2 project plans from local runs, 14 change plans):
- Every plan imports with no lost or added words, re-imports to an identical model, and validates with no
  errors. Typed row blocks cover most tables; the rest (layer/runner matrices, finding dispositions,
  implementation-step tables) stay generic `table` blocks.
- Findings that changed the spec: an id reused across kinds (above); a table cell with a bare `|` (inside a
  code span, or an unescaped regex), handled by not splitting inside code spans and keeping overflow cells in
  the last column; numbered items inside bullet lists and lists starting at 0 (the list fields above).
- Header spellings vary run to run for one logical table (six spellings of the restrictions table); the
  importer maps them to one row kind, and rendering uses the kind's canonical column titles.
- Not built yet: per-call JSON Schemas for ops (phase 2), the edit-writer and resolver pipeline on ops, and
  any change to prompts or drivers.

## Phase 2 results

What was built
- `updated_plan_ops.py`: the writer prompt (the plan model as JSON; no Markdown plan, no text-patch rules), the merge,
  conflict groups, resolver prompts, and the resolver-answer check. `worker_schemas.py` has `edit-ops` and
  `resolve-ops`, whose per-call schemas list the ids that exist; the static forms are registered so a local grammar
  enforces the shape too (new packet kinds `updated-plan-edit-ops-packet` and `updated-plan-resolution-ops-packet`).
- Ops are flat and every value is a string, so any grammar accepts them: `set_fields`, `set_text`, `set_step`,
  `insert_row`, `insert_item`, `insert_block`, `delete`, `insert_section`. A list field is one comma-separated string;
  `plan_model.typed_op` turns it into the typed op.
- The merge publishes the section-level patch (`edit_sections`, `insert_sections`) the pipeline already reads, so
  nothing downstream changed; untouched sections stay byte-identical to the base plan.
- Both drivers (`stagegate.sh`, `change-workflow.sh`) use ops mode by default; `WORKFLOW_UPDATED_PLAN_OPS=0` keeps the
  text patches. Any ops failure returns nonzero, so the single-call fallback runs exactly as before.

Behavior
- Two writers conflict only on the same field of the same id (or a delete / whole-section rewrite against an edit
  inside it, or two inserts after the same anchor). Different fields of one row never need a resolver.
- An op naming an id or field that does not exist is not fatal: it becomes a resolver group showing the current rows.
  After a resolver is asked again, an op that still cannot apply is left out and the findings behind it are marked
  Partially accepted, as in the text-patch mode.
- Not offered to writers yet: renaming or deleting a section, creating a typed table, editing generic `table` rows.
  Those fall back to a resolver or the single call.

Dry run on the saved calculator-local writer output, replayed as id ops (no model):
- 14 of 30 saved text edits convert to ops mechanically. Of the other 16, 8 quote text no node holds, 4 are row
  lines the converter could not locate, and 4 are new rows (inserts).
- Overlap groups needing a resolver: 3 (component `C-1`, `step-9`, and one command group), down from 8 for the
  quoted-text edits of the same run. With a stand-in resolver that keeps the last writer's ops, the merge completes,
  the patch applies, 6 sections are edited, and 12 of 18 sections stay byte-identical.
- This shows the mechanics, not how a model writes ops. The gate before phase 3 is still one real local-model
  updated-plan run, comparing retries and wall time with the calculator-local baseline.

Tests: `plan-model-test.py`, `updated-plan-ops-test.py`, `updated-plan-ops-driver-test.sh` and
`updated-change-plan-ops-driver-test.sh` are new; the text-patch driver tests are pinned to
`WORKFLOW_UPDATED_PLAN_OPS=0` so that mode stays covered.


Full test run (252 test files, 3 at a time, 2026-10-27): 213 pass, 38 fail, 1 skipped (`self-hosted-live-test.py`
needs a live server). The same run on a pristine export of HEAD (248 files) fails the same 38 tests, so the working
tree adds no failure; the four new test files pass. The 38 are not caused by this work: several extract shell
functions from the drivers that no longer exist under those names (`command not found`), some need a logged-in
`claude` or an installed `cline`. They are worth their own cleanup.

## noinit: the first real run of ops (hosted Claude)

The updated-plan stage of a noinit run (17 findings, 17 writers, 7 resolver groups) used ops mode with no fallback:
- 45 ops from 17 writers (35 `set_fields`, 5 `set_text`, 4 `insert_block`, 1 `insert_row`); no writer wrote a text
  patch and no op named an invalid id or field.
- 6 id-conflict groups and 1 command group, all resolved; every resolver answer passed the check.
- Wall time of the stage's moving parts: writers 16 s (parallel), resolvers 11 s (parallel); the whole speculative
  updated-plan stage 51 s.
- One defect found and fixed: a single dropped duplicate insert (a resolver repeating a row another writer had already
  inserted) marked all 17 findings Partially accepted. Dropped ops are now attributed to the writers who wrote them,
  and a duplicate insert, which loses nothing, marks nobody. Replaying noinit's merge now marks 0 of 17.

## Phase 3 results (new-application project plan)

What was built
- Section workers answer with `project-plan-section-model-packet`: `sections` of typed blocks (`prose`, `heading`, `list`,
  `code`, `rows` with a `row_kind`, `steps`, generic `table`) with every value a string. The prompt lists the row kinds
  and fields each worker's sections use and forbids Markdown syntax in values.
- The outline is a JSON packet (`project-plan-outline-packet`: stack, components, steps with owns/depends_on, decisions,
  restrictions, tests, requirement map). Workers read `outline.json`; the traceability join reads the requirement map
  as data instead of parsing Markdown arrows.
- The driver renders each packet to the section Markdown file the rest of the pipeline still reads (and a
  `.model.json` of typed sections), assembles the Markdown plan as before, and also assembles the model
  (`assemble-model`): section 13 is built as typed `traceability` rows. The model is stored beside the plan as
  `PROJECT_PLAN.model.json` only when its words equal the narrative's; `load_model` ignores a stale sidecar. The plan
  JSON itself is unchanged, so review agents do not read two descriptions and the approval hash is unaffected.
- Updated-plan writers and the merge both read that sidecar (`UNCLE_PLAN_JSON`), so the ids a writer sees are the ids
  the merge applies.
- `WORKFLOW_PLAN_BLOCKS=0` keeps the Markdown-body packets. Any failure still falls back to the single-pass plan.

Changes the real plans forced
- Restriction rows have a `binding` (runner/config binding) field and `Feasibility evidence` before `Phase`; component
  rows have `interface`; long header variants map by prefix.
- Steps written on one line ending in `Owns: ...` (noinit's form) import as typed steps.

Dry run: each saved plan's sections were rebuilt as worker block packets and run through the new render and assembly.
calculator-local and noinit assemble to 18 sections and pass `plan_context.py plan-unprotected`; the remaining word
differences are tables whose extra columns the flat block form cannot carry, and section 13 rebuilt from limited data.

Not done: the change workflow's plan authoring (one agent writing Markdown), the single-pass project-plan fallback,
and the traceability fallback worker's use of typed context. These remain Markdown until phase 4 and 5.

## noinit, second run (phase 3 on hosted Claude)

The run completed (about 426 s of agent time from the first log to the final audit). The block-mode project plan produced an
authored model with the same typed structure the Markdown import gives for the same plan (every row kind matches), stored
beside the plan. The updated-plan stage on that model: 19 writers, 52 ops (40 `set_fields`, 6 `set_step`, 2 `set_text`,
and inserts), 8 resolver groups all valid, nothing left out, no fallback.

Two of ten section workers had to be run again (about 70 s each, which made the project-plan stage 111 s):
- `behaviors` wrote an extra empty `rows` block. Empty blocks are now dropped.
- `closing` used the `change_impact` row kind for its risks table. A worker's schema now lists only the row kinds its sections
  use, and no `rows` or `steps` block at all when it has none; the prompt says so.

Also found: the design worker wrote a numbered data-flow list as a `steps` block, which collided with the implementation
steps' ids. Only the worker that writes section 12 may now write `steps`. A local model's grammar is static per packet kind,
so these limits are enforced by the prompt, not the grammar, on local runners.

## Later additions (still hosted-tested only by stubs)

- **Review findings as JSON.** The sealed synthesis prompt now carries the adversarial findings and the specialist corrections as
  JSON objects, not Markdown tables (`updated_plan_synthesis_prompt.py`).
- **Change plan as blocks (opt-in).** `WORKFLOW_CHANGE_PLAN_BLOCKS=1` asks the combined change-planning pass for `change_plan.sections`
  (typed blocks) instead of a `narrative`. `publish_change_planning_bundle.py` renders the narrative from them, stores
  `CHANGE_PLAN.model.json` beside `CHANGE_PLAN.json`, and validates the whole bundle before writing anything. Hosted runners only.
  The updated-change-plan writers already read that sidecar.
- **Agent view (opt-in).** `plan_model.py view PLAN.json OUT.json` writes the plan as an agent should read it: the model, the commands
  and the protected paths, no narrative. `WORKFLOW_AGENT_PLAN_VIEW=1` points the adversarial-review workers at it.
- The remaining Markdown-for-agents inventory and the order to convert it in are in [json-only-inventory.md](json-only-inventory.md).

## Performance round after the third and fourth noinit runs

Measured on noinit (368 s, hosted Claude): a call takes about 3 s plus its output tokens at roughly 110 per second, so time is saved
by splitting large outputs, removing serial hand-offs and not repeating work.

- **Step sandboxes** (`parallel_steps.py`): the eleven mirrors of the tree were made one after another before the first model call
  (about 16 s). They are now made together (`WORKFLOW_SANDBOX_JOBS`, default 8) and leave out driver state a step never reads
  (the performance trace was 21 MB by then). On a copy of noinit, 11 sandboxes took 25 s before and 8 s after.
- **Project-plan workers** (`project_plan_sections.py`): `behaviors` (55 s) and `tests` (53 s) were the longest calls. Behaviors is
  now section 6 alone with a new `handling` worker (8, 9, 11, manual checks); the test strategy (section 10) is written by `tests`
  (the test table) then `defects` (defect injections `DI-n`, obligations `O-n`, protected paths), joined in that order. A section
  may be shared by two workers; any other section written twice is still refused.
- **Updated plan, decide and edit in one pass** (`run_updated_plan_decide`, `run_updated_change_plan_decide`, on by default;
  `WORKFLOW_UPDATED_PLAN_DECIDE=0` restores the specialist round). The old stage did every finding twice: three "dispositions"
  specialists decided it and described the fix in prose, then a writer re-read the whole plan to turn that into ops. Now the
  writers read the review themselves and answer with their disposition and ops; the ownership, verification and scope specialists
  run beside them; one reconciler (a single call, in the background beside the resolvers) reads the writers' ops and the specialists'
  corrections and adds ops only for what no writer did. A reconciler op that touches a field a writer already changed is dropped, so
  the reconciler can add but not overwrite. Any failure of the specialists or the reconciler costs only the extra edits; a failure of the
  writers leaves nothing published and the old stage runs. Expected: about 32 s against 43 to 49 s, and about 3 to 4 dollars less per run.
  Not measured on a live run: whether skipping the specialists' input to the first draft costs plan quality; compare the two plans
  with the switch on and off.
- **Install guard** (`install_command.py`): `npm ci` becomes `npm install` in the green-check commands when there is no lockfile.
- A test (`checklist-lanes-test.py`) read the live noinit project's checklist and failed whenever that project was run again; it
  now uses a self-contained list of the same shape.

Not done: wiring `verify_prewarm.py` (installs and the browser download during implementation, about 18 s of a 31 s green check);
running resolvers as soon as their own writers finish; grouping findings by the ids they name; cache-friendly shared prompt prefixes.

## The implementation, test and verification loop (sixth noinit run)

Sequence seen: `IMPLEMENT -> TEST_REVIEW -> IMPLEMENT -> TEST_REVIEW`, every run. Cause, two parts:
1. The parallel implementation leaves a placeholder test report ("Implementation handoff: NOT RUN") because steps are told to run nothing.
   The test review therefore failed its coverage and results rows, and `VALIDATE_TEST_REVIEW` routed the run back to IMPLEMENT to run an
   agent that rewrote the report, then reviewed again. Both the review and the agent were wasted.
2. That route (`--mutation-evidence-gap`, and the handoff one) fired even when a driver command had FAILED: the mutation runner exited 1,
   the reviewers wrote "no mutation proof", and a failing command was treated as missing documentation.

Fixed: the driver records its own command results as the test report right after the green check (`test_report.py from-green`; a report
the implementation really wrote is kept, a driver-written one is refreshed each run), and both routes now require a green suite, so a failing
command goes to repair or waiver and never back through the implementation stage as a documentation gap.

Faster verification: a plan that declares no parallel groups now runs a build beside the unit tests (`auto_groups.py`; setup commands and
browser tests are never grouped, and `WORKFLOW_AUTO_VERIFY_GROUPS=0` turns it off), and `npx playwright install` checks the local CLI first
(`npx --no-install ... || npx ...`), skipping an eight-second registry check once the dependencies are installed.

Why the test review does not run beside the verification commands: its reviewers are read-only and their evidence is the commands' results,
so they cannot wait for them and would judge without. What can overlap is work that needs no results, such as writing the manual
checklist (about 23 s); that is not built.

Why implementation step 10 is the long pole: it writes the mutation runner (190 lines, about 8,300 output tokens, 53 s) against a list
file and sources that other steps write at the same moment and it is told not to read. It guesses their shape (the report lists the
assumptions), which costs reasoning time and is why the runner then fails.


## Project plan to about 30 s (seventh round)

From the fifth noinit run (stage 65 s: outline 28 s, then the longest worker 37 s):

- **Outline cut to about 1,000 tokens.** Decisions, restrictions, component responsibilities and step titles are a few words each; the
  decisions and restrictions workers write the full sentence, reason and fields.
- **Workers over 2,500 tokens split.** `invariants` + `guards` (section 7, I-1..I-40 and I-41 up), `design` (1 to 3) + `components`
  (4, 5), `handling` (8, 9) + `checks` (11), `restrictions` + `limits` (the first half of the outline's restrictions, rounded up, and the
  rest; a `limits` worker with nothing writes NONE and the driver drops it). A section or inventory several workers write is joined in
  `WORKERS` order. Sixteen workers.
- **Early workers.** `behaviors`, `handling` and `checks` need only the requirements, so they start with the outline
  (`PHASES[0]`). The second phase starts when the outline finishes, not when the first phase does; whatever is still running is
  collected after the second phase has started (`project_plan_section_settle`).
- Every worker's prompt carries the outline (without its schema fields) instead of telling it to read the file; one call fewer on
  each worker's path.

Estimated (not measured): outline ~12 s, longest worker ~20 s. A live noinit run is the test. Not done: a faster model for the
mechanical workers (`decisions`, `restrictions`, `limits`, `commands`, `closing`).

## Eighth round: measured 75 s, not 30 s

The run after the seventh round took 75 s (outline 24 s at 2.3k tokens, not 1k; `design` 46 s at 6.2k tokens, `restrictions` and
`limits` 35 s and 32 s at about 4.7k each, `steps` 30 s at 3.8k). Time followed output size again, so:

- `design` is three workers (`design` for section 1, `state` for 2, `domain` for 3); `steps` is two (`steps`, `sequence`: first
  half rounded up and the rest, joined into one `steps` block so a dependency can cross); the restriction inventory is three
  (`restrictions`, `limits`, `bounds`: thirds of the outline's list). A shared section may now have more than two writers
  (`WRITERS`); a part that says NONE is dropped. Twenty workers.
- The outline asks for decisions, restrictions and step titles in four words or fewer and responsibilities in three.
- Estimate (not measured): outline ~14 s, longest second-phase worker ~20 s, so about 35 s.

Beside it: the early checklist now starts when the verification commands start and, in an unattended run, is kept whatever the review
found (an attended run still writes it again after a failing review); `auto_groups.py` also runs the browser tests and the
defect-injection runner together; the install warm-up no longer takes prose words for packages (noinit: 40 of them, one invalid,
so nothing was cached) and checks names with `npm view` when a batch fails; the first group's step sandboxes are made while the
updated plan is written (`parallel_steps.py prewarm`) and used only when the tree is unchanged.

## Eighth round: measured 70 s after the sixteen-worker split

Per worker, from the performance events of that run: the outline ended at 19 s but the second phase started at 25 s; `design` took
70 s (4,258 tokens), `invariants` 65 s (5,129), `tests` 64 s (4,025), then `defects`, `limits`, `components`, `restrictions`, `domain`
at about 2,300 to 3,000 tokens and 52 s. Time follows output; the models write far more than a prompt asks of them.

- **Outline-lite.** The outline is components (id, name, files), steps and the requirement map only (about 600 tokens, the model
  will write more). Decisions, restrictions and the test list left it; `decisions`, `restrictions`, `limits` and `bounds` now start
  with the outline from the requirements alone (`EARLY`), the restrictions in thirds of the requirements with their own id ranges
  (R-1.., R-20.., R-40..). Other workers no longer cite D- or R- ids.
- **Finer splits.** `design` (section 1), `state` (2), `domain` (3); `steps` + `sequence` (halves, joined into one list); twenty workers.
- **Length caps.** Every worker is told to keep to about 300 to 600 words (`WORD_CAP`), because the stage waits for the longest answer.
  This trades plan detail for time, and is the part to loosen if plans read thin.
- Also: the early checklist starts beside the verification commands and, in an unattended run, is kept whatever the review found;
  browser tests and the defect-injection runner run together; the install warm-up no longer takes prose words for packages (noinit:
  40 of them, one invalid, so nothing was cached); the first group's step sandboxes are made while the updated plan is written.
- Estimate, not measured: outline about 15 s, second phase about 20 s, so about 35 to 40 s.
