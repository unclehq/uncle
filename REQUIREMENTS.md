## Summary
A web-based calculator app featuring a groovy, retro 1970s-style background (bold colors, swirling patterns, funky typography accents).

## Problem
Users want a fun, visually distinctive calculator instead of a plain utilitarian one.

## Scope
A single-page web app with a functional basic calculator (arithmetic operations) styled with a groovy retro background and theme.

## Non-goals
No scientific/advanced calculator functions, no user accounts, no persistence beyond the current session.

## Functional requirements
- Support addition, subtraction, multiplication, division.
- Support decimal numbers and clear/reset.
- Display current input and result.

## User-visible behavior
User clicks number and operator buttons to build an expression, presses equals to see the result, and can clear the display. The background and UI use a groovy retro aesthetic (warm colors, swirls, funky fonts).

## Domain rules and invariants
Division by zero shows an error state instead of crashing. Only valid numeric/operator sequences are accepted.

## Data and state
Calculator state (current input, pending operation, result) is held client-side only; no backend storage.

## Interfaces
Browser-based UI only; no external APIs.

## Constraints
Must run as a static/client-side web app.

## Failure behavior
Invalid operations (e.g., divide by zero) display a clear error message rather than crashing the app.

## Verification
Manually test all four operations, decimal input, clear function, and divide-by-zero handling in a browser.

## Definition of done
A working calculator web app is deployed/runnable locally with a groovy retro-styled background and all functional requirements met.

## Open questions
None.