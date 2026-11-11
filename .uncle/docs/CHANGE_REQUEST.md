# Change Request

Issue 254

Seeded from [unclehq/uncle#254](https://github.com/unclehq/uncle/issues/254).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

PRs close their issue even over a NOT_READY audit or BLOCKED acceptance items: #236 and #235 were closed with their fixes undone

## Motivation

## Summary

Every PR that Uncle publishes for an issue ends with `Closes owner/repo#N`. This holds when the final audit says NOT_READY, when the publish went through an audit override, and when every acceptance item is BLOCKED. Merging such a PR closes the issue even though nothing was fixed.

That is how both preview-link follow-ups were closed with their work undone:

| Issue | Closed by | What the PR's own records say |
|---|---|---|
| #236 (release must allow the signed-link call) | PR #237, merged 2026-11-10 (`2c956a6`) | Body: "Published over a **NOT_READY** audit verdict", "audit result fail; NOT_READY; the override is recorded but does not release". `IMPLEMENTATION_NOTES.md`: "AC-1 \| BLOCKED \| No grant added; release definition not in repo". AC-1 to AC-6 are all BLOCKED. The body still ends `Closes unclehq/uncle#236`. |
| #235 (preview link never worked end to end) | PR #241, merged 2026-11-10 (`8b1182b`) | `FINAL_AUDIT.md` FA-005: "Issue 235 is not closed by this change alone." FA-012: the live checks are "BLOCKED and have no waiver". The verdict was READY_WITH_NON_BLOCKING_ISSUES, and the body still ends `Closes unclehq/uncle#235`. |

A preview link has still never worked for a hosted build (#251), but the issues tracking it read as done.

## How it happens

1. At publish, `change-pr.sh` builds the PR body. It adds a warning banner for a failing audit (`:1785-1796`), a note for unattended waivers (`:1797-1803`) and a line for an overridden verdict (`:1804-1808`).
2. Then, whatever the verdict, it appends `Closes <origin>` whenever the run has a bound issue (`scripts/lib/change-pr.sh:1823-1825`).
3. A PR published over a failing audit or an override is opened as a draft (`:1882`). A draft still carries `Closes`, so marking it ready and merging it closes the issue.
4. `scripts/README.md:405-407` documents this: the PR "includes `Closes owner/repo#issue` for an eligible bound origin". Eligibility depends on the origin, never on the verdict.

## Code paths (main `b27e23c`)

Blame is `git blame`.

| Where | What it does | Last changed in |
|---|---|---|
| `scripts/lib/change-pr.sh:1823-1825` | `if j['origin']: body += '\nCloses ' + origin[0] + '#' + origin[1]` with no check of the verdict, override or BLOCKED acceptance rows. | `57312a8` 2026-09-10 |
| `scripts/lib/change-pr.sh:1785-1808` | Banners for a failing audit, waived findings and an overridden verdict. None of them removes the `Closes` line. | `369ac2a` 2026-09-17, `22f2909` 2026-10-26, `29eb66b` 2026-09-13, `adfb2ad` 2026-11-09 ("Always publish a draft PR over a NOT_READY audit, in every mode") |
| `scripts/lib/change-pr.sh:1882` | Draft when `release_skipped` or an override is recorded. | |
| `scripts/lib/attestation.py:323-326` | When re-reading a body, separates the trailing `Closes` lines out as a trailer. A `Refs` line would need the same handling. | |
| `scripts/README.md:405-407` | Documents `Closes` for "an eligible bound origin". | |

## Fix

1. **Write `Closes` only for finished work.** Append `Closes <origin>` only when all of these hold:
   - The verdict is READY or READY_WITH_NON_BLOCKING_ISSUES.
   - No override is recorded and `release_skipped` is unset.
   - No required acceptance row (`IMPLEMENTATION_NOTES` "Acceptance delivery" or `VERIFICATION_REPORT` "Acceptance gate") is BLOCKED.
2. **Otherwise write `Refs <origin>`,** followed by a short "Still open" list: the BLOCKED acceptance IDs, and any FINAL_AUDIT finding that says the issue stays open.
3. Update `scripts/README.md:405-407` to say when each line is used.

## Tests

- A PR journal with a NOT_READY verdict and an override record gives a body with `Refs`, not `Closes`.
- READY_WITH_NON_BLOCKING_ISSUES plus one required acceptance row BLOCKED gives `Refs` and a "Still open" list naming that row.
- READY with nothing blocked still gives `Closes`, unchanged.
- `attestation.py` still strips both `Closes` and `Refs` trailers when re-reading a body.

## Checks after the fix

1. Publish an unattended run whose acceptance rows are all BLOCKED. The PR body says `Refs #N` and lists them, and merging it leaves the issue open.
2. Reopen #235 and #236, or link them from their replacement, so the preview work is tracked as open.

## Related

#235, #236, #251 (the preview work they were meant to track); PR #237, PR #241.

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
