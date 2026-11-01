#!/usr/bin/env bash
# Group-at-a-time implementation, when the plan says which files each step owns.
#
# On by default whenever the approved plan proves independent ownership. Set
# WORKFLOW_PARALLEL_IMPLEMENT=0, or `misc.parallel_implement false` in
# .uncle/config, to opt out for good: a plan whose ownership declarations are
# wrong repeatedly costs an operator a stopped run and a manual plan edit far
# more often than a correct partition saves wall clock, and unlike the other
# knobs here this one is a standing choice about a whole project, not a
# single run. A plan that does not declare ownership, or has no multi-step
# group, remains serial anyway because there is no safe parallel schedule to
# execute.
#
# The grouping is the plan's statement, not this code's guess, and a group that
# writes outside its declaration is refused whole. Both properties live in
# step_groups.py and parallel_steps.py; this file only decides when to use them.

# parallel_implement_enabled — resolved per call, not once at source time:
# parallel-implement.sh is sourced before stage-config.sh in stagegate.sh, so
# uncle_config_get would not exist yet if this were a top-level assignment.
# WORKFLOW_PARALLEL_IMPLEMENT, when set, always wins over the saved config.
parallel_implement_enabled() {
    if [[ -n "${WORKFLOW_PARALLEL_IMPLEMENT:-}" ]]; then
        [[ "$WORKFLOW_PARALLEL_IMPLEMENT" == "1" ]]
        return
    fi
    if declare -f uncle_config_get > /dev/null; then
        case "$(uncle_config_get misc.parallel_implement)" in
            false|False|FALSE|0) return 1 ;;
        esac
    fi
    return 0
}

# parallel_groups <plan> <lib-dir> — one group per line, space-separated step
# numbers. Prints nothing (and fails) when parallel implementation is off, the
# plan declares no ownership, or every group holds a single step -- in all of
# which the caller should run steps one at a time exactly as before.
parallel_groups() {
    local plan="$1" lib="$2" out
    parallel_implement_enabled || return 1
    [[ -s "$plan" ]] || return 1
    out="$(UNCLE_LIB="$lib" python3 -B "$lib/step_groups.py" "$plan" "$PWD" 2>/dev/null)" || return 1
    # Steps that only run the test suites are not implementation work (the driver runs those commands itself afterwards);
    # drop them from the groups so a model session is not spent running the whole regression block.
    local skip=""
    if declare -F plan_steps > /dev/null; then
        skip="$(plan_steps "$plan" 2>/dev/null | python3 -B "$lib/verification_steps.py" skip-set - 2>/dev/null || true)"
    fi
    printf '%s' "$out" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    raise SystemExit(1)
skip = set(sys.argv[1].split())
groups = [[n for n in g if str(n) not in skip] for g in (d.get("groups") or [])]
groups = [g for g in groups if g]
# Nothing to gain, and nothing to risk, when no group holds more than one step.
if not d.get("steps_declaring_ownership") or max((len(g) for g in groups), default=0) < 2:
    raise SystemExit(1)
for g in groups:
    print(" ".join(str(n) for n in g))
' "$skip" || return 1
}

# parallel_merge_map <plan> <lib-dir> <group> -- JSON {"primary": [absorbed...]} naming the application steps of one group that a
# single worker writes (WORKFLOW_IMPLEMENT_MERGE_APP=1; see step_groups.py). `{}` when off, when nothing merges, or on any failure.
parallel_merge_map() {
    local plan="$1" lib="$2" group="$3" out
    # shellcheck disable=SC2086
    out="$(python3 -B "$lib/step_groups.py" merge-map "$plan" $group 2>/dev/null)" || out=""
    [[ "$out" == \{*\} ]] && printf '%s' "$out" || printf '{}'
}

# parallel_run_group <lib> <log-dir> <plan> <group steps...> — run one group
# concurrently and merge it. Execution or ownership failures leave the tree
# untouched. A failed fast check stops advancement but preserves the merged files.
parallel_run_group() {
    local lib="$1" logdir="$2" plan="$3"; shift 3
    local request steps_json owned_json allowlist_json rc=0
    request="$(mktemp)"
    owned_json="$(UNCLE_PLAN="$plan" python3 -B -c '
import json, os, subprocess, sys
lib = sys.argv[1]
rows = subprocess.run(["bash", "-c", ". \"%s/plan-scope.sh\"; plan_step_owns \"%s\"" % (lib, os.environ["UNCLE_PLAN"])],
                      capture_output=True, text=True).stdout.splitlines()
owned = {}
for line in rows:
    if "\t" in line:
        n, path = line.split("\t", 1)
        owned.setdefault(n, []).append(path.strip())
# Application steps merged into one worker (step_groups.py merge-map): the worker owns all their files, and the absorbed
# steps stop being separate owners, or the same file would be claimed twice.
for primary, absorbed in json.loads(os.environ.get("UNCLE_STEP_MERGE") or "{}").items():
    for step in absorbed:
        owned[primary] = owned.get(primary, []) + owned.pop(str(step), [])
print(json.dumps(owned))' "$lib")"
    allowlist_json="$(UNCLE_LIB="$lib" python3 -B -c '
import json, os, sys
sys.path.insert(0, os.environ["UNCLE_LIB"])
import supervisor
print(json.dumps(list(supervisor.load_config(".uncle/config").files_allowlist)))')"
    steps_json="$(UNCLE_OWNED="$owned_json" python3 -B -c '
import json, os, re, sys
logdir, plan, lib = sys.argv[1], sys.argv[2], sys.argv[3]
owned = json.loads(os.environ.get("UNCLE_OWNED") or "{}")
RUNNER = {"run", "runner", "mutate", "run-mutations", "run_mutations", "runmutations", "mutation-runner", "mutation_runner",
          "run-defects", "defect-runner", "run-injections", "inject"}

def provided(paths):
    """The path of the defect-injection runner when this step owns nothing else: the driver supplies that file (mutation_runner.mjs)."""
    if len(paths) != 1:
        return None
    path = paths[0].strip()
    match = re.match(r"^(?:.*/)?([^/]+)\.m?js$", path)
    if not match or match.group(1).lower() not in RUNNER:
        return None
    if not re.search(r"mutat|defect|inject", path.lower()):
        return None
    return path

steps = []
for n in sys.argv[4:]:
    command = ["bash", "%s/parallel-agent.sh" % lib, n]
    target = provided(owned.get(n, []))
    if target and os.environ.get("WORKFLOW_PROVIDED_MUTATION_RUNNER", "1") == "1":
        command = ["bash", "%s/parallel-provided.sh" % lib, n, target]
    steps.append({"number": int(n),
                  "log": "%s/implementation-step-%s.log" % (logdir, n),
                  "note": ".uncle/workflow/parallel/notes/step-%s.json" % n,
                  "command": command})
print(json.dumps(steps))' "$logdir" "$plan" "$lib" "$@")"
    printf '{"project": "%s", "owned": %s, "steps": %s, "files_allowlist": %s}\n' \
        "$PWD" "$owned_json" "$steps_json" "${allowlist_json:-[]}" > "$request"
    python3 -B "$lib/parallel_steps.py" "$request" || rc=$?
    rm -f "$request"
    if [[ "$rc" == 0 ]]; then
        # Guarded like the drivers' calls: a caller that loads only the fan-out has no step checks.
        if declare -f implementation_fast_check > /dev/null; then
            implementation_fast_check "group-$*" >&2 || return 1
        fi
    fi
    return "$rc"
}

# parallel_prewarm_start <plan> <lib-dir> — make the first group's sandboxes in the background, while the updated plan is still
# being written (parallel_steps.py prewarm).  They are used only if the tree is the one they mirror when the group starts, so this
# can only save time.  WORKFLOW_PREWARM_SANDBOXES=0 turns it off.
PARALLEL_PREWARM_PID=""
parallel_prewarm_start() {
    local plan="$1" lib="$2" first
    [[ "${WORKFLOW_PREWARM_SANDBOXES:-1}" == 1 ]] || return 0
    [[ -z "$PARALLEL_PREWARM_PID" ]] || return 0
    first="$(parallel_groups "$plan" "$lib" 2>/dev/null | head -n 1)" || return 0
    [[ -n "$first" ]] || return 0
    # shellcheck disable=SC2086
    python3 -B "$lib/parallel_steps.py" prewarm "$PWD" $first > /dev/null 2>&1 < /dev/null &
    PARALLEL_PREWARM_PID=$!
}

# parallel_prewarm_wait — implementation must not start while the early sandboxes are still being made.
parallel_prewarm_wait() {
    [[ -n "${PARALLEL_PREWARM_PID:-}" ]] || return 0
    wait "$PARALLEL_PREWARM_PID" 2>/dev/null || true
    PARALLEL_PREWARM_PID=""
}

# A landed group is a stable snapshot; tests must finish before checkpointing it.
implementation_fast_check() {
    local runner="claude"
    if declare -f stage_uses_self_hosted > /dev/null && stage_uses_self_hosted implementation AGENT; then
        runner="self-hosted"
    elif declare -f uncle_stage_runner > /dev/null; then
        runner="$(uncle_stage_runner implementation)"
    fi
    python3 -B "$ROOT/scripts/lib/implementation_fast_check.py" "$1" "$runner"
}

# Only the first approved step's paths may receive opt-in deterministic boilerplate.
implementation_scaffold_template() {
    local selected="${WORKFLOW_SCAFFOLD_TEMPLATE:-}"
    if [[ -z "${WORKFLOW_SCAFFOLD_TEMPLATE+x}" ]] && declare -f uncle_config_get > /dev/null; then
        selected="$(uncle_config_get execution.scaffold-template)"
    fi
    [[ -n "$selected" ]] || return 0
    mkdir -p "$STATE_DIR"
    plan_step_owns "$1" > "$STATE_DIR/scaffold-owns.tsv" || return 1
    WORKFLOW_SCAFFOLD_TEMPLATE="$selected" python3 -B "$ROOT/scripts/lib/scaffold_templates.py" \
        --ownership-file "$STATE_DIR/scaffold-owns.tsv"
}

# parallel_implement_run_groups <plan_doc> <prompt_builder_fn> <notes_label_prefix> [<post_group_fn>]
#
# The group-at-a-time fan-out + merge that stagegate.sh's
# run_parallel_application_implementation and change-workflow.sh's
# run_supervised_parallel_implementation each implemented independently
# before this extraction (uncle consolidation phase (b), scoped to this path
# only -- see .uncle/docs/, module-interfaces-stage.sh precedent). Both
# callers' per-step prompt bodies differ too much in wording to share (app's
# carries scaffold/ownership-boundary language that has no change-family
# analogue), so prompt construction stays a caller-supplied callback; this
# function owns exactly the risk-bearing part both drivers had copy-pasted:
# group scheduling, the parallel_run_group call, ownership-mismatch/serial-
# fallback handling, the module-interfaces derivation+injection, and the
# per-step notes-fragment merge into .uncle/docs/IMPLEMENTATION_NOTES.md.
#
# prompt_builder_fn is called once per step, as:
#     "$prompt_builder_fn" "$step" "$group" "$prompt_path" "$module_interfaces_section"
# and must write that step's complete worker prompt to $prompt_path.
#
# notes_label_prefix becomes "$notes_label_prefix $step" in the
# implementation_notes.py append label (stagegate.sh used "Isolated step $step",
# change-workflow.sh used "Step $step" -- preserved verbatim by the caller).
#
# post_group_fn, if given, is called once after each group's notes merge, as
# "$post_group_fn" "$group", so each driver records its own resume marker at
# its own existing granularity (stagegate.sh's per-group checkpoint touch,
# change-workflow.sh's per-step implement-step-done file) without this
# function assuming either family's resume semantics -- those were never
# simple path-literal differences and are deliberately left alone here.
#
# skip_group_fn, if given, is called as "$skip_group_fn" "$group" before that
# group's prompts are built; a zero return means the group was already merged
# by an earlier attempt at this same resume point and must be skipped
# entirely (no prompt rebuild, no parallel_run_group call). stagegate.sh uses
# this for its per-group checkpoint directory; change-workflow.sh resumes at
# the whole-function level instead (see its own guard before calling in) and
# passes none.
#
# Returns 0 once every group in the plan's partition has merged, 2 when there
# is no usable parallel partition at all (the caller falls back to serial
# implementation -- no groups, or the plan does not declare ownership), or
# parallel_steps.py's own nonzero exit status otherwise. A group exiting 3
# (ownership mismatch; parallel_run_group's contract: nothing was merged)
# always becomes 2 here and leaves $STATE_DIR/parallel-implementation-serial-fallback
# behind, exactly as both callers already did independently.
parallel_implement_run_groups() {
    local plan_doc="$1" prompt_builder_fn="$2" notes_label_prefix="$3" post_group_fn="${4:-}" skip_group_fn="${5:-}"
    local groups group step prompt result module_interfaces_section=""
    local serial_fallback_marker="$STATE_DIR/parallel-implementation-serial-fallback"

    if [[ -e "$serial_fallback_marker" ]]; then
        echo 'Parallel implementation was previously rejected for this plan; using serial implementation.'
        return 2
    fi
    groups="$(parallel_groups "$plan_doc" "$ROOT/scripts/lib")" || return 2
    [[ -n "$groups" ]] || return 2

    # Derivation itself now runs once in the dedicated MODULE_INTERFACES state
    # (scripts/lib/module-interfaces-stage.sh), always before IMPLEMENT is
    # reached, so this only renders whatever that state already produced
    # (or wrote nothing for, if derivation was disabled or failed -- the
    # section then stays empty, exactly as a failed/disabled derivation
    # always meant here).
    if [[ -s "$STATE_DIR/documents/MODULE_INTERFACES.json" ]]; then
        module_interfaces_section="$(python3 -B "$ROOT/scripts/lib/module_interfaces.py" --render-section \
            "$STATE_DIR/documents/MODULE_INTERFACES.json" 2>/dev/null || true)"
    fi

    mkdir -p "$STATE_DIR/parallel/prompts" "$STATE_DIR/parallel/notes"
    # STATE_DIR is already absolute; see the identical note both callers used
    # to carry here independently -- a relative prefix built a doubled path
    # when a worker's sandbox cwd differed from the driver's.
    export PARALLEL_PROMPT_DIR="$STATE_DIR/parallel/prompts"

    while IFS= read -r group; do
        [[ -n "$group" ]] || continue
        if [[ -n "$skip_group_fn" ]] && "$skip_group_fn" "$group"; then
            echo "Implementation fan-out group $group is already merged; skipping."
            continue
        fi
        # Application steps whose files name one another by string are written by one worker (merge_json), and only a
        # builder that knows how to carry the absorbed steps' text may be handed that. Absorbed steps leave the group.
        local merge_json="{}" run_group="$group" absorbed_all="" absorbed_for=""
        if [[ "${PARALLEL_BUILDER_SUPPORTS_MERGE:-0}" == 1 ]] && declare -F parallel_merge_map > /dev/null; then
            merge_json="$(parallel_merge_map "$plan_doc" "$ROOT/scripts/lib" "$group")" || merge_json="{}"
        fi
        if [[ "$merge_json" != "{}" ]]; then
            absorbed_all="$(python3 -c 'import json,sys; print(" ".join(str(s) for v in json.loads(sys.argv[1]).values() for s in v))' "$merge_json")"
            run_group=""
            for step in $group; do
                case " $absorbed_all " in *" $step "*) ;; *) run_group="${run_group:+$run_group }$step" ;; esac
            done
        fi
        for step in $run_group; do
            prompt="$STATE_DIR/parallel/prompts/step-$step.md"
            absorbed_for=""
            [[ "$merge_json" == "{}" ]] || absorbed_for="$(python3 -c 'import json,sys; print(" ".join(str(s) for s in json.loads(sys.argv[1]).get(sys.argv[2], [])))' "$merge_json" "$step")"
            UNCLE_ABSORBED_STEPS="$absorbed_for" "$prompt_builder_fn" "$step" "$group" "$prompt" "$module_interfaces_section" || return 1
            cat >> "$prompt" <<CONTRACT

## Shared implementation and test contract (binding)

Independent test suites are written concurrently with source and scaffold steps.
Use the shared interface contract above when supplied. If an exact export, data
shape, selector, fixture API, or test title is missing, read the relevant section
of the approved plan at \`$plan_doc\` before writing. This targeted contract read
is required despite the speed guidance; do not guess aliases or read sibling files
that are still being written. Keep expectations independent of implementation.
Write only your owned files. Shared configuration and helpers belong to their
assigned owners. Test execution happens after the required files are merged.

## Prepare the acceptance handoff now

For browser acceptance checks assigned to your step, write the approved reusable
probes and their \`*.acceptance.md\` handoffs during implementation, alongside
the other tests. Each handoff names requirement IDs, the exact invocation and
runtime URL argument, assertions, and observations still requiring a person.
Use the approved selector/behavior contracts while sibling UI files are being
written. Keep ownership boundaries: only the assigned test worker writes its
probe and handoff; source workers must not duplicate them. Reuse existing
helpers, keep probes out of automatic discovery unless they support that runner,
and do not install or start services just to prepare them. Use isolated browser
state/output, report actual values, and exit nonzero on assertion failure.
Do not add browser dependencies to a non-browser project. Do not claim a
prepared or unexecuted probe passed. Final-page selector confirmation and live
acceptance execution belong to Execute Checklist.
CONTRACT
        done
        if [[ "$merge_json" != "{}" ]]; then
            echo "Implementation fan-out: isolated parallel steps $run_group (application steps $absorbed_all written together with their first)."
        else
            echo "Implementation fan-out: isolated parallel steps $group."
        fi
        # A boundary violation (exit 3) is safe to recover from:
        # parallel_steps.py leaves the project untouched when it returns 3, so
        # abandon only the speculative fan-out and let serial implementation
        # own the whole tree.
        result="$(UNCLE_STEP_MERGE="$merge_json" parallel_run_group "$ROOT/scripts/lib" "$LOG_DIR" "$plan_doc" $run_group)" || {
            local parallel_status=$?
            if [[ "$parallel_status" == 3 ]]; then
                touch "$serial_fallback_marker"
                echo 'Implementation fan-out ownership mismatch; no worker changes were merged. Falling back to serial implementation.'
                return 2
            fi
            return "$parallel_status"
        }
        # Diagnostic only, and guarded unconditionally with `|| true`: this
        # must never be able to affect control flow, no matter what calling
        # context (an `if`, a `||`, or in the future a bare call) this
        # function itself runs under. Before this extraction, change-
        # workflow.sh ran the equivalent block bare with no such guard, the
        # one documented latent defect this consolidation found and closed --
        # see scripts/tests/parallel-implement-metrics-guard-test.sh.
        PARALLEL_RESULT="$result" python3 - "$group" <<'PY' || true
import json, os, sys
group = sys.argv[1]
try:
    data = json.loads(os.environ['PARALLEL_RESULT'])
except ValueError:
    print('Parallel group %s complete (result summary unavailable).' % group)
    raise SystemExit(0)
elapsed = float(data.get('elapsed_seconds', 0))
total = sum(float(v) for v in (data.get('step_seconds') or {}).values())
saved = max(0.0, total - elapsed)
files = len(data.get('files') or [])
print('Parallel group %s complete: %.1fs wall time; %.1fs worker time; '
      'estimated %.1fs saved; %d files merged; worktrees %s.' %
      (group, elapsed, total, saved, files, data.get('worktrees', 'preserved')))
PY
        for step in $run_group; do
            require_file "$STATE_DIR/parallel/notes/step-$step.json"
            python3 "$ROOT/scripts/lib/implementation_notes.py" append . \
                "$STATE_DIR/parallel/notes/step-$step.json" .uncle/docs/IMPLEMENTATION_NOTES.md \
                "$notes_label_prefix $step" || {
                supervision_validation_failed implementation-notes \
                    .uncle/docs/IMPLEMENTATION_NOTES.md "malformed fragment for step $step"
                return 1
            }
        done
        echo "Implementation fan-out group $group merged."
        [[ -z "$post_group_fn" ]] || "$post_group_fn" "$group"
    done <<< "$groups"
    return 0
}
