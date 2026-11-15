# Defects

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** MANUAL_CHECKLIST.json row MC-400; scripts/lib/change-pr.sh (change_pr_publish, lines ~239-276). No terminal observation of the decline path.
- **Expected result:** Declining publication preserves successful completion and does not trigger publication or require repeating completed verification or approvals.
- **Actual result:** Not observed. The row needs a complete interactive default-mode run (--no-footprint omitted, UNCLE_NO_FOOTPRINT unset) with human-gated approvals and a person declining the optional publication offer at the terminal. A worker cannot supply that. The code shows an interactive publish consent path (change_pr_publish 1) but no run was observed, so no pass or fail is claimed.
