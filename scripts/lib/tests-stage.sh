#!/usr/bin/env bash
# EXPERIMENTAL (on by default; WORKFLOW_TESTS=0 turns it off): write the protected tests before any application code, in parallel lanes, show them to
# the human, freeze them, and refuse an implementation that edits or deletes a frozen file.
#
# Sits between MODULE_INTERFACES and IMPLEMENT. With WORKFLOW_TESTS=0 the state is a pass-through, so a normal
# run is unchanged.
#
# Lanes. A `harness` lane (test configuration, fixtures, helpers) runs first, because every other lane imports it. Then the
# remaining lanes -- `unit` always, `e2e` when the plan mentions a browser/playwright, `mutation` when it mentions defect
# injection -- run concurrently in the same tree, each owning disjoint files that it reports in tests/lane-<name>.files.
# After the barrier the driver (not an agent) checks ownership, runs the plan's test commands once to confirm the suite is red
# for the right reason, and only then opens the human gate.
#
#   WORKFLOW_TESTS_LANES="unit e2e"   override the lane list (harness is implied first unless listed)
#   WORKFLOW_TESTS_PARALLEL=0         run the lanes one after another (debugging)
#   WORKFLOW_TESTS_RED_TIMEOUT=120    seconds allowed per test command in the red check
#
# Needs from the caller: ROOT, STATE_DIR, LOG_DIR, PLAN_DOC, UNATTENDED, set_state, run_claude, hash_file, verification_paths,
# verification_manifest, verify_commands.

tests_enabled() {
    case "${WORKFLOW_TESTS:-1}" in
        1) return 0 ;;
        0) return 1 ;;
        *) echo "WORKFLOW_TESTS=${WORKFLOW_TESTS} is not 0 or 1; tests is OFF (a stray character after the 1?)." >&2
           return 1 ;;
    esac
}

# WORKFLOW_TESTS_RUNNER_REUSE=0 gives every lane its own cold CLI (the older behaviour); the default shares warm runners.
tests_runner_reuse() { if [[ "${WORKFLOW_TESTS_RUNNER_REUSE:-1}" == 0 ]]; then printf 0; else printf '%s' "${UNCLE_RUNNER_REUSE:-1}"; fi; }

tests_lock() { printf '%s/tests.lock' "$STATE_DIR"; }
tests_dir() { printf '%s/tests' "$STATE_DIR"; }

# The lock is only valid for the plan it was frozen against.
tests_locked() {
    local lock; lock="$(tests_lock)"
    [[ -s "$lock" && -s "$STATE_DIR/tests-plan.sha256" \
        && "$(cat "$STATE_DIR/tests-plan.sha256")" == "$(hash_file "$PLAN_DOC")" ]]
}

# Manifest of the protected paths that exist right now. Absent ones are tolerated: a plan may protect a path the tests
# legitimately do not need, and the implementation stage still creates anything the tests did not.
tests_manifest() {
    local absent="$STATE_DIR/tests.absent" scope
    : > "$absent"
    while IFS= read -r scope; do
        [[ -e "${scope%/}" ]] || printf '%s\n' "$scope" >> "$absent"
    done < "$STATE_DIR/tests.paths"
    # Completable files (declared by a lane) are not hash-frozen even when a protected directory scope covers them.
    local mutable; mutable="$(tests_dir)/mutable.paths"
    if [[ -s "$mutable" ]]; then
        WORKFLOW_ALLOW_ABSENT_PROTECTED_DIRECTORIES="$absent" verification_manifest "$STATE_DIR/tests.paths" \
            | awk -F'\t' 'NR == FNR { m[$0] = 1; next } !($2 in m)' "$mutable" -
    else
        WORKFLOW_ALLOW_ABSENT_PROTECTED_DIRECTORIES="$absent" verification_manifest "$STATE_DIR/tests.paths"
    fi
}

# Lanes this plan needs, in order. Harness is always first.
tests_lanes() {
    local wanted="${WORKFLOW_TESTS_LANES:-}" text
    if [[ -z "$wanted" ]]; then
        text="$(cat "$PLAN_DOC" REQUIREMENTS.md 2> /dev/null || true)"
        wanted="unit"
        printf '%s' "$text" | grep -qiE 'playwright|e2e|end-to-end|cypress|browser test|in a browser' && wanted="$wanted e2e"
        printf '%s' "$text" | grep -qiE 'defect.injection|mutation|representative defect' && wanted="$wanted mutation"
    fi
    case " $wanted " in *" harness "*) ;; *) wanted="harness $wanted" ;; esac
    printf '%s\n' $wanted
}

tests_lane_brief() {
    case "$1" in
        harness) cat <<'EOT'
Lane `harness` (runs first, alone). Own: test-runner configuration (vitest/jest/pytest/playwright config), setup files, shared
fixtures and oracle data, and shared helpers (for example a selector helper built from the `ui_contract`, a key-press helper, a
state builder). Write NO test cases: the other lanes write them, start after you finish, and will import what you wrote. Make each
helper's name and signature explicit in your notes under `## Assumed interfaces` (list them as exports), because they are binding
for the other lanes. If the plan needs none of this, write an empty files list.
EOT
        ;;
        unit) cat <<'EOT'
Lane `unit`. Own: pure domain/logic unit tests, component tests (render, props, events, with the testing library the plan names),
and property or invariant tests. Cover every behavior and invariant that is not a whole-browser flow. Conventional location when the
plan names none: `tests/unit/` and `tests/component/`. Do not write browser (playwright/cypress) tests or defect-injection specs.
EOT
        ;;
        e2e) cat <<'EOT'
Lane `e2e`. Own: browser tests that drive the real application the way a user does, with the framework the plan names (for
example playwright), including every keyboard flow and visible-state requirement the plan lists. Select elements only through the
`ui_contract` names. Rely on whatever web-server configuration the harness lane wrote; do not write your own server. Conventional
location when the plan names none: `tests/e2e/`. Do not write unit, component or defect-injection files.
EOT
        ;;
        mutation) cat <<'EOT'
Lane `mutation`. Own: the defect-injection list. For each representative defect the plan lists (and each critical invariant the plan
says must reject a defect), write one entry in the list file the plan names (default `tests/mutations/list.mjs`, exporting an array
as `defects` and as the default): `id`, `breaks` (behavior/invariant ids), `mutation` (plain-language wrong implementation), `target`
(the source module that contains it, taken from MODULE_INTERFACES.json), `spec` (the test file that must fail) and
`expected_failing_tests` (ids the other lanes cite in test names).

Do NOT write `file`, `find` or `replace`. The runner needs the exact source text to replace, and no source exists yet: guessing it
would freeze text that cannot match. The implementation step that owns this list adds those fields after the source is written,
and the driver checks that every id, `breaks` and `expected_failing_tests` you write survives unchanged. So this file is
COMPLETABLE, not frozen: list it in `.uncle/workflow/tests/lane-mutation.mutable` (one path per line) in addition to the
usual `.files`. Do NOT write the injection runner when the plan says the driver provides it (`mutation_runner.mjs`).
EOT
        ;;
        *) printf 'Lane `%s`. Own the tests the plan assigns to this lane and nothing else.\n' "$1" ;;
    esac
}

# tests_run_lane <lane> -- one author for one lane. Resumable: a lane that finished is not run again.
tests_run_lane() {
    local lane="$1" dir prompt others
    dir="$(tests_dir)"
    [[ ! -e "$dir/lane-$lane.done" ]] || return 0
    others="$(tests_lanes | grep -vx "$lane" | tr '\n' ' ')"
    prompt="$PWD/$dir/prompt-$lane.md"
    case "$dir" in /*) prompt="$dir/prompt-$lane.md" ;; esac
    {
        cat "$ROOT/prompts/tests.md"
        printf '\n## Your lane\n\n'
        tests_lane_brief "$lane"
        printf '\nOther lanes in this run: %s\n' "${others:-none}"
        printf 'Your lane name for the two output files is `%s`.\n' "$lane"
    } > "$prompt"
    rm -f "$dir/lane-$lane.files" "$dir/lane-$lane.md"
    local rc=0
    # Runner reuse (a warm pooled CLI, keyed by the `implementation` runner config these lanes share) saves the cold start and keeps the
    # prompt cache warm for every lane. The pool falls back to an unpooled run when every slot is busy.
    SESSION_REUSE=0 UNCLE_RUNNER_REUSE="$(tests_runner_reuse)" PROGRESS_TOTAL=0 \
        run_claude "$prompt" "tests-$lane" > "$LOG_DIR/tests-$lane.log" 2>&1 || rc=$?
    # WORKFLOW_TESTS_TRACE=1 records how each lane's agent call ended (the log alone can end mid-line if it was killed).
    [[ "${WORKFLOW_TESTS_TRACE:-0}" != 1 ]] || echo "lane $lane run_claude rc=$rc at $(date +%T)" >> "$dir/trace-exit.log"
    [[ "$rc" == 0 ]] || return 1
    [[ -f "$dir/lane-$lane.files" ]] || { echo "Tests lane $lane wrote no lane-$lane.files." >&2; return 1; }
    touch "$dir/lane-$lane.done"
}

tests_status_snapshot() { git status --porcelain=v1 -uall 2> /dev/null | LC_ALL=C sort; }

# Whether $1 lies inside a protected scope.
tests_covered() {
    local path="$1" scope
    while IFS= read -r scope; do
        [[ -n "$scope" ]] || continue
        [[ "$path" == "$scope" || "$path" == "${scope%/}/"* ]] && return 0
    done < "$STATE_DIR/tests.paths"
    return 1
}

# Barrier checks the driver makes itself. Prints each problem; fails if any.
tests_collate() {
    local dir lane file line problems=0 owner listed="$STATE_DIR/tests/listed.tsv" path
    dir="$(tests_dir)"
    : > "$listed"; : > "$STATE_DIR/tests/outside.paths"
    while IFS= read -r lane; do
        if [[ ! -f "$dir/lane-$lane.files" ]]; then
            echo "  lane $lane has no $dir/lane-$lane.files (delete lane-$lane.done and rerun to redo it)"; problems=$((problems + 1)); continue
        fi
        while IFS= read -r file; do
            [[ -n "$file" ]] || continue
            if [[ ! -f "$file" ]]; then
                echo "  lane $lane lists $file, which does not exist"; problems=$((problems + 1)); continue
            fi
            if ! tests_covered "$file"; then
                # Shared helpers/fixtures the plan did not list. Not an error: tests freezes them itself (see tests_freeze_paths).
                echo "  note: lane $lane wrote $file, which the plan does not list under Protected verification paths; tests will freeze it."
                printf '%s\n' "$file" >> "$STATE_DIR/tests/outside.paths"
            fi
            if owner="$(awk -F'\t' -v f="$file" '$2 == f { print $1; exit }' "$listed")" && [[ -n "$owner" ]]; then
                echo "  $file is listed by lanes $owner and $lane"; problems=$((problems + 1))
            fi
            printf '%s\t%s\n' "$lane" "$file" >> "$listed"
        done < "$dir/lane-$lane.files"
    done < <(tests_lanes)
    # Anything that appeared in the tree and no lane claimed is production code or a stray.
    while IFS= read -r line; do
        path="${line:3}"
        [[ -n "$path" && "$path" != .uncle/* ]] || continue
        awk -F'\t' -v f="$path" '$2 == f { found = 1 } END { exit !found }' "$listed" && continue
        # Concurrent mode: the implementation is writing source at the same time, so a changed file an implementation step owns is its own.
        if tests_concurrent && [[ -s "$STATE_DIR/implement-owns.all.tsv" ]] \
                && awk -F'\t' -v f="$path" '$2 == f { found = 1 } END { exit !found }' "$STATE_DIR/implement-owns.all.tsv"; then continue; fi
        echo "  $path changed during test authoring and no lane claimed it"; problems=$((problems + 1))
    done < <(comm -13 "$dir/status.before" <(tests_status_snapshot))
    [[ "$problems" == 0 ]]
}

# Run the plan's test commands once, before any code exists. Hard failure only if every test command passes (a vacuous suite);
# everything else is evidence for the human at the gate.
tests_red_check() {
    local out="$1" timeout="${WORKFLOW_TESTS_RED_TIMEOUT:-120}" cmd status ran=0 passed=0 log
    : > "$out"
    printf '## Red-state check (driver-run, before any application code)\n\n' >> "$out"
    while IFS= read -r cmd; do
        [[ -n "$cmd" ]] || continue
        printf '%s' "$cmd" | grep -qiE 'vitest|jest|pytest|playwright|mocha|cypress|go test|cargo test|node --test|npm (run )?test|npm run test' || continue
        log="$(mktemp)"
        status=0
        python3 -B -c '
import subprocess, sys
try:
    r = subprocess.run(sys.argv[1], shell=True, capture_output=True, text=True, timeout=float(sys.argv[2]))
    sys.stdout.write((r.stdout + r.stderr)[-6000:]); sys.exit(r.returncode if r.returncode < 125 else 1)
except subprocess.TimeoutExpired as e:
    sys.stdout.write("TIMEOUT after %ss\n" % sys.argv[2]); sys.exit(124)' "$cmd" "$timeout" > "$log" 2>&1 || status=$?
        ran=$((ran + 1))
        [[ "$status" != 0 ]] || passed=$((passed + 1))
        printf -- '- `%s` exited %s' "$cmd" "$status" >> "$out"
        if grep -qiE 'no test files found|no tests (found|ran)|collected 0 items|0 tests' "$log"; then printf ' -- WARNING: collected no tests' >> "$out"; fi
        if grep -qE 'SyntaxError|Unexpected token|Transform failed' "$log"; then printf ' -- WARNING: a syntax error (an authoring defect, not a red test)' >> "$out"; fi
        if [[ "$status" == 124 ]]; then printf ' -- timed out' >> "$out"; fi
        printf '\n' >> "$out"
        rm -f "$log"
    done < <(verify_commands "$PLAN_DOC")
    if [[ "$ran" == 0 ]]; then
        printf 'No test commands recognised in the plan; nothing was run.\n' >> "$out"
        return 0
    fi
    if [[ "$passed" == "$ran" ]]; then
        printf '\n**All %s test command(s) passed with no application code: the suite is vacuous.**\n' "$ran" >> "$out"
        return 1
    fi
    printf '\n%s of %s test command(s) failed as expected before implementation.\n' "$((ran - passed))" "$ran" >> "$out"
    return 0
}

tests_concurrent() { [[ "${WORKFLOW_TESTS_CONCURRENT:-1}" == 1 ]]; }

# Create the working directory, read the plan's protected scopes, and note which files already changed. Idempotent.
tests_prepare() {
    local dir notes=.uncle/docs/TESTS_NOTES.md
    dir="$(tests_dir)"
    mkdir -p "$dir" "$(dirname "$notes")"
    verification_paths "$PLAN_DOC" > "$STATE_DIR/tests.paths.new" 2> "$STATE_DIR/tests.log" || {
        echo "Tests: cannot read the plan's Protected verification paths:" >&2
        cat "$STATE_DIR/tests.log" >&2
        return 1
    }
    # Never rewrite the scope list once lanes have extended it (outside.paths) or the freeze set was derived from it.
    if [[ ! -e "$dir/prepared" ]]; then mv "$STATE_DIR/tests.paths.new" "$STATE_DIR/tests.paths"; else rm -f "$STATE_DIR/tests.paths.new"; fi
    [[ -e "$dir/status.before" ]] || tests_status_snapshot > "$dir/status.before"
    touch "$dir/prepared"
}

# Harness first (everyone imports it), then the remaining lanes concurrently. Returns 1 if any lane failed; never exits, so a
# background caller can record the outcome.
tests_run_lanes() {
    local lane failed=0 dir; dir="$(tests_dir)"
    local -a pids=() names=() all_lanes=()
    while IFS= read -r lane; do all_lanes+=("$lane"); done < <(tests_lanes)
    echo "Tests lanes: ${all_lanes[*]}"
    tests_run_lane harness || { echo "Tests: the harness lane failed; see $LOG_DIR/tests-harness.log" >&2; return 1; }
    for lane in "${all_lanes[@]}"; do
        [[ "$lane" != harness ]] || continue
        if [[ "${WORKFLOW_TESTS_PARALLEL:-1}" == 0 ]]; then
            tests_run_lane "$lane" || { echo "Tests: lane $lane failed." >&2; failed=1; }
        else
            # An explicit subshell, not `tests_run_lane "$lane" &`: under macOS bash 3.2 an async *function* silently exits (status 0)
            # the first time it calls a function that does `command ...; return` -- which is the driver's own `python3` (pyhost.sh).
            ( tests_run_lane "$lane" ) & pids+=("$!"); names+=("$lane")
        fi
    done
    # An index loop, not "${!pids[@]}": bash 3.2 (macOS) expands that to nothing for these arrays and the barrier silently vanishes.
    local i=0 count=${#pids[@]}
    while (( i < count )); do
        wait "${pids[$i]}" || { echo "Tests: lane ${names[$i]} failed; see $LOG_DIR/tests-${names[$i]}.log" >&2; failed=1; }
        i=$((i + 1))
    done
    if [[ "$failed" == 1 ]]; then
        echo "Rerun to retry only the failed lane(s); finished lanes are kept." >&2
        return 1
    fi
}

# Barrier checks, notes, optional red check and human gate, then freeze. Arguments: <gate 0|1> <red 0|1>. Returns 1 on any failure.
tests_finish() {
    local gate="$1" red="$2" notes=.uncle/docs/TESTS_NOTES.md answer lane dir; dir="$(tests_dir)"
    local -a all_lanes=()
    while IFS= read -r lane; do all_lanes+=("$lane"); done < <(tests_lanes)
    echo "Tests: lanes finished; checking ownership."
    if ! tests_collate; then
        echo "Tests: ownership check failed. Fix the files above, or delete $dir/lane-<name>.done to rerun a lane." >&2
        return 1
    fi
    : > "$dir/mutable.paths"
    for lane in "${all_lanes[@]}"; do
        [[ ! -s "$dir/lane-$lane.mutable" ]] || grep -v '^$' "$dir/lane-$lane.mutable" >> "$dir/mutable.paths"
    done
    sort -u "$dir/outside.paths" >> "$STATE_DIR/tests.paths"
    if [[ -s "$dir/mutable.paths" ]]; then   # completable files are not hash-frozen
        grep -vxF -f "$dir/mutable.paths" "$STATE_DIR/tests.paths" > "$STATE_DIR/tests.paths.tmp" || true
        mv "$STATE_DIR/tests.paths.tmp" "$STATE_DIR/tests.paths"
    fi
    if ! tests_manifest | grep -qv '^ABSENT\|^DIRECTORY'; then
        echo "Tests: none of the plan's Protected verification paths hold a file; there is nothing to freeze." >&2
        return 1
    fi
    {
        printf '# Tests notes\n\nAssembled by the driver from the lane notes. Lanes: %s\n' "${all_lanes[*]}"
        for lane in "${all_lanes[@]}"; do
            printf '\n---\n\n# Lane: %s\n\nFiles:\n' "$lane"
            sed 's/^/- /' "$dir/lane-$lane.files"
            printf '\n'
            [[ ! -f "$dir/lane-$lane.md" ]] || cat "$dir/lane-$lane.md"
        done
    } > "$notes"
    if [[ "$red" == 1 ]]; then
        if ! tests_red_check "$dir/red-check.md"; then
            cat "$dir/red-check.md" >&2
            cat "$dir/red-check.md" >> "$notes"
            echo "Tests: the suite passes with no code. Strengthen the tests (delete $dir/lane-<name>.done to rerun a lane)." >&2
            return 1
        fi
        { printf '\n---\n\n'; cat "$dir/red-check.md"; } >> "$notes"
    else
        printf '## Red-state check\n\nSkipped: the tests were written while the implementation ran, so there is no code-free state to run them against.\n' > "$dir/red-check.md"
    fi
    echo
    echo "=================================================="
    if [[ "$gate" == 1 ]]; then echo "TESTS: review the tests before any code exists"; else echo "TESTS: tests written alongside the implementation (frozen now)"; fi
    echo "=================================================="
    echo "Notes (assumed interfaces, coverage, red-state check): $notes"
    echo "Files, by lane:"
    sort "$dir/listed.tsv" | awk -F'\t' '{ printf "  [%s] %s\n", $1, $2 }'
    echo
    sed -n '3,$p' "$dir/red-check.md"
    echo
    if [[ "$gate" == 1 ]]; then
        echo "Approving freezes these files: the implementation may not edit or delete them."
        echo "A wrong assumption found later means deleting $(tests_lock) and rerunning this stage."
        if [[ "${UNATTENDED:-0}" != 1 ]]; then
            printf '%s' "$(gate_prompt 'Approve and freeze these tests? [y/N] ')"
            read -r answer || answer=n
            case "$answer" in
                y|Y|yes|YES) ;;
                *) echo "Not approved. Edit the tests (or $notes) and rerun; finished lanes are not rerun."; return 1 ;;
            esac
        fi
    else
        echo "These files are now frozen. You approve them with the implementation at the next gate, where the diff includes them."
    fi
    tests_manifest > "$(tests_lock)"
    if [[ -e "$dir/intent.early" ]]; then rm -f "$dir/intent.early"; else tests_intent_snapshot; fi
    hash_file "$PLAN_DOC" > "$STATE_DIR/tests-plan.sha256"
}

# Sequential mode: author, review, freeze, then implement.
tests_stage() {
    if ! tests_enabled || tests_locked; then
        set_state IMPLEMENT
        return 0
    fi
    tests_prepare || exit 1
    tests_run_lanes || exit 1
    tests_finish 1 1 || exit 1
    set_state IMPLEMENT
}

# --- Concurrent mode: the lanes run in the background while the implementation steps run -------------------------------------
# Implementation and tests are both written from the approved plan and the shared module contract, so neither needs the other to
# start. The implementation steps are told that the protected scopes are reserved (see tests_reserved_scopes); the lanes write
# only inside them. The barrier is tests_join, called right after the implementation stage.
tests_pid_file() { printf '%s/tests/authoring.pid' "$STATE_DIR"; }

tests_authoring_running() {
    local pid; pid="$(cat "$(tests_pid_file)" 2> /dev/null || true)"
    [[ -n "$pid" ]] && kill -0 "$pid" 2> /dev/null
}

tests_background_start() {
    tests_enabled && tests_concurrent && ! tests_locked || return 0
    local dir; dir="$(tests_dir)"
    tests_prepare || return 1
    if tests_authoring_running; then return 0; fi
    rm -f "$dir/authoring.status"
    # Warm the shared runner now (unattended runs only; the call is a no-op otherwise) so the first lane does not pay the cold start.
    if declare -F unattended_prewarm_stage_for_state > /dev/null && [[ "$(tests_runner_reuse)" != 0 ]]; then unattended_prewarm_stage_for_state TESTS || true; fi
    echo "Tests: writing the tests in the background while the implementation runs (log: $LOG_DIR/tests-authoring.log)."
    ( tests_run_lanes; echo "$?" > "$dir/authoring.status" ) > "$LOG_DIR/tests-authoring.log" 2>&1 &
    echo "$!" > "$(tests_pid_file)"
}

tests_join() {
    tests_enabled || return 0
    local dir; dir="$(tests_dir)"
    if tests_concurrent && ! tests_locked; then
        tests_prepare || return 1
        tests_complete_early_start            # the mutation author is often done long before the others
        if tests_authoring_running; then
            local started="$SECONDS"
            echo "Tests: implementation finished; waiting for the test authors..."
            while tests_authoring_running; do tests_complete_early_start; sleep 1; done
            echo "Tests: authors finished after a further $((SECONDS - started))s."
        fi
        if [[ "$(cat "$dir/authoring.status" 2> /dev/null || echo missing)" != 0 ]]; then
            # Never ran to completion (crash, resume, or a failed lane): lanes are resumable, so finish them here.
            [[ ! -s "$LOG_DIR/tests-authoring.log" ]] || tail -5 "$LOG_DIR/tests-authoring.log" >&2
            echo "Tests: finishing the unfinished lanes now."
            tests_run_lanes || return 1
        fi
        tests_finish 0 0 || return 1
        tests_complete_mutable || return 1
    fi
    tests_check_frozen
}

# --- Completing the defect list ---------------------------------------------------------------------------------------------
# The list could not be completed while its source was being written elsewhere, so one agent call does it once both exist. Two things
# keep that call cheap. The driver puts the list and every target source in the prompt, so the agent writes the list in one step instead
# of reading its way to it, and the driver (not the agent) checks that every `find` occurs exactly once, with one retry that names the
# failures. And the call starts as soon as the implementation is done and the mutation author has finished, beside the wait for the
# slower authors, with the list's intent snapshotted first so a changed intent is still caught.
#
# It is deliberately NOT overlapped with the verification that follows. The list is a protected verification input that every command
# re-hashes, the tree fingerprint covers it, and the approval gate and attestation hash the tree: an edit landing during verification
# would halt the checks, restart them or invalidate the approval.

# The source files the list's entries target, one path per line.
tests_list_targets() {
    command -v node > /dev/null 2>&1 || return 0
    node --input-type=module -e '
import { pathToFileURL } from "node:url"; import path from "node:path"; import fs from "node:fs";
const m = await import(pathToFileURL(path.resolve(process.argv[1])).href);
const l = m.default ?? m.defects ?? m.list ?? m.mutations ?? m.injections ?? Object.values(m).find(Array.isArray) ?? [];
const seen = new Set();
for (const e of l) for (const f of [e.file, e.target]) if (typeof f === "string" && !seen.has(f) && fs.existsSync(f)) { seen.add(f); console.log(f); }
' "$1" 2> /dev/null || true
}

# Prints a problem per line when an entry cannot be run: no file/find/replace, an unreadable file, or a `find` that does not occur once.
tests_verify_list() {
    command -v node > /dev/null 2>&1 || return 0
    node --input-type=module -e '
import { pathToFileURL } from "node:url"; import path from "node:path"; import fs from "node:fs";
const m = await import(pathToFileURL(path.resolve(process.argv[1])).href);
const l = m.default ?? m.defects ?? m.list ?? m.mutations ?? m.injections ?? Object.values(m).find(Array.isArray) ?? [];
for (const e of l) {
  const id = e.id ?? e.name ?? "?", f = e.file, find = e.find;
  if (typeof f !== "string" || !(typeof find === "string" || find instanceof RegExp)) { console.log(id + ": needs a string `file` and a `find`"); continue; }
  if (typeof e.replace !== "string" || e.replace === find) { console.log(id + ": needs a `replace` that differs from `find`"); continue; }
  let text; try { text = fs.readFileSync(f, "utf8"); } catch { console.log(id + ": cannot read " + f); continue; }
  const n = typeof find === "string" ? text.split(find).length - 1 : (text.match(new RegExp(find.source, find.flags.includes("g") ? find.flags : find.flags + "g")) || []).length;
  if (n !== 1) console.log(id + ": `find` occurs " + n + " times in " + f + " (it must occur exactly once)");
}
' "$1" 2> /dev/null || true
}

# tests_complete_prompt <retry-problems-file or ""> -- the agent's whole input, written to $dir/prompt-complete.md.
tests_complete_prompt() {
    local dir prompt f src bytes; dir="$(tests_dir)"; prompt="$dir/prompt-complete.md"
    { cat "$ROOT/prompts/tests-complete.md"; printf '\n## Files to complete\n\n'; sed 's/^/- `/; s/$/`/' "$dir/mutable.paths"; } > "$prompt"
    while IFS= read -r f; do
        [[ -f "$f" ]] || continue
        { printf '\n## Current contents of `%s`\n\n```\n' "$f"; cat "$f"; printf '\n```\n'; } >> "$prompt"
        while IFS= read -r src; do
            [[ -n "$src" ]] || continue
            bytes="$(wc -c < "$src" | tr -d ' ')"
            if (( bytes > 40000 )); then printf '\n## `%s` is %s bytes: read it yourself.\n' "$src" "$bytes" >> "$prompt"; continue; fi
            { printf '\n## Source `%s`\n\n```\n' "$src"; cat "$src"; printf '\n```\n'; } >> "$prompt"
        done < <(tests_list_targets "$f")
    done < "$dir/mutable.paths"
    if [[ -n "${1:-}" && -s "$1" ]]; then
        { printf '\n## The driver rejected your previous list for these reasons. Fix exactly these entries; you may read files now.\n\n'; sed 's/^/- /' "$1"; } >> "$prompt"
    fi
}

# One completion pass, with one retry that names what the driver found wrong. Returns 0 when every entry runs and the intent is intact.
tests_complete_run() {
    local dir problems attempt f; dir="$(tests_dir)"; problems="$dir/complete-problems.txt"
    for attempt in 1 2; do
        if [[ "$attempt" == 1 ]]; then tests_complete_prompt ""; else tests_complete_prompt "$problems"; fi
        SESSION_REUSE=0 UNCLE_RUNNER_REUSE="$(tests_runner_reuse)" PROGRESS_TOTAL=0 \
            run_claude "$dir/prompt-complete.md" tests-complete > "$LOG_DIR/tests-complete.log" 2>&1 || {
                echo "Tests: completing the defect list failed; see $LOG_DIR/tests-complete.log" >&2; return 1; }
        : > "$problems"
        while IFS= read -r f; do tests_verify_list "$f" >> "$problems"; done < "$dir/mutable.paths"
        if [[ ! -s "$problems" ]] && tests_check_intent 2> "$dir/complete-intent.txt"; then return 0; fi
        [[ ! -s "$dir/complete-intent.txt" ]] || cat "$dir/complete-intent.txt" >> "$problems"
        [[ "$attempt" == 1 ]] && echo "Tests: the completed defect list has problems; asking once more:" && sed 's/^/  /' "$problems"
    done
    echo "Tests: the defect list is still incomplete:" >&2; sed 's/^/  /' "$problems" >&2
    return 1
}

tests_complete_pid_file() { printf '%s/tests/complete.pid' "$STATE_DIR"; }
tests_completion_running() {
    local pid; pid="$(cat "$(tests_complete_pid_file)" 2> /dev/null || true)"
    [[ -n "$pid" ]] && kill -0 "$pid" 2> /dev/null
}

# Start completing the list in the background if the implementation is done (the caller is the join) and the mutation author is.
tests_complete_early_start() {
    local dir; dir="$(tests_dir)"
    [[ ! -e "$dir/complete.pid" && ! -e "$dir/complete.status" ]] || return 0
    [[ -e "$dir/lane-mutation.done" && -s "$dir/lane-mutation.mutable" ]] || return 0
    grep -v '^$' "$dir/lane-mutation.mutable" > "$dir/mutable.paths"
    tests_intent_snapshot                 # the intent as authored, before anything edits the list
    touch "$dir/intent.early"
    echo "Tests: completing the defect list now, beside the remaining authors."
    ( tests_complete_run; echo "$?" > "$dir/complete.status" ) > "$LOG_DIR/tests-complete.log" 2>&1 &
    echo "$!" > "$(tests_complete_pid_file)"
}

# The list is complete before anything reads it: an early run is waited for, a missing one is run now.
tests_complete_mutable() {
    local dir; dir="$(tests_dir)"
    [[ -s "$dir/mutable.paths" ]] || return 0
    if tests_completion_running; then
        local started="$SECONDS"
        echo "Tests: waiting for the defect list to be completed..."
        while tests_completion_running; do sleep 1; done
        echo "Tests: the defect list was ready after a further $((SECONDS - started))s."
    fi
    if [[ -e "$dir/complete.status" ]]; then
        [[ "$(cat "$dir/complete.status")" == 0 ]] && tests_check_intent && return 0
        echo "Tests: the early completion of the defect list did not succeed; trying once more now." >&2
        rm -f "$dir/complete.status" "$dir/complete.pid"
    fi
    tests_check_intent 2> /dev/null && return 0
    echo "Tests: completing the defect list against the finished source."
    tests_complete_run
}

# Paths the implementation steps must not write. After the freeze: the files frozen with a content hash (paths that were absent at
# freeze time, such as the driver-supplied defect-injection runner, are NOT frozen and may appear later). Before it, in concurrent mode:
# the plan's protected scopes, because the lanes are writing there right now -- except the runner, which the driver installs.
tests_frozen_paths() {
    tests_enabled || return 0
    if tests_locked; then
        awk -F'\t' '$1 != "ABSENT" && $1 != "DIRECTORY" { print $2 }' "$(tests_lock)"
        return 0
    fi
    tests_concurrent || return 0
    [[ -s "$STATE_DIR/tests.paths" ]] || return 0
    awk '
        NF == 0 { next }
        { p = tolower($0); sub(/\/$/, "", p); n = split(p, parts, "/"); base = parts[n]; sub(/\.m?js$/, "", base) }
        (base ~ /^(run|runner|mutate|run-mutations|run_mutations|runmutations|mutation-runner|mutation_runner|run-defects|defect-runner|run-injections|inject)$/) && (p ~ /mutat|defect|inject/) { next }
        { print $0 }
    ' "$STATE_DIR/tests.paths"
}

# Shared awk prelude: load scopes from the first file, then `covered(path)` is true for an exact path or a path under a directory scope.
# The defect-injection runner is installed by the driver, never reserved, even inside a directory scope.
TESTS_AWK_COVERED='function runner(p,  q, n, parts, base) { q = tolower(p); n = split(q, parts, "/"); base = parts[n]; sub(/\.m?js$/, "", base)
  return (base ~ /^(run|runner|mutate|run-mutations|run_mutations|runmutations|mutation-runner|mutation_runner|run-defects|defect-runner|run-injections|inject)$/) && (q ~ /mutat|defect|inject/) }
function covered(p,  i, s) { if (runner(p)) return 0; for (i = 1; i <= ns; i++) { s = sc[i]; if (p == s || (substr(s, length(s)) == "/" && index(p, s) == 1)) return 1 } return 0 }'

# stdin: "step<TAB>path" ownership rows; stdout: the rows whose path is reserved. The plan assigns test files to implementation steps
# ("Engine and unit tests"); no step may be told it owns them once the tests are being (or have been) written.
tests_filter_owns() {
    local list; list="$(mktemp)"
    tests_frozen_paths > "$list"
    if [[ -s "$list" ]]; then awk -F'\t' "$TESTS_AWK_COVERED"' NR == FNR { sc[++ns] = $0; next } !covered($2)' "$list" -; else cat; fi
    rm -f "$list"
}

# stdin: unfiltered ownership rows; stdout: step numbers whose every owned path is reserved. They have nothing left to write, and must
# not be run: a step with no owned paths is treated as owning everything.
tests_frozen_only_steps() {
    local list; list="$(mktemp)"
    tests_frozen_paths > "$list"
    if [[ -s "$list" ]]; then
        awk -F'\t' "$TESTS_AWK_COVERED"' NR == FNR { sc[++ns] = $0; next } { n[$1]++; if (covered($2)) z[$1]++ } END { for (s in n) if (z[s] == n[s]) print s }' "$list" -
    fi
    rm -f "$list"
}

# stdin: unfiltered ownership rows; $1 a step number; stdout: that step's completable paths as a markdown list.
tests_mutable_for_step() {
    local list; list="$(tests_dir)/mutable.paths"
    [[ -s "$list" ]] || return 0
    tests_locked || return 0
    awk -F'\t' -v s="$1" 'NR == FNR { f[$0] = 1; next } $1 == s && ($2 in f) { print "- `" $2 "`" }' "$list" -
}

# stdin: unfiltered ownership rows; $1 a step number; stdout: that step's frozen paths as a markdown list.
tests_frozen_for_step() {
    local list; list="$(mktemp)"
    tests_frozen_paths > "$list"
    if [[ -s "$list" ]]; then
        awk -F'\t' -v s="$1" "$TESTS_AWK_COVERED"' NR == FNR { sc[++ns] = $0; next } $1 == s && covered($2) { print "- `" $2 "`" }' "$list" -
    fi
    rm -f "$list"
}

# --- Completable files ------------------------------------------------------------------------------------------------------
# A lane may declare files it can only finish after the source exists (the defect list needs exact `find` text). They are not hash
# frozen. What is frozen is their intent: each entry's id, `breaks` and expected failing tests, which the implementation must keep,
# while adding the missing fields.
tests_intent_dump() {   # $1 file; prints a JSON array, or nothing if it cannot be read
    command -v node > /dev/null 2>&1 || return 0
    node --input-type=module -e '
import { pathToFileURL } from "node:url"; import path from "node:path";
const m = await import(pathToFileURL(path.resolve(process.argv[1])).href);
const l = m.default ?? m.defects ?? m.list ?? m.mutations ?? m.injections ?? Object.values(m).find(Array.isArray);
const n = (v) => (Array.isArray(v) ? v.slice().sort() : v ?? null);
console.log(JSON.stringify((Array.isArray(l) ? l : []).map((e) => ({ id: e.id ?? e.name, breaks: n(e.breaks), expected: n(e.expected_failing_tests ?? e.expected),
  file: typeof (e.file ?? e.path ?? e.target) === "string" && typeof e.file === "string" ? e.file : null,
  find: typeof (e.find ?? e.search ?? e.pattern ?? e.from) === "string" || (e.find instanceof RegExp) }))));
' "$1" 2> /dev/null || true
}

tests_intent_snapshot() {
    local dir f out; dir="$(tests_dir)"; : > "$dir/intent.tsv"
    [[ -s "$dir/mutable.paths" ]] || return 0
    while IFS= read -r f; do
        [[ -f "$f" ]] || continue
        out="$(tests_intent_dump "$f")"
        [[ -z "$out" ]] || printf '%s\t%s\n' "$f" "$out" >> "$dir/intent.tsv"
    done < "$dir/mutable.paths"
}

# After IMPLEMENT: every intent entry survives unchanged, and now carries the fields the runner needs.
tests_check_intent() {
    local dir f was now; dir="$(tests_dir)"
    [[ -s "$dir/intent.tsv" ]] || return 0
    local bad=0
    while IFS=$'\t' read -r f was; do
        now="$(tests_intent_dump "$f")"
        if [[ -z "$now" ]]; then echo "Tests: $f no longer loads as a defect list." >&2; bad=1; continue; fi
        python3 -B - "$f" "$was" "$now" << 'PY' || bad=1
import json, sys
f, was, now = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
by = {e["id"]: e for e in now}
problems = []
for e in was:
    n = by.get(e["id"])
    if n is None:
        problems.append("%s was removed" % e["id"]); continue
    if n["breaks"] != e["breaks"] or n["expected"] != e["expected"]:
        problems.append("%s changed its breaks/expected_failing_tests (frozen intent)" % e["id"])
    if not n["file"] or not n["find"]:
        problems.append("%s still has no exact `file` + `find`" % e["id"])
if problems:
    print("Tests: %s is incomplete:" % f, file=sys.stderr)
    for p in problems: print("  " + p, file=sys.stderr)
    sys.exit(1)
PY
    done < "$dir/intent.tsv"
    [[ "$bad" == 0 ]]
}

# --- Amendments -------------------------------------------------------------------------------------------------------------------
# A frozen test that is genuinely wrong must not send the build around a repair loop it cannot win. The implementer or repair agent may
# amend it by appending `path<TAB>reason` to tests/amendments.tsv. The amendment is accepted, logged with the reason, the lock is
# refreshed, and the changed file is in the diff the human approves. An amendment with no reason is not accepted.
tests_amendments_file() { printf '%s/tests/amendments.tsv' "$STATE_DIR"; }

# After IMPLEMENT: every frozen file must still be byte-identical. New files are allowed.
tests_check_frozen() {
    tests_enabled || return 0
    tests_locked || return 0
    local actual changed amended file reason unamended="" amendments
    actual="$(tests_manifest)" || return 1
    changed="$(grep -vE '^(ABSENT|DIRECTORY)' "$(tests_lock)" | grep -vxF -f <(printf '%s\n' "$actual") || true)"
    if [[ -n "$changed" ]]; then
        amendments="$(tests_amendments_file)"
        while IFS=$'\t' read -r _ file; do
            [[ -n "$file" ]] || continue
            reason=""
            [[ ! -s "$amendments" ]] || reason="$(awk -F'\t' -v f="$file" '$1 == f && $2 != "" { r = $2 } END { print r }' "$amendments")"
            if [[ -n "$reason" ]]; then
                printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$file" "$reason" >> "$(tests_dir)/amendments.log"
                echo "Tests: frozen file $file amended: $reason"
                amended="${amended:-}1"
            else
                unamended="${unamended}  $file"$'\n'
            fi
        done <<< "$changed"
        if [[ -n "$unamended" ]]; then
            echo >&2
            echo "Tests: the implementation changed or deleted frozen tests without recording an amendment:" >&2
            printf '%s' "$unamended" >&2
            echo "Restore them (git checkout), or append \`<path><TAB><reason>\` to $(tests_amendments_file) if the test is wrong," >&2
            echo "and the change will be accepted and shown at the approval gate. To re-author instead, delete $(tests_lock)." >&2
            return 1
        fi
        tests_manifest > "$(tests_lock)"   # accept the amended content as the new frozen state
    fi
    tests_check_intent || return 1
    return 0
}
