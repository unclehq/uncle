Execution settings use `execution.<name> VALUE` in `.uncle/config`; the corresponding
`WORKFLOW_<NAME>` environment variable (uppercase, hyphens replaced by underscores)
wins. Settings are read when the helper runs, with no model-specific dependency.

| Name | Default | Meaning |
| --- | --- | --- |
| check-idle-seconds | 90 | Stop a silent check whose owned process tree stays below the configured CPU threshold; 0 disables. Unknown CPU accounting falls back to the overall timeout. |
| check-idle-cpu-percent | 1 | Minimum average percentage of one CPU core to count as activity, with a 0.05 CPU-second quantization floor. |
| install-lock-seconds | 15 | Maximum wait for another managed cache install. |
| install-lock | ~/.cache/uncle/install.lock | Shared advisory lock, never deleted. All cooperating runs must use the same path. |
| playwright-preflight | true | Check local Node Playwright before recognized browser commands; disable explicitly for custom launchers. |
| playwright-browsers | chromium | Comma-separated chromium,firefox,webkit. Chromium also checks the headless-shell executable when the installed version declares it. |
| playwright-auto-install | false | Install missing browser files under the shared lock; otherwise fail before launching browser tests. |
| browser-install-seconds | 180 | Overall limit for an automatic browser install. |
| step-tests | true for self-hosted; false otherwise | Run a fast unit target after each serial step or merged independent group, before checkpointing. |
| step-test-command | auto | Explicit fast unit command; otherwise select `test:unit` or `test` only when it invokes `vitest run` or `node --test` and unit files exist. No ready target is recorded as NOT RUN. |
| step-test-seconds | 120 | Overall fast-check limit. Failures stop advancement and retain a per-step log. |
| scaffold-template | empty (off) | `vite-react` opts into the deterministic scaffold below. |

`WORKFLOW_CHECK_TIMEOUT_SECONDS` continues to control the overall check limit (900 seconds).
A stalled check returns 123 and logs STALLED with preceding output; a total timeout returns 124.
CPU is sampled across the POSIX process group and descendants, or the native Windows Job.
Serial checks spool output locally so redirected pipes also support idle detection.

Managed warm-up, background setup, and green-check install commands share the lock. Cleanup
terminates only owned process trees; it never removes the shared cache, installer locks, or
another run's downloads. Playwright garbage collection is disabled for these installs so a
warm-up using a different version cannot delete an active project's browsers. Commands run
manually or directly by a model outside these managed paths do not participate in this lock.
Preflight recognizes direct Playwright commands, npm/pnpm/yarn/bun scripts, and leading `cd`.
Combined install-and-browser-test commands fail immediately with a request to separate setup from tests,
so the version check happens after installation. Custom launchers should expose a package script or
call the helper explicitly. Set the browser
selection to match the project's projects/channels; arbitrary executablePath overrides are not inferred.

To opt into the scaffold, set `execution.scaffold-template vite-react` before implementation.
Both drivers call the helper at implementation entry. The approved first step must own all four
files (`package.json`, `vite.config.js`, `playwright.config.js`, `.gitignore`) or `*`. Existing
nonidentical files and symlinks are refused before writing. An application receipt prevents
resume from overwriting later implementation edits. The model supplies the application, entry
point, and real tests; this template contains no placeholder passing tests.

The exact template bytes are in `vite-react/`. The package versions are a fixed compatibility
baseline, not a claim about current releases; dependency upgrades require explicit template
review. `verification-commands.txt` is copied to `.uncle/workflow/scaffold-verification-commands.txt`
as a proposal for the plan's normal approval flow. Applying a template never replaces the
approved verification commands, assertions, or protected paths. No install happens on application.
The template separates unit and browser test discovery and requires a production build before
Playwright starts Vite preview. It assumes Node 20 and Chromium with Playwright's default channel.

Run the hermetic regressions with `python3 -I scripts/tests/execution-hygiene-test.py` and
`bash scripts/run-shell-tests.sh`. No fixture needs a Git commit or accesses a real signing key.
