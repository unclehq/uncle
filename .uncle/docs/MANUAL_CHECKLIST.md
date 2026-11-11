# Manual checklist

## PR body integration

### MC-901
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In an isolated harness, exercise the body-assembly path in scripts/lib/change-pr.sh through capture of the prepared body, with publication and external mutations mocked. Use a bound origin owner/repo#123. Check READY with valid passing acceptance tables, NOT_READY with a matching override, READY_WITH_NON_BLOCKING_ISSUES with required BLOCKED row AC-2, and READY with only audit finding AR-3 stating the issue stays open. Repeat without a bound origin. Use the application's emitted audit format rather than substituting the helper test's Verdict line.
- Expected result: The finished READY case ends with Closes owner/repo#123. Each unfinished case contains Refs owner/repo#123 and a nonempty Still open list identifying the applicable reasons and blocker IDs, without a closing trailer. The attestation precedes the trailer. The originless case adds neither trailer nor Still open section.
- Evidence to capture: Input audit and acceptance fixtures, mocked boundary details, and captured complete bodies for each case.
- Actual result: 
- Status: NOT RUN
