# Manual checklist

### MC-200
- Exclusive resources: none
- Depends on: none
- Exact action: In an isolated no-footprint workflow with a READY result, proceed to the publication consent prompt and decline publication.
- Expected result: The prompt requires an explicit decision, and declining leaves the completed work available locally without publishing or treating that decision as a verification failure.
- Actual result: 
- Status: NOT RUN

### MC-400
- Exclusive resources: none
- Depends on: none
- Exact action: In an interactive default-mode workflow, with --no-footprint omitted and UNCLE_NO_FOOTPRINT unset, complete the required verification and approvals, then decline the optional publication offer. Observe the terminal's completion status and subsequent prompts.
- Expected result: Declining publication preserves successful completion and does not trigger publication or require repeating completed verification or approvals.
- Actual result: 
- Status: NOT RUN
