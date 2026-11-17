# Manual checklist

## Review-incomplete classification

### MC-901
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Trace implementation_incomplete_choice in scripts/lib/implementation-gates.sh and both callers in scripts/change-workflow.sh for unattended cases with: all acceptance rows delivered and a missing review; all acceptance rows delivered and a rejected review; a missing acceptance row together with a missing review. Check the completion-text matching and follow each return value through the caller.
- Expected result: Under AC-4 and SI-4, only review-delivery gaps with all acceptance rows delivered produce 'review incomplete' and driver exit status 3. Missing acceptance rows retain their existing incomplete behavior and cannot be classified as review incomplete.
- Evidence to capture: For each case, record the completion input, matching branch, gate return value, driver exit status, and source locations.
- Actual result: 
- Status: NOT RUN
