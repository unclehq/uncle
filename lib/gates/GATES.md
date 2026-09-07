# GATES.md — Project Plan Output Gates

These rules apply whenever a stage produces a plan. Every gate must pass before output is written. If a gate fails, fix the plan and re-check; do not emit a failing plan.

The stage's prompt owns the plan: the target file, the sections and their order, the content. These gates govern quality only. Where a gate and the stage's prompt disagree about the file or the structure, the stage's prompt wins.

## Gate 0 — Output target

- Write exactly the file the stage's prompt names, at exactly that path. Do not rename it, do not add a suffix, do not write a second copy elsewhere.
- Print nothing to the conversation except the path of the file written, on one line.
- No preamble, no closing summary, no "here is your plan."

## Gate 1 — Audience

Write for a senior engineer who already knows the domain and is about to approve or reject the plan. Do not explain what tools are, why testing matters, or what the project is for beyond the one-sentence goal.

## Gate 2 — Structure

- Use the sections the stage's prompt names, in that order, with those exact headings. Add nothing, drop nothing, reorder nothing.
- When the prompt names no sections, use `# <Plan title>` then `## Goal`, `## Constraints`, `## Steps`, `## Risks`, `## Done when` — in that order.
- Rejected either way: intro paragraphs, "Overview," "Background," "Next steps," "Conclusion," stakeholder tables, timelines with weeks unless the user asked for dates.

## Gate 3 — Concreteness and length

- Every step names something concrete: a file path, a command, a function, a schema, a number.
- The output rules own the length caps. When over a cap, delete the lowest-information item first. Never compress by merging two steps into one vague step.

## Gate 4 — Language

- Plain declarative sentences. Active voice. Imperative mood in steps ("Add `retry()` to `client.py`").
- No adjectives that don't change what an engineer would do.

Banned (hard fail if any appear): leverage, robust, seamless, seamlessly, scalable, scalability, streamline, holistic, best-in-class, world-class, ecosystem, synergy, synergize, empower, cutting-edge, state-of-the-art, comprehensive, innovative, optimize (unless a metric is named), enhance, facilitate, utilize, "ensure that", "it is important to note", "in order to", "going forward", "moving forward", "at the end of the day", "stakeholders" (name the people or teams instead), "solution" (name the thing), "robustness", "best practices".

## Gate 5 — Self-check pass (run before writing the file)

After drafting, rewrite once with only these instructions:

1. Delete any sentence that does not tell an engineer what to do or what to check.
2. Replace any category word ("the service," "the data layer") with the specific name.
3. Scan for every banned term; replace or delete.
4. Confirm the target file and the section list match the stage's prompt exactly.

Only the rewritten version is written to the file.
