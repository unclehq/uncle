## AR-001: The plan permits dropping required behavior while retaining its acceptance criteria.

- Severity: HIGH
- References: .uncle/workflow/documents/CHANGE_PLAN.json §21 permits cutting S-3 and edits.py; R-B permits omitting Markdown derivation if validation rejects the field. These alternatives conflict with CHANGE_SPEC.json AC-5/SB-5 and the plan's D-2 promise that both merge paths agree, allowing completion without the requested fix.
- Failure: The plan permits dropping required behavior while retaining its acceptance criteria. Add: "S-3 and the edits.py consistency change are required; if validation rejects the field, resolve that incompatibility before completion."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Extensionless executed paths have contradictory eligibility rules.

- Severity: MEDIUM
- References: .uncle/workflow/documents/CHANGE_PLAN.json D-1 accepts tokens containing a slash or extension, while CHANGE_SPEC.json §15 requires a file extension. Thus scripts/check can be protected or omitted depending on which document drives implementation and tests; align the specification and add an acceptance example.
- Failure: Extensionless executed paths have contradictory eligibility rules. Add: "An executed repository-relative token qualifies if it contains a slash or a file extension, subject to exclusions; extensionless paths such as scripts/check qualify."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Interpreter options and inline code lack a defined extraction rule, risking missed scripts or protection of files that a

- Severity: MEDIUM
- References: .uncle/workflow/documents/CHANGE_PLAN.json D-1 says tokens 'following an interpreter'; CHANGE_SPEC.json §15 says 'first argument'. Neither settles bash -e scripts/check.sh or python3 -c 'scripts/check.py'. These inputs can produce different protected sets or false protection; define option handling and cover both cases.
- Failure: Interpreter options and inline code lack a defined extraction rule, risking missed scripts or protection of files that are not executed. Add: "Skip interpreter options when locating a script operand; inline-code and module modes yield no script path, and their arguments are never scanned as executed files."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Populating protected paths during Markdown ingest can preserve stale paths when review later renames or removes tests.

- Severity: HIGH
- References: CHANGE_PLAN.json D-3 prepopulates the field, while scripts/lib/updated_plan_ops.py:939–960 derives from the merged model only when existing paths are empty. Lines 942–944 explicitly identify resurrecting renamed paths from the base narrative as a regression; require a Markdown-ingest-to-merge regression case that renames a protected script and asserts only its new path survives.
- Failure: Populating protected paths during Markdown ingest can preserve stale paths when review later renames or removes tests. Add: "When merged steps or commands change, recompute ingest-derived protected paths from the merged plan and commands, then apply ownership filtering; preserve explicitly supplied paths."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Interpreter option handling is unspecified, allowing inline code or option values to be mistaken for protected files.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-1 accepts tokens “following an interpreter”; CHANGE_SPEC.json §15 instead specifies its first argument. Neither defines `python3 -c 'scripts/check.sh'` or `bash -c ...`; treating these strings as files can satisfy the nonempty protection check without protecting an executed script.
- Failure: Interpreter option handling is unspecified, allowing inline code or option values to be mistaken for protected files. Add: “Parse commands without executing them; interpreter inline-code strings and option values are not script paths, and only literal script operands qualify.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The fixture signing mechanism omits tag signing and repository-local settings and is scoped only to AC-6.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §16 and R-1 specify only `-c commit.gpgsign=false` and `--no-gpg-sign`; R-1 references AC-6 alone, although AC-3 also creates a fixture plan. The binding signing instructions require both signing settings for every disposable repository and subprocess, explicit tag suppression, and fake-signer verification for new helpers; the stated mechanism leaves inherited signing reachable.
- Failure: The fixture signing mechanism omits tag signing and repository-local settings and is scoped only to AC-6. Add: “All new or modified fixtures and their subprocesses disable commit and tag signing through command and local configuration, retain explicit no-sign flags, and verify helpers with an isolated failing fake signer.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The shell test exercises helpers without requiring the stagegate dispatch that distinguishes conflicts from writer exhau

- Severity: HIGH
- References: CHANGE_PLAN.json §16 specifies sourcing model-jobs.sh helpers; D-4 assigns status handling to stagegate.sh. CHANGE_SPEC.json AC-6 and SI-5 require stagegate behavior, so helper-only tests could pass while the original misreporting remains.
- Failure: The shell test exercises helpers without requiring the stagegate dispatch that distinguishes conflicts from writer exhaustion. Add: “The shell regression must exercise stagegate’s merge dispatch with statuses 0, 4, and 1 and assert the resulting stop reason, flag, and output.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Extensionless executed paths have contradictory expected results, preventing a consistent test oracle.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-1 accepts tokens containing a slash OR a file extension, but CHANGE_SPEC.json §15 requires a file extension. AC-1 examples all have extensions, leaving this disagreement undetected.
- Failure: Extensionless executed paths have contradictory expected results, preventing a consistent test oracle. Add: “Executed-file candidates may contain a slash without an extension; include scripts/check in positive derivation tests while excluding bare tool names.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Interpreter options and inline programs have no defined derivation outcome.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-1 says tokens following an interpreter; CHANGE_SPEC.json §15 says its first argument. Neither defines options or inline execution, and AC-1 only requires interpreter-prefixed forms, allowing incompatible parsers and tests.
- Failure: Interpreter options and inline programs have no defined derivation outcome. Add: “Skip interpreter options to identify a script operand, but return no executed-file candidates for inline-code or module invocations; test python3 -u scripts/check.py, python3 -c, python3 -m, and bash -c.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The required single-line, truncated conflict message has no precise expected output.

- Severity: MEDIUM
- References: CHANGE_SPEC.json §8 requires a single-line, truncated message; CHANGE_PLAN.json D-4 captures and replays merge stderr without defining normalization or a limit. AC-6 cannot assert a unique stop-reason value for these inputs until the transformation is specified.
- Failure: The required single-line, truncated conflict message has no precise expected output. Add: “Strip the updated-plan ops prefix, replace each run of whitespace with one space, trim, and retain the first 500 Unicode characters; test multiline, empty, and over-limit stderr.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
