
# Project brief

Issue 115

> Seeded from [unclehq/uncle#115](https://github.com/unclehq/uncle/issues/115).
> Replace the placeholder guidance below with specifics before running the driver.

## Summary

Refresh Claude, Codex, and Kimi model catalogs at Uncle startup

## Problem

## Problem

Uncle can start with stale model choices for Claude, Codex, and Kimi. Users must enter configuration or otherwise manually refresh before newly available models appear.

## Requested behavior

On Uncle startup, refresh the available model catalogs for:

- Claude
- Codex
- Kimi

The refreshed lists should feed the normal model pickers and stage configuration UI before a workflow is launched.

## Constraints

- Refresh failures must be non-fatal: retain the last known catalog and surface a concise diagnostic.
- Do not require a user to open configuration solely to refresh models.
- Avoid startup delays where a runner/provider is not configured or unavailable; use bounded timeouts and skip unavailable providers.
- Preserve configured model selections even when a transient refresh fails.

## Scope

What this project covers. Keep it to what must ship.

## Non-goals

What this project explicitly does not do.

## Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| R-001 | | Must |
| R-002 | | Should |
| R-003 | | Could |

## User-visible behavior

| ID | Trigger | Expected result | On failure |
|---|---|---|---|
| B-001 | | | |

## Domain rules and invariants

| ID | Invariant | Consequence if violated |
|---|---|---|
| I-001 | | |

## Data and state

What the authoritative state is, where it lives, what may hold a cached copy,
and what survives a restart.

## Interfaces

APIs, CLI surface, UI entry points, message formats, external services.

## Constraints

Language, runtime, frameworks, libraries, deployment target, budgets,
compatibility that must not break.

## Failure behavior

What must happen on invalid input, unavailable dependencies, partial writes,
concurrent access, and restart mid-operation.

## Verification

How correctness will be demonstrated: test frameworks, commands, and anything
only checkable by hand.

## Definition of done

The concrete conditions under which this is finished.

## Open questions

Anything genuinely undecided.
