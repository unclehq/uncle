# Change Request

Issue 275

Seeded from [unclehq/uncle#275](https://github.com/unclehq/uncle/issues/275).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Hosted builds never install a missing language toolchain: an OCaml app ends NOT_READY with its requirements waived and output hand-traced, though installing OCaml takes 5 seconds on the build machine

## Motivation

## What happened

A hosted, unattended build (Daytona sandbox, Debian 13, passwordless `sudo`, apt package lists present, `runner self-hosted`, Claude Sonnet 5) was asked for a hello-world OCaml application with a one-page interactive tutorial.

1. **Baseline.** The baseline report recorded the missing toolchain, and the green-check baseline failed on it:
   ```
   FAIL(1)   command -v ocaml && ocaml -version
   FAIL(1)   command -v dune && dune --version
   FAIL(1)   command -v ocamlfind && ocamlfind ocamlc -version
   ```
   The report assumed a toolchain "is or can be made available". The plan instead chose a fallback: "if `ocaml` is unavailable … hand-derive expected output", with R-3 "absence of `ocaml` must not block writing/implementing".
2. **Preflight.** `Preflight: the runtime probe did not confirm the environment: Deterministic preflight needs diagnosis: Unrecognized verification executable: command`. This was recorded as a non-blocking failure.
3. **Implementation.** "No ocaml binary found. I'll write both files, hand-trace output". AC-1 and AC-2 came back `INCOMPLETE`. The run printed "Unattended: waiving rejected rows (AC-1 AC-2); no person authorized this."
4. **Test review.** ASSERTIONS and COVERAGE failed as MAJOR, and NEGATIVE and ORACLE as MINOR. None was critical, so there was no repair.
5. **Final audit.** `NOT_READY`.

After the build finished, I ran `sudo apt-get install -y --no-install-recommends ocaml` on the same machine. It took about 5 seconds and installed OCaml 5.3.0. Both `.ml` files then ran with exit 0, and every output line matched the hand-traced output on the tutorial page. The build's only blocker was a toolchain it never tried to install.

An earlier hosted build that asked for a hello-world **Haskell** application shipped no Haskell at all: only `index.html`, JavaScript and JS tests. That looks like the same gap.

## Cause

1. Nothing in the workflow installs a runtime the plan needs. `install_warm.py` only warms the npm and Playwright caches. The baseline, planning and implementation prompts treat a missing compiler as a fact to work around, even on a hosted machine with a package manager and `sudo`.
2. `preflight.py` can't probe a toolchain outside its fixed list ([`scripts/lib/preflight.py#L12-L19`](https://github.com/unclehq/uncle/blob/3cecf2b3e46d59fa00389edd50ccb0fc93b2679a/scripts/lib/preflight.py#L12-L19)):
   - `BUILTINS` lacks `command`, yet the baseline writes `command -v <tool>`, the usual POSIX probe. Every such line raises "Unrecognized verification executable: command" ([`#L42-L44`](https://github.com/unclehq/uncle/blob/3cecf2b3e46d59fa00389edd50ccb0fc93b2679a/scripts/lib/preflight.py#L43-L44)).
   - `PROBES` covers node, npm, npx, python, bash, git, ruby, go, cargo, rustc, pytest and ruff only. `ocaml`, `dune`, `ghc`, `cabal`, `stack`, `java`, `dotnet`, `opam` and others are refused the same way. So preflight can neither confirm a missing toolchain nor report it as missing.
3. The supervisor that should diagnose these non-blocking failures is never started in headless builds (#274).

## Requested fix

1. In hosted builds (`UNCLE_HOSTED=1`), when the baseline or preflight shows that a runtime the plan's verification needs is missing, install it before implementation (apt, opam, ghcup, rustup and so on), or add an explicit toolchain step the implementer runs. Record what was installed in the baseline or preflight report.
2. Tell the planner and implementer that on a hosted machine with a package manager, a missing compiler is something to install, not a reason to hand-trace output or waive acceptance rows.
3. In `preflight.py`, treat `command -v <name>` (and `which <name>`) as a probe of `<name>`. For an executable not in `PROBES`, check it with `shutil.which` and report "Missing runtime: <name>" instead of refusing the line.
4. Add a test: a hosted hello-world build in a language missing from the base image (OCaml or Haskell) installs its toolchain, runs its verification commands, and reaches `READY` with AC rows `IMPLEMENTED`.

Related: #262 (Haskell, Rust and Go test-file recognition), #274 (supervisor never runs in headless builds).

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
