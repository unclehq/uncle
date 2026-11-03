# Defects

## D-1

- **Status:** FAIL
- **Evidence:** D-1 symlink target clobbered
- **Expected result:** per checklist MC-206
- **Actual result:** Whitespace-only prompts (driver). Symlink and directory prompt; decline leaves link, target and dir intact. After 'y' on symlink: CHANGE_REQUEST.md stays a symlink but its target hash CHANGED (write followed the link). Expected target not clobbered. Filed D-1.

## MC-301

- **Status:** NOT RUN
- **Evidence:** see finding
- **Expected result:** per checklist MC-301
- **Actual result:** Depends on MC-300, which is not in the checklist (README: NOT DECLARED). Equivalent action covered by MC-102 PASS but this ID is not asserted.

## MC-303

- **Status:** NOT RUN
- **Evidence:** see finding
- **Expected result:** per checklist MC-303
- **Actual result:** Depends on MC-302, absent from the checklist. Equivalent covered by MC-203 PASS but this ID is not asserted.

## MC-404

- **Status:** NOT RUN
- **Evidence:** see finding
- **Expected result:** per checklist MC-404
- **Actual result:** `uncle --change-request` stdin import not executed; not touched by the diff (scripts/from-issue.sh only). Settled by running that command against an existing file.
