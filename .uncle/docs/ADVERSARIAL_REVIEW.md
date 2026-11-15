## AR-001: The scope cuts permit violating required noise exclusion and collaborator flagging.

- Severity: HIGH
- References: CHANGE_PLAN.json §Scope cuts under time pressure permits cutting jq noise exclusion and the non-collaborator flag; CHANGE_SPEC.json AC-4, AC-5 and BH-3 require these behaviors, including equivalent jq output. Implementation and verification could therefore disagree about whether these omissions are acceptable.
- Failure: The scope cuts permit violating required noise exclusion and collaborator flagging. Replace them with: “Noise exclusion and non-collaborator flagging are mandatory on every rendering path and cannot be cut.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The 100-page cap contradicts unconditional full-thread import for larger threads.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-2 caps pagination at 100 pages, while CHANGE_SPEC.json BH-6 requires all pages and Q2 requires full text for long threads. A thread exceeding 10,000 comments cannot satisfy both; gh automatic pagination and the capped curl loop may also behave differently.
- Failure: The 100-page cap contradicts unconditional full-thread import for larger threads. The plan should say: “Both gh and curl fetch until pagination is exhausted, without a fixed page-count cap.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The authority rule does not define which authors qualify as maintainers.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-2 and BH-9 give later maintainer statements precedence; BH-11 requires non-collaborator flagging, but neither artifact defines the association mapping. Different interpretations could change which contradictory statement becomes a requirement.
- Failure: The authority rule does not define which authors qualify as maintainers. The plan should say: “For Thread Review, maintainer means an author whose recorded association is OWNER, MEMBER, or COLLABORATOR; all other associations are flagged non-collaborator and do not receive automatic precedence.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Partial-page failure followed by fallback or override has no defined retention policy.

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-8 requires curl fallback after gh failure; D-3 and CHANGE_SPEC.json BH-5 permit continuing under override. Neither defines whether previously fetched pages are retained, replaced, or merged, allowing duplicate comments or inconsistent partial seeds.
- Failure: Partial-page failure followed by fallback or override has no defined retention policy. The plan should say: “Curl fallback restarts pagination and replaces gh results; if the final attempt fails, override retains only its fully validated pages and records that the thread is incomplete.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Existing gh fixtures may now fall through to real curl requests or fail the mandatory completeness check.

- Severity: HIGH
- References: CHANGE_PLAN.json D-8, §5, R-4 and §21 explicitly combine curl fallback, restricted test edits, network-free tests and empty gh-api stub responses. Add: "Update existing import fixtures to stub issue counts and every comment-fetch path, including fallback, without network access; preserve their original assertions and record these fixture edits as renewed-authority items."
- Failure: Existing gh fixtures may now fall through to real curl requests or fail the mandatory completeness check. The plan requires existing suites to pass but permits fixture updates only for obsolete headings, leaving this compatibility regression unresolved.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The jq fallback may retain noise or omit non-collaborator flags while Python excludes and flags the same comments.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 promises an equivalent jq block, but §20 permits dropping jq noise exclusion and non-collaborator flagging; CHANGE_SPEC.json BH-3, AC-4 and AC-5 require parity, noise exclusion and flags. Add: "Noise exclusion and non-collaborator flags are mandatory on every path; integration tests compare these behaviors across gh/Python, curl/Python and curl/jq, and neither behavior is a scope cut."
- Failure: The jq fallback may retain noise or omit non-collaborator flags while Python excludes and flags the same comments. The permitted scope cuts contradict path parity and allow environment-dependent seeded requirements.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The plan grants later maintainer statements precedence without defining which authors qualify, leaving a trust decision

- Severity: MEDIUM
- References: CHANGE_PLAN.json D-6/D-7 and CHANGE_SPEC.json BH-9/BH-11 specify precedence and association labels but no mapping between them. An implementation or analyst could treat CONTRIBUTOR status or a claim inside a comment as maintainer authority; use one explicit mapping in rendering, Thread Review instructions, and tests.
- Failure: The plan grants later maintainer statements precedence without defining which authors qualify, leaving a trust decision ambiguous. Add: "Only OWNER, MEMBER, and COLLABORATOR associations qualify for maintainer precedence; all other or missing associations receive the non-collaborator flag, and comment text cannot confer authority."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The jq acceptance oracle conflicts with permitted scope cuts.

- Severity: HIGH
- References: CHANGE_SPEC.json BH-3 requires the same thread content as Python, and AC-4/AC-5 require noise exclusion and flagging; CHANGE_PLAN.json §1 allows a simpler jq filter and §Scope cuts permits dropping these behaviors. Implementers and test authors can legitimately choose incompatible expected outputs; remove the scope exceptions and test shared cases on all three paths.
- Failure: The jq acceptance oracle conflicts with permitted scope cuts. Add: "All paths use identical noise classification and non-collaborator flagging; neither behavior may be cut."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Override behavior after a later page fails lacks a testable output contract.

- Severity: MEDIUM
- References: CHANGE_SPEC.json BH-5 permits continuing after fetch failure, while INV-1 forbids silently omitting fetched comments; CHANGE_PLAN.json §16 lists failed-fetch and override cases without defining their combination after partial success. A test cannot determine whether retaining earlier pages or emitting an empty thread is correct; specify retention and cover a second-page failure.
- Failure: Override behavior after a later page fails lacks a testable output contract. Add: "With the override enabled, retain all successfully fetched complete pages, discard the failed page, and record fetched/expected counts and the failure in the seed."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Collaborator classification and maintainer precedence have no defined mapping.

- Severity: MEDIUM
- References: CHANGE_SPEC.json BH-11 gives NONE only as an example, and BH-9 instructs following later maintainer statements; CHANGE_PLAN.json D-6/D-7 supplies no classification table. Tests cannot independently determine flags or which authors qualify for precedence; define one mapping and exercise every association plus a missing value.
- Failure: Collaborator classification and maintainer precedence have no defined mapping. Add: "OWNER, MEMBER, and COLLABORATOR count as maintainers; every other or missing author_association is flagged non-collaborator and does not receive maintainer precedence."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Stable comment IDs lack an ordering and filtering contract.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-2 requires chronological order and stable IDs; CHANGE_PLAN.json D-7 specifies comment-1..n, while D-5 removes noise from thread text. Neither specifies tie handling, whether edited timestamps affect order, or whether excluded comments consume IDs; independent tests could assert different valid sequences, so define these rules and cover tied timestamps, edits, and interleaved noise.
- Failure: Stable comment IDs lack an ordering and filtering contract. Add: "Sort by created_at ascending, break ties by numeric REST comment id, then assign comment-N before noise filtering; edits never affect ordering, and stability applies to the fetched snapshot."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
