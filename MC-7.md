# MC-7 Evidence

**Note:** Intended path `/var/folders/wx/9by5vyzd4lggvy2gp25fmtzm0000gq/T//uncle-checklist-workers.Gal7rR/MC-7.md` was unreachable due to tool permission rules. File placed in workspace root instead.

## Check ID
MC-7

## Action actually performed
Code inspection of `parent_stage()` at `uncle_tui.py:185-195` and the grouping logic at lines 5306-5310 and title rendering at line 5370.

## Expected result
Raw stage is used as fallback when `parent_stage(stage)` returns `""`; no crash or empty title.

## Actual result

**`parent_stage()` inspection (lines 185-195):**
No pattern matches `""`, so it falls through to `return stage` (line 195), returning `""`.

**Grouping logic (lines 5308-5310):**
```
stage = row.get("stage", "")
parent = parent_stage(stage)
group = groups.setdefault(parent, ...)
```
`parent` is used directly as the group key — **no fallback to raw stage** when `parent` is `""`.

**Title rendering (line 5370):**
```
title = ("> " if active else "") + stage
```
`stage` here is the group key (the `parent` value). When parent is `""`, title is `""` — an empty heading with no name suffix.

**Active stage handling (lines 5344-5347):**
Same pattern — no fallback.

**No fallback logic exists anywhere in `_session_panel_lines()`** — no `or stage` or conditional to substitute the raw stage when parent is empty string.

**Crash behavior:** No crash; an empty-string key is a valid dict key and produces a line entry with an empty title.

## Evidence
- `uncle_tui.py:185-195` — `parent_stage("")` returns `""`
- `uncle_tui.py:5308-5310` — grouping uses `parent` directly as key, no fallback
- `uncle_tui.py:5370` — title uses group key (parent) with no fallback
- `uncle_tui.py:5344-5347` — same pattern for active stages

## Status: FAIL

## Defect reference
The grouping logic at `uncle_tui.py:5309-5310` does not implement the fallback specified in CHANGE_SPEC.md §9 ("Group whose parent name is an empty string: use raw stage as fallback"). The line `parent = parent_stage(stage)` should include a fallback such as `parent = parent_stage(stage) or stage` to prevent an empty-string group key and empty title.
