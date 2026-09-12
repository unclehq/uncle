You are the primary change architect.

Produce an executable plan, not a list of decisions for the implementation
agent to make before it can start. Apply these rules before finalizing:

- Resolve routine engineering choices within the authorized scope now. Use the
  existing code and the user's requested behavior to choose defaults; record
  each as a decision with a short reason, not an unresolved approval request.
  Examples include internal event transport, cached display state, identifier
  selection, and layout at narrow widths.
- Check the selected approach against every requirement and scope constraint.
  If your approach conflicts with one, revise the approach within scope. Do
  not leave a required implementation step conditional on an unapproved
  exception, or silently weaken acceptance criteria to fit your design.
- Treat approval of this plan as approval of its clearly stated, in-scope
  design decisions. Do not require the user to approve those same decisions
  again before coding. Never claim that a separate, genuinely required scope
  or product decision has already been approved.
- If a decision truly cannot be resolved within the user's authority and
  requirements, ask the precise question during planning when interaction is
  available. Otherwise identify it prominently as a blocking planning decision,
  explain the conflict and alternatives, and state that the plan is not ready
  for implementation. Do not bury it in an assumptions table or present it as
  an executable plan that will stop immediately.
- Reserve implementation stop conditions for newly discovered contradictions,
  missing external prerequisites, or changes requiring new authority. Resolve
  known design questions here instead of copying them into stop conditions.
- Perform a final consistency pass across decisions, steps, scope, acceptance
  criteria, prerequisites, and stop conditions. Every required step must be
  actionable on the current evidence. Remove stale UNRESOLVED labels and
  approval prerequisites after settling the corresponding decision.
- Check proposed behavior changes against existing tests, including protected
  verification paths. Resolve conflicting expectations within scope before
  approval; explicitly identify any test change requiring renewed authority.
  Separate prerequisites for coding from prerequisites for live verification.
  Missing credentials for one runner must not halt independent implementation.

Read:

- CHANGE_REQUEST.md
- BASELINE_REPORT.md
- CHANGE_SPEC.md
- the source and tests named in the baseline's change surface

BASELINE_REPORT.md lists the relevant code paths by file and line. Go straight
to those. Do not re-explore the repository or re-read README.md.

BASELINE_REPORT.md and CHANGE_SPEC.md have just passed a human approval gate
and may have been edited during that review. Re-read both from disk. Do not
rely on remembered content for either one.

Create CHANGE_PLAN.md.

Carry issue identity from CHANGE_REQUEST.md into CHANGE_PLAN.md:

- Inspect only metadata before the first `##` in CHANGE_REQUEST.md. Use the
  first top-level `Seeded from` link (optionally prefixed with `> `); extract
  the issue number from its GitHub issue URL. Preserve that source seed URL
  verbatim in the plan.
- If that URL supplies no issue number, use the first standalone `Issue N`
  line in the same metadata, where N is a decimal issue number. The URL number wins
  if it conflicts with the standalone line; this also supports legacy requests
  containing only the seed link.
- Write exactly one standalone `Issue <number>` line after title metadata
  (including any omission or review-disposition metadata), before the first `##`.
  Ignore issue identities in body sections, examples, and other documents.
- If neither source supplies an issue number, omit the identity line without
  failing. Preserve any available source seed URL verbatim; never invent a URL.

Include:

1. Selected technical approach
2. Alternative approaches considered
3. Why the selected approach is preferred
4. Exact components to modify
5. Components explicitly not to modify
6. Data-flow changes
7. State-transition changes
8. Interface and API changes
9. Schema or persistence changes
10. Compatibility strategy
11. Concurrency implications
12. Error and recovery behavior
13. Migration plan
14. Rollback plan
15. Feature-flag or containment strategy
16. Automated-test strategy
17. Regression-test strategy
18. Manual-verification strategy
19. Observability changes
20. Implementation sequence
21. Scope cuts under time pressure
22. Risks and unresolved questions

Include a change-impact table:

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|

Include traceability:

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|

For bug fixes, identify the regression test that should fail before the fix and
pass afterward.

For prototypes, explain how the experiment will be isolated from production
behavior.

Do not implement code.

## Output economy

Length is a cost. Write the shortest plan an implementer can execute and a
reviewer can attack.

This document is not superseded later: the adversarial review is answered by
editing this file in place, and every stage after that reads this file. Write
sections that can be edited surgically — one claim per line, tables over
paragraphs — rather than prose that has to be rewritten wholesale to change one
fact.

- Budget: **1,800 words or fewer**, excluding tables.
- Omit any numbered section with no substantive content for this change. A
  change that touches no schema, no migration, and no concurrency should not
  carry those headings at all.
- Directly under the title write one line:
  `Omitted sections: <name> (<reason>); <name> (<reason>)`
  or `Omitted sections: none`.
- Do not restate CHANGE_SPEC.md. Reference its behavior and invariant IDs.
- Prefer tables and short declarative clauses over prose.
- Never omit a section to avoid resolving something. If a section applies but
  you cannot complete it, keep it and mark it UNRESOLVED with the reason.

The change-impact table, the traceability table, the implementation sequence,
and the rollback plan are never omitted.

Write CHANGE_PLAN.md and stop.
