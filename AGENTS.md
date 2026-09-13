# Test fixture signing

All new or modified test fixtures must explicitly disable Git commit signing.
Never inherit the user's signing configuration or invoke their GPG agent,
pinentry, or private signing key from an automated test.

- Pass `--no-gpg-sign` to fixture `git commit` and `git commit-tree` commands.
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
