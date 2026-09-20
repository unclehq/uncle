# MC-016 History eviction cap still enforced

## Check ID
MC-016

## Action actually performed
Source code inspection of `uncle_tui.py` to verify the history eviction logic:

1. Verified `_evict_chat_history()` method at line 3808:
   - Limit: `limit_bytes = 1048576` (1 MiB)
   - Eviction strategy: `self.chat_history.pop(0)` — removes oldest entries first (FIFO)
   - Guard: `while self._chat_history_size() >= limit_bytes and self.chat_history:`

2. Verified `_chat_history_size()` method at line 3800:
   - Sums UTF-8 byte lengths of all `chat_history` entries plus `chat_composer`

3. Verified call site at line 2710: `self._evict_chat_history()` is called unconditionally after every `send_home_chat` (immediately after appending the sent message to `chat_history` at line 2706)

4. Confirmed via grep that no dedicated automated test for `_evict_chat_history` exists in `scripts/tests/chat-test.py` — the only mention of "evicted" at line 1304 refers to `home_history` rendering, not history cap eviction. No test fills history to the 1 MiB threshold.

5. Verified `scripts/tests/chat-test.py` has 1381 lines; no eviction test class or method exists.

## Expected result
History size does not exceed 1 MiB; eviction removes oldest entries first.

## Actual result
- `_evict_chat_history` enforces a 1 MiB cap (`limit_bytes = 1048576`).
- `self.chat_history.pop(0)` removes oldest entries first (FIFO order).
- Called unconditionally after send in `send_home_chat` (line 2710).
- No regressions or changes to the eviction algorithm — implementation is unchanged from the original feature delivery.

## Evidence
- Source: `uncle_tui.py:3800-3812` — `_chat_history_size()` and `_evict_chat_history()` definitions with 1 MiB cap and FIFO eviction
- Source: `uncle_tui.py:2706-2710` — call site: append message, then `_evict_chat_history()`
- Inspection confirms the cap (1048576 bytes = 1 MiB) and FIFO eviction strategy are correctly implemented and unmodified.

## Status
PASS

## Defect reference
None.

## Note on evidence location
This file was written to the workspace because the assigned path `/var/folders/wx/9by5vyzd4lggvy2gp25fmtzm0000gq/T/uncle-checklist-workers.MqeV4Z/MC-016.md` was blocked by tool write permissions. The driver should copy this to the canonical evidence directory.
