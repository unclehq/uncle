# Testing pipeline reuse on the next run

New implementation approvals bind to file content and executable modes, relevant
plan inputs, and recorded verification command results. Their canonical snapshot
is bound to the human-approved review digest. Legacy approvals continue using
the old review digest comparison. Changed inputs still require approval.

Stage evidence packets also save structured handoffs under workflow/handoffs.
These are navigation evidence, not reviewer conclusions or approval records.

The verification runner supports explicit opt-in reuse through
`.uncle/workflow/check-reuse.json`. Keys are exact commands; each value supplies
`deterministic_read_only: true`, `always_run: false`, and `input_scopes`, the path
to a file using the protected-path inventory format. Scope every source, test,
fixture, lockfile and configuration input. Unspecified checks always execute.
Checks explicitly requiring repetition must not opt in. Do not opt in installs,
servers, network checks, time-sensitive checks, environment-mutating commands,
or checks with incomplete inputs. Reuse requires unchanged scoped content,
policy, complete environment and timing-run identity. Failed checks never cache.
Logs label reused evidence explicitly. Environment changes conservatively miss
cache; no environment values are persisted in cache keys.

Existing approved group barriers and worker limits remain authoritative. Reuse
compatible installed dependencies and browser binaries only after version checks;
share server setup only inside checks whose resource declarations permit it.
No new cross-stage server sharing or speculative overlap is enabled by this patch.
Install after testing, then start a fresh run. Do not replace installed code in
an ongoing benchmark. Compare time to completion, including repairs and approvals.
