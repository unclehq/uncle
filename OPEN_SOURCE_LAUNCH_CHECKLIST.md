# Uncle public launch checklist

Reviewed September 13, 2026 against the local `uncle2/uncle` checkout and live
`unclehq/uncle` GitHub metadata. Public `main` was
`ac56740e3e8cb901163f63de06199bb227b4547e` (PR #42 merge).

**Recommendation: announce a public beta after the release blockers below are
closed.** Describe enforced checks and known limits precisely; do not promise
that independent AI review guarantees correct or production-safe code.

Unchecked boxes mean work or verification remains, not necessarily a confirmed
product defect. This was a source/documentation/repository review, not a fresh
end-to-end validation of every runner or platform. Local uncommitted fixes are
not evidence that the GitHub installer delivers them.

## Already present

- [x] Public repository with a clear issue-to-PR value proposition and logo.
- [x] MIT license, contributor guide, and Contributor Covenant with a contact.
- [x] Installers for Homebrew, Debian/Ubuntu, and Scoop.
- [x] A recent successful installer CI run on macOS, Ubuntu, and Windows.
- [x] Documentation for GitHub authentication, audited PR handoff, manual signing,
  and resuming a pending handoff.
- [x] Working evidence of the project building itself: PR #42 was merged.

Evidence: [repository](https://github.com/unclehq/uncle),
[installer run](https://github.com/unclehq/uncle/actions/runs/34747960404),
[PR #42](https://github.com/unclehq/uncle/pull/42), [LICENSE](LICENSE),
[GITHUB_INTEGRATION.md](GITHUB_INTEGRATION.md).
These do not substitute for validation of the eventual release commit.

## P0 — Release blockers

### Choose and validate one release candidate

- [ ] **Consolidate the intended fixes onto one reviewed release commit.** The
  uncle2 checkout has uncommitted installer, signing, parallel-execution, and UI
  changes plus new helper/test files. Verify every referenced helper is tracked
  and included in the package. Do not ship a mixture of uncle2, uncle3, and
  installed Homebrew code. Done when the release SHA and installed SHA match.
- [ ] **Run native installer CI on that exact commit.** Test fresh install,
  upgrade, launching outside the source checkout, and uninstall on each advertised
  platform. Include WSL separately if it remains advertised; a native Ubuntu job
  alone does not prove WSL behavior.
- [ ] **Verify the new pytest dependencies in the actual runtime.** Exercise
  Homebrew's private environment, Scoop's environment, and apt dependencies;
  prove `import pytest, xdist` and a small `pytest -n 2` example work using Uncle's
  selected Python. Do not imply an arbitrary terminal `python3` uses that same
  environment. Local installer unit tests are insufficient for this change.
- [ ] **Correct the Python support floor.** PREREQUISITES advertises Python 3.9+,
  while `scripts/lib/native_kimi.py` imports `tomllib` directly. Choose a tested
  minimum or add compatibility support, then align launchers, package metadata,
  prerequisites, and CI. Verify on the actual minimum version.

### Prevent the failures encountered during development

- [ ] **Prove automated fixtures never request the user's signing key.** Run all
  Git-creating fixtures with inherited signing enabled and a fake signer that
  fails/records calls. Ordinary fixture commits must explicitly disable signing;
  signing tests must use isolated disposable keys. Include newly added triage
  fixtures, not just the previously fixed ones. Keep this regression in CI.
- [ ] **Prove manual signing resumes without prompting for another commit.** Test
  cancel, no commit yet, valid user-signed commit, wrong tree/parent, signature
  verification failure, and restart after signing. Only the user runs the signing
  command. A failed verification must explain the problem, not loop silently.
- [ ] **Validate checklist output before execution.** Local
  `MANUAL_CHECKLIST.md` contains one reasoning sentence, and its scheduling file
  says no checks were found. Require actual check IDs, expected results, and valid
  dependencies; reject/repair malformed output before `execute-checklist`.
  A waived prior audit finding is not a fix for this generator/validation failure.
- [ ] **Make reviewer final-document capture reliable.** Add regressions for
  streamed reasoning, interleaved chat, truncated output, and a final answer that
  fails the document contract. Verify the saved checklist/audit is the intended
  artifact, rather than a reasoning fragment or unrelated chat response.
- [ ] **Finish audit-review recovery.** Test a NOT READY table with trailing prose,
  explicit per-finding decisions, restart with partial decisions, and invalidation
  after report edits. Retain the original verdict and evidence; no parser error
  should leave the user with only a stopped process and no actionable recovery.
- [ ] **Finish stale-audit/PR recovery.** When files change after audit, clearly
  route the user back to an audit of the new tree. Verify PR creation, push failure,
  ambiguous API outcome, signing resume, and re-entry after a created PR without
  creating duplicates. Distinguish build complete, handoff pending, and PR created.
- [ ] **Verify runner interruption behavior.** Test transport disconnects, timeout,
  cancellation, runner switches, and steering during a stage. Bound retries and
  stop descendants; retain draft chat, logs, and available usage totals. Check
  Cline's HTTP/2 recovery with the actual supported CLI version.

### Make verification trustworthy and understandable

- [ ] **Eliminate false-green command wrappers.** Audit generated command lists
  for `for …; done`, `… | tail`, and `…; echo $?; tail …` constructions that hide
  failures. Exercise a failing first test followed by a passing last test. Preserve
  each command's true status when summarizing output, not only recognized loops.
- [ ] **Publish one authoritative developer test entry point.** Include all Python
  and shell suites with reliable discovery and exit aggregation. pytest/xdist is
  now an installer dependency change, not a completed pytest migration: configure
  `*-test.py` discovery and remove import-time `unittest.main()` calls before
  advertising `python -m pytest scripts/tests` as the full test command.
- [ ] **Validate concurrency, not just worker configuration.** Run the new shell
  runner and syntax dispatcher on Windows and Unix; verify cancellation, isolated
  logs/fixtures, resource conflicts, and deterministic summaries. Keep dependent
  suites serial. Test both grouped and sequential driver entry paths.
- [ ] **Record a reproducible baseline timing breakdown.** Measure model analysis,
  commands, report writing, retries, and approval wait separately. Show when four
  workers actually run. Investigate duplicate checks and repeated baseline attempts
  before making speed claims; existing stage totals alone do not locate the delay.

### Demonstrate the advertised product

- [ ] **Record a clean issue-to-PR run on the release build.** Use a small public
  demo repository; include setup, plan approval, chat steering, verification,
  manual signing if enabled, and the final PR URL. Link the issue, PR, release SHA,
  elapsed time, provider/model, and measured/unknown cost in the evidence.
- [ ] **Record a new-application run.** Verify requirements entry, generated files,
  prerequisites, approvals, and successful execution of the app. State whether
  publication is supported for this path; current GitHub docs limit automated PR
  handoff to the change workflow.
- [ ] **Exercise the homepage and build UI on real terminals.** Check initial
  focus, menus, slash commands, file mentions, narrow terminals, multiline input,
  left-aligned responses, live steering, modal focus, and return to chat.
- [ ] **Resolve completion-popup behavior and destination.** The local UI says
  “star” but links to `/issues/new`, and the once-per-user marker suppressed the
  popup in a later run. Decide the intended CTA and frequency, then verify mouse
  hyperlink/keyboard behavior and the exit-versus-dialog timing on a real terminal.
- [ ] **Publish a runner support matrix backed by smoke tests.** State tested CLI
  versions and support for execution, reviewer permissions, steering, cancellation,
  and usage reporting for each advertised runner. Mark partial support explicitly.

## P1 — Documentation and community essentials before the announcement

- [ ] **Rewrite QUICK_START for the installed product.** It still tells users to
  copy Stagegate scripts/prompts into another repository and gives raw state-file
  edits/reset commands. Lead with `uncle`, one supported setup, one small task,
  expected approvals, and a documented recovery path that preserves PR journals.
- [ ] **Update CONTRIBUTING.** Rename “Contributing to Stagegate”; document Python,
  test dependencies, the actual full test command, Windows setup, fixture isolation,
  and no automatic signing. Its current test instructions omit the Python suites.
- [ ] **Reconcile README, PREREQUISITES, packaging docs, and workflow reference.**
  Document the release's actual defaults, stages, compaction policy, model setup,
  test environments, optional tools, and private-environment commands. Packaging
  still describes Windows curses as a separate manual install.
- [ ] **Explain security boundaries and data flow.** State what runs with the user's
  permissions, which files/logs are retained, where credentials are stored, what
  gets sent to external models, and what network/sandbox settings each runner
  actually enforces. Define independent review as a separate session/role unless
  a different model is required and configured; avoid implying either guarantees
  correctness or that all files are OS-level immutable.
- [ ] **Add SECURITY.md and a private vulnerability-reporting route.** Define
  supported versions, reporting contact, and response expectations. Review package
  contents, tracked workflow artifacts, screenshots, and example configuration for
  credentials/private content before release. No full secret/history audit was
  performed in this review.
- [ ] **Fix the Discussions invitation.** README and CONTRIBUTING invite discussion,
  but live GitHub metadata reports `has_discussions: false`. Enable Discussions
  and create a welcome/Q&A space, or remove/change those links.
- [ ] **Add issue forms and a PR template.** Ask for OS, Uncle revision/install path,
  runner/version, stage, reproduction steps, and redacted logs; warn against posting
  tokens/passphrases. Request tests and issue linkage in PRs. GitHub currently
  reports neither template.
- [ ] **Triage public issues into release blockers versus follow-up work.** Review
  [#40 triage](https://github.com/unclehq/uncle/issues/40),
  [#38 attestation](https://github.com/unclehq/uncle/issues/38),
  [#29 configuration](https://github.com/unclehq/uncle/issues/29), and
  [#26 PR work](https://github.com/unclehq/uncle/issues/26). An open enhancement is
  not automatically a blocker. Label support bugs and a few approachable first
  contributions; current listed issues have no labels.
- [ ] **Set repository topics and a support entry point.** Topics and homepage are
  empty in GitHub metadata. A polished README can serve as the landing page;
  a separate website is not required for beta.

Sources: [community profile](https://api.github.com/repos/unclehq/uncle/community/profile),
[repository metadata](https://api.github.com/repos/unclehq/uncle),
[QUICK_START.md](QUICK_START.md), [CONTRIBUTING.md](CONTRIBUTING.md),
[PREREQUISITES.md](PREREQUISITES.md), [packaging guide](packaging/README.md),
[workflow reference](scripts/README.md).

## P1 — Package the announcement

- [ ] **Publish a versioned beta release with release notes.** No tags or releases
  were returned by GitHub during this review; `VERSION` is `0.1.0`. Choose the
  release name, supported platforms/runners, known issues, and upgrade instructions.
  Provide installation instructions pinned to that tag/ref, not only moving `main`.
- [ ] **Verify downloadable artifacts and provenance.** Build from the release SHA,
  attach the intended packages/checksums or explain the source-build path, and test
  the published links. Existing installer CI uploads a Debian artifact but does
  not publish a release. Review bundled dependency license/notice obligations.
- [ ] **Add a short demo near the README quick start.** Show the actual homepage,
  a message steering a build, an approval, and the resulting PR. Keep private
  repository names, account details, keys, and unrelated terminal content out.
- [ ] **Prepare one announcement draft.** Include the problem, who beta is for,
  what makes Uncle useful, a working install command, the demo, provider costs,
  current limitations, and one feedback link. Avoid unmeasured speed/cost claims.
- [ ] **Have a few people outside the project follow the instructions unaided.**
  Capture where they stop; fix the instructions and first-run errors before broad
  promotion. Include a Windows user if Windows is in the launch headline.
- [ ] **Assign launch support ownership.** Decide where bugs/questions go, who
  responds, how to collect redacted diagnostics, and how to ship a rollback/fix.
- [ ] **Publish the release first, then announce it.** Verify links as a logged-out
  visitor, then post to the communities you choose. Track concrete installation
  failures and completed first runs, not only stars.

Release evidence: [releases](https://github.com/unclehq/uncle/releases),
[tags](https://github.com/unclehq/uncle/tags), [VERSION](VERSION).

## P2 — Can follow the beta announcement

- [ ] Build the dedicated website in [#34](https://github.com/unclehq/uncle/issues/34).
- [ ] Expand demo projects and model/provider compatibility beyond the tested matrix.
- [ ] Finish optional triage/attestation features if they are not release requirements.
- [ ] Refactor remaining test harnesses into pytest and tune parallelism using timings.
- [ ] Add release automation, broader package distribution, and more accessibility tests.
- [ ] Turn internal strategy notes into a short public roadmap, or clearly mark/archive
  stale Stagegate-era material so it does not compete with current user docs.

## Go / no-go record

- [ ] Release candidate SHA: __________
- [ ] Native CI run covering that SHA: __________
- [ ] Clean issue-to-PR evidence: __________
- [ ] New-app and first-run evidence: __________
- [ ] Known limitations published: __________
- [ ] All P0 items resolved; P1 announcement essentials complete: __________
- [ ] Maintainer launch decision and date: __________

Do not make closing every feature request a launch condition. Require the
advertised paths to work, failures to be recoverable, and limitations to be clear.
