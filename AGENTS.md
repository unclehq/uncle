# Test fixture signing

Every project must be able to build, test, and complete without project commits.
Do not introduce commit or clean-working-tree prerequisites in generated plans
or reviews. Use file snapshots that include untracked files. Publishing is an
optional, separately approved action after completion.

All new or modified test fixtures must explicitly disable Git commit signing.
Never inherit the user's signing configuration or invoke their GPG agent,
pinentry, or private signing key from an automated test.

- Pass `--no-gpg-sign` to fixture `git commit` and `git commit-tree` commands.
- Disable tag signing with `tag.gpgsign=false` and `--no-sign` on fixture tags.
- For shared fixture helpers, also set `commit.gpgsign=false` in the temporary
  repository. Keep the explicit command flag so environment overrides cannot
  accidentally enable signing.
- Signing-specific tests must use mocks or isolated, disposable test keys and
  configuration. They must never access the user's real signing setup.
- When adding fixture helpers, verify them with inherited `commit.gpgsign=true`
  and a fake signer that records invocation and fails without prompting. Assert
  that ordinary fixture creation never invokes it.

Do not change the user's global Git configuration. Real workflow commits that
require signing must be handed to the user as a command to run explicitly;
automated code may verify the resulting commit afterward.

# Shell regression execution

For this repository, run shell suites with `bash scripts/run-shell-tests.sh`.
Use that command in generated baseline reports and verification command lists.
Do not generate or recommend a sequential `for t in scripts/tests/*-test.sh`
loop. The runner defaults to four workers, preserves per-suite output, and
aggregates failures; `WORKFLOW_VERIFY_JOBS` selects 1–8 workers. Do not run the
whole runner concurrently with individual suites it already includes.

# Python regression execution

The Python suites are `scripts/tests/<name>-test.py`, hyphenated, and the shell
runner does not run them. Run them with `bash scripts/run-python-tests.sh`: one
process per suite, four at once, the same output and exit-status conventions as
the shell runner. Do not use `python3 -m unittest discover -p "*-test.py"`: it
cannot import hyphenated file names and runs zero tests ("NO TESTS RAN"). A new
Python test named `<name>_test.py` (underscore) is never collected by anything.
The shell and Python runners are independent and may run at the same time; in a
baseline report, record both and declare them as one parallel group.
