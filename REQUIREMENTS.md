# Requirements

> **This file is the input for the new-application workflow.**
>
> Every stage of `./scripts/stagegate.sh` reads `REQUIREMENTS.md` as the
> requirements source. Fill in the [Project brief](#project-brief) below, then
> run the driver. Keep the brief unambiguous and let it carry the requirements.

---

# Project brief

> Replace this entire section with the project. Everything below the heading is
> read as requirements by every agent in the pipeline. Delete the guidance in
> each subsection — leaving it in produces requirements about the template.
>
> Be specific and testable. Vague lines here become ambiguities in
> `REQUIREMENTS_INTERPRETATION.md`, findings in `ADVERSARIAL_REVIEW.md`, and
> guesses in the implementation.

## Summary

One or two sentences: what is being built, and for whom.

## Problem

What is wrong today, and what changes for the user once this exists.

## Scope

What this project covers. Keep it to what must ship.

## Non-goals

What this project explicitly does not do. Name the tempting adjacent features
you are refusing — this is the strongest single lever on scope creep, and the
review stage will cut against it.

## Functional requirements

Number them. Downstream artifacts reference these identifiers, so stable IDs
matter more than prose.

| ID | Requirement | Priority |
|---|---|---|
| R-001 | | Must |
| R-002 | | Should |
| R-003 | | Could |

## User-visible behavior

For each behavior: the trigger, the observable result, and what the user sees
when it fails. "Rejects invalid input" is not a requirement; "rejects a
negative quantity with a 400 and the field name" is.

| ID | Trigger | Expected result | On failure |
|---|---|---|---|
| B-001 | | | |

## Domain rules and invariants

Conditions that must hold at all times, not steps. State each so a test could
falsify it.

| ID | Invariant | Consequence if violated |
|---|---|---|
| I-001 | | |

## Data and state

What the authoritative state is, where it lives, what may hold a cached copy,
and what survives a restart.

## Interfaces

APIs, CLI surface, UI entry points, message formats, external services. Include
the contracts you already control; say so where the shape is open.

## Constraints

Language, runtime, frameworks, libraries that are required or forbidden,
deployment target, performance or size budgets, compatibility that must not
break.

## Failure behavior

What must happen on invalid input, unavailable dependencies, partial writes,
concurrent access, and restart mid-operation. Say which failures must be
visible to the user and which are handled silently.

## Verification

How correctness will be demonstrated: test frameworks, the commands the
implementation stage should run (formatter, type checker, tests, lint, build,
startup smoke), and anything only checkable by hand.

## Definition of done

The concrete conditions under which this is finished. The final audit checks
claims against this list.

## Open questions

Anything genuinely undecided. Listing it here is better than letting an agent
resolve it silently — these surface as assumptions in stage 1 and as findings
in stage 3.
