# MC-8 evidence

## Check ID
MC-8

## Action actually performed
Ran `grep -rn '\[failed\]' uncle_tui.py` on the final modified source file at `/Users/brianwoods/src/unclehq/uncle-issue-89/uncle_tui.py`.

## Expected result
Zero lines returned. All `[failed]` suffix logic removed from `uncle_tui.py`.

## Actual result
One match at `uncle_tui.py:5478`: `title += " [failed]"`. The `[failed]` suffix logic was not removed.

## Evidence
```
$ grep -rn '\[failed\]' uncle_tui.py
uncle_tui.py:5478:                title += " [failed]"
$ echo "EXIT: $?"
EXIT: 0
```
Exit code 0 (match found), one line matched.

## Status
FAIL

## Defect reference
Line 5478 of `uncle_tui.py` still contains `title += " [failed]"`. This contradicts CHANGE_PLAN.md step 2 ("Delete `[failed]` suffix logic entirely") and violates the REMOVE behavior classification for AC-8 / I-7. The per-worker dot indicator logic may have been added (new tests pass), but the old `[failed]` suffix string was not deleted, so both the old suffix and new dots appear on rollup lines with any failed worker.
