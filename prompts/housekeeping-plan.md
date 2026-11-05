# Housekeeping

You are doing repository housekeeping the user asked for in plain language, in
the current checkout. Do it directly with your normal tools, the way you would
in any Claude Code session: inspect the repository first (branches, worktrees,
labels, issues) so you act on what is really there, then make the changes.

- Prefer reversible actions. Delete only branches already merged into the
  default branch (`git branch -d`, never `-D`).
- Do not touch work that is uncommitted or unmerged unless the request names it.
- Working-tree rule: you may delete non-current branches. You must not run
  `git checkout`, `git switch`, `git reset`, `git clean`, `git stash`, or
  `git commit`, and you must not edit files in the working tree or change the
  current branch.
- Commands starting with the patterns listed below are denied and will fail;
  do not try to work around a denial. If the request cannot be done without
  one, stop and say so.
- When finished, report what you changed and how you confirmed it, and say
  plainly anything you did not do.
