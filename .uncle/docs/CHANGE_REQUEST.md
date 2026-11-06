# Change Request: Uncle must create and push a PR when appropriate

## Change Type
Bug fix (regression)

## Summary
Uncle no longer opens a pull request and pushes its branch after a finished build. It should create the PR and push the branch whenever doing so is appropriate.

## Motivation
The operator reports that Uncle "doesn't make PRs anymore for some reason". PR publication used to work (added in commit 882a671 "now makes PRs for a change request"). Recent changes, such as the 'send all errors to stderr' change (PR #175) and the Windows curses fix, may have affected it, but the cause has not been confirmed.

## Observed Current Behavior
After a change or build completes, no PR is created and nothing is pushed. Known paths in scripts/lib/change-pr.sh (`change_pr_complete`) that return without a PR: handoff disabled or unattended ("PR handoff disabled or unattended; no PR was created" / "leaving the issue open"), a failing `assert_tree_matches_attested` check, and a non-READY audit verdict needing an override. The actual cause in the operator's runs is not yet determined.

## Desired Behavior
When a run finishes and publishing is appropriate (work is complete, tree matches the attested tree, audit is READY or explicitly overridden by a person, a GitHub remote is available), Uncle creates the PR with `gh` and pushes the branch. When it is not appropriate, Uncle says clearly why no PR was made. Unattended mode behavior stays as designed (draft PR when the audit is not READY).

## Reproduction
Run a change (for example via github_issue or create_change) to completion in the current checkout and observe that no branch is pushed and no PR is opened. First step for the implementer: reproduce and identify which path in change_pr_complete / change_pr_publish skips publication, including whether the driver is calling it at all and whether recent commits (a6c05c2, 355822d, 45d8feb) broke it.

## Constraints
Do not weaken the attested-tree check, audit gating, or human override rules. Never force-push. Keep Bash 3.2 compatibility in the driver libraries. Add a regression test where practical.

## Known Relevant Files
- scripts/lib/change-pr.sh
- scripts/change-workflow.sh (calls change_pr_complete around lines 4980-5000)
- scripts/lib/home_agent_session.py
- scripts/lib/gate_answer.py
- scripts/tests/supervisor-test.py
- GITHUB_INTEGRATION.md

## Out of Scope
Redesigning the publication dialogs, changing audit or approval gates, and unrelated cleanup.

## Success Criteria
- A completed run in a repository with a GitHub remote pushes its branch and opens a PR.
- When no PR is made, the reason is reported to the operator.
- A regression test covers the fixed path.
- Existing verification commands show no regressions.