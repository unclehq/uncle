# Output Rules

These rules apply to every markdown document a stage writes for a human to
read: the requirements interpretation, the baseline, the specs, the plans, the
notes, the test reports, the checklists, the verification reports, the audits.

They are appended to the prompt of every document-producing stage, so they
bind whatever agent runs it. They are about the shape of the document, not its
content: a stage's own prompt says what to write, and `lib/gates/GATES.md`
adds the quality gates a plan must pass.

If a rule fails, fix the document before writing it. Do not emit a document
that breaks one and note the breakage in the text.

## Rule 0 — Output target

- Write exactly the file the stage asked for, at exactly that path. Do not
  rename it, do not add a suffix, do not write a second copy elsewhere.
- When the stage explicitly requires multiple artifacts, write each named
  artifact and print its path on its own line. This exception also permits
  source and test edits explicitly required by implementation or repair stages.
- Print nothing to the conversation except the output artifact paths, one per
  line.
- No preamble, no closing summary, no "here is your document", no offer to
  continue.

## Rule 1 — Audience

Write for a senior engineer who already knows the domain and is about to
approve or reject this document at a gate.

- Do not explain what a tool is, why testing matters, or what the project is
  for beyond the single sentence that states the goal.
- Do not restate the prompt, the requirements, or a previous stage's document.
  Reference it by name and move on.

## Rule 2 — One claim per line, every claim checkable

- A statement about the code names the file, and the symbol or line when the
  claim is about one place: `scripts/stagegate.sh:402`.
- A statement about behavior names how it was observed: a command that was
  run, output that was read, a file that was inspected.
- A statement about what will happen is marked as a plan, not as a fact.

## Rule 3 — Say what is not known

Anything unverified is labeled, in place, with what would settle it:

```
ASSUMPTION: the resume PDF describes one role per page.
  Unverified: pdftoppm is not installed, so the file was not read.
  Settled by: installing poppler and re-running this stage.
```

An assumption presented as a finding is the failure this whole workflow exists
to prevent. A document with no assumptions section is claiming there were
none.

## Rule 4 — Structure is fixed, not invented

- Use the sections the stage's prompt names, in that order, with those exact
  headings. Add nothing, drop nothing, reorder nothing.
- When the prompt names no sections, use `## Summary`, `## Findings`,
  `## Assumptions`, `## Open questions` — in that order.
- Tables for anything enumerable: behaviors, invariants, findings,
  dispositions, checks. One row per item, one item per row.
- Preserve any driver-parsed section, columns, status vocabulary, and required
  rows exactly as specified by the stage. Never omit mandatory acceptance rows
  to meet a length limit; shorten surrounding prose first. If required rows
  alone exceed a section or document cap, retain them and report that exception
  in Open questions.
- Give every enumerated item a stable identifier (`B-3`, `I-2`, `AR-004`,
  `MC-7`) so later stages and humans can cite it.

## Rule 5 — Length

- Every stage document has a per-file byte and line budget, including
  implementation, repair, review, checklist, and acceptance reports. The appended
  budget lists the exact limits and enforcement mode. Budgets are advisory
  unless WORKFLOW_DOC_BUDGET_ENFORCE=1; ceilings are not targets to fill.
- Default budgets scale from authoritative REQUIREMENTS.md (new builds) or
  CHANGE_REQUEST.md (changes), with artifact-specific floors and ceilings listed
  in README.md. Plans, reports and reviews use twice the source byte size;
  interpretations, change specs and notes use source size. Line limits also scale
  within bounds, except interpretations and change specs retain 160 lines.
  Generated upstream artifacts never enlarge downstream budgets.
- Reference settled upstream obligations by file and ID instead of recataloging
  them. Preserve required acceptance rows and the complete executable plan.
  Update current rows during revisions and repairs, retaining IDs and dispositions;
  do not append a narrative for every attempt.
- `WORKFLOW_DOC_MAX_BYTES` and `WORKFLOW_DOC_MAX_LINES` override defaults.
  Artifact-specific variables (e.g. `WORKFLOW_DOC_MAX_BYTES_FINAL_AUDIT`)
  take precedence over global overrides. The appended budget is authoritative.
- Keep the execution contract complete in the named artifact. Cite existing logs
  and evidence by file and section; avoid copying transcripts and repeated rationale.
  Do not create a second summary artifact or move obligations out of the contract.
- Draft to the appended byte and line targets from the start. Reserve room for
  mandatory headings, rows, commands, and evidence before writing. Collect results
  before composing the report; batch independent reads and size measurements.
- If the document fits both ceilings, finish without a size-only rewrite. An
  advisory target is not a reason to compact. Reviewers return a concise final
  artifact directly; the driver measures it. Do not request filesystem writes
  solely to measure a read-only reviewer's response.
- For project-plan, change-plan, adversarial-review, updated-plan and
  updated-change-plan, test-review and manual-checklist (including base/delta),
  execute-checklist and final-audit, advisory budgets require compact-first drafting with ZERO
  size-only rewrite passes. Preserve complete artifacts even above the guide.
  This stage-specific policy takes precedence over the general rule below.
- Otherwise, only compact an oversized document, within the producing stage and using its
  model and context, at most twice total across its output documents. Leave
  compliant documents unchanged. The initial draft is not a pass;
  every later size-driven rewrite or trim counts, including a "final trim".
  Chat questions and steering do not reset the count. After the second pass,
  stop size-only edits, preserve the complete artifact, report final byte/line
  counts and any overage, and finish. Do not restart just to shrink it further.
  The driver preserves oversized artifacts and continues by default; an operator
  can increase the budget or set `WORKFLOW_DOC_BUDGET_ENFORCE=1` to block overruns.
- No sentence that survives having its adjectives removed unchanged in
  meaning. Cut it instead.

## Rule 6 — Banned

These add length without adding information, and their presence is a defect:

- "comprehensive", "robust", "seamless", "leverage", "utilize", "in order to",
  "it is important to note", "as mentioned above", "best practices",
  "production-ready", "enterprise-grade", "cutting-edge".
- Emoji, decorative rules, ASCII art, and horizontal separators between every
  section.
- Praise of the plan, the code, the requirements, or the reader.
- Any sentence whose subject is "we" and whose verb is a promise.

## Rule 7 — Diffs and code

- Quote code only when the document's claim depends on the exact text. Quote
  the smallest span that carries the claim, and cite its location.
- Never paste a whole file. Never paste a diff the driver already records.


## Proportional work and bounded inspection

For a small application or change, use the shortest report that satisfies every
required section, acceptance row, and evidence reference. Do not turn a simple
page into an extensive design exercise. Prefer one concise table over repeated
prose; reference earlier requirements by ID instead of restating them. Preserve
all actual requirements and blockers. Budgets are drafting targets, not a reason
to repeatedly rewrite an otherwise complete report.

Before inspection, collect the known input paths and read independent files in
one batch. Start with files named in the approved plan and current evidence.
Avoid recursive searches from the project root. Exclude `.uncle/workflow-history`,
`.git`, dependency directories, virtual environments, caches, and generated build
outputs from discovery unless a specific investigation requires them. Read named
hidden workflow files directly; never infer absence from a Glob result.

Reviewers should use current driver exit codes and linked test output before
requesting additional execution. Rerun only to resolve a concrete evidence gap,
changed input, or failure; state why. Inspect assertions and negative cases, but
do not duplicate passing driver checks merely to produce another passing record.
Batch independent inspections and report only findings, decisions, and required
acceptance evidence. Keep progress commentary out of the final report response.
