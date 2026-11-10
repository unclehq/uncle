# Change spec — Issue 236

Omitted sections: Performance (none); Migration (none); Prototype isolation (n/a)

## 1. Change type
Bug fix / configuration (release definition, external to this repo).

## 2. Problem statement
The release's script publisher grants omit Daytona's signed preview-link call, so every hosted build's link request is refused and no `Preview:` line is printed. Step 1 of #235; replaces #209.

## 3. Current behavior
Baseline B-2.

## 4. Desired behavior
Release lists `daytona GET /sandbox/{sandboxId}/ports/{port}/signed-preview-url` with `require_approval` false; script asks `expiresInSeconds` <= 3600; a new release is published.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | ADD | Release publish with new grant | n/a | Publishes without "must match one publisher operation" refusal | Live: publish (AC-2) |
| SB-2 | MODIFY | Hosted build requests signed link | Refused (B-2) | Returns link; output has `Preview:` line | Live hosted build (AC-3) |
| SB-3 | PRESERVE | Hire installs the release | n/a | Installs with no Daytona-write approval prompt | Live install (AC-4) |
| SB-4 | PRESERVE | Existing Daytona grants, B-1 | Work | Unchanged | Diff review (AC-5) |
| SB-5 | ADD | Script ends links early (conditional) | n/a | If used, expire POST entry added likewise | Review (AC-6) |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | EXISTING | Each grant matches exactly one publisher operation | Release | Host | Publish succeeds |
| SI-2 | NEW | Signed-link request has `expiresInSeconds` <= 3600 | Build script | Script | Review/live |
| SI-3 | EXISTING | No grant removed or weakened | Release | Diff review | AC-5 |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Existing hires install without new approval (Daytona runs on host key).

## 8. Failure behavior
If the host rejects the entry, the publish fails with the match error; do not add `operation_id` guesses, report it.

## 10. Security
Only the one GET entry (and expire POST only if used). Do not add the plain `preview-url` call. `require_approval` false or omitted (host supports approval only for mail on script surface).

## 12. Rollback
Remove the entry and republish.

## 14. Non-goals
Changes to `host_preview.py`, `SKILL.md`, #235 later steps, plain preview-url grant.

## 15. Assumptions / unresolved
- UNRESOLVED: release definition and build script are outside this repo; access is required.
- Whether the script ends links early is unknown; expire entry is conditional.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | The release script publisher grants contain exactly one new entry: publisher daytona, method GET, path /sandbox/{sandboxId}/ports/{port}/signed-preview-url, require_approval false or omitted, with no operation_id. | Inspect the release definition diff. |
| AC-2 | Publishing the new release succeeds without the "must match one publisher operation" refusal. | Live: publish release; record output. |
| AC-3 | In a hosted build of a small web app, the signed-link call returns a link and output contains a `Preview:` line. | Live hosted build. |
| AC-4 | An existing hire installs the new release without a Daytona-write approval prompt. | Live install on an existing hire. |
| AC-5 | No existing grant is removed or altered, and the plain preview-url call is not added. | Inspect the diff. |
| AC-6 | The build script requests expiresInSeconds <= 3600; the expire POST grant is added if and only if the script ends links early. | Inspect the script and grants. |

