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
    printf '%s' "$out" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    raise SystemExit(1)
groups = d.get("groups") or []
# Nothing to gain, and nothing to risk, when no group holds more than one step.
if not d.get("steps_declaring_ownership") or max((len(g) for g in groups), default=0) < 2:
    raise SystemExit(1)
for g in groups:
    print(" ".join(str(n) for n in g))
' || return 1
}

# parallel_run_group <lib> <log-dir> <plan> <group steps...> — run one group
# concurrently and merge it. Nonzero means the caller must stop: either a step
# failed or the plan's partition was wrong, and both leave the tree untouched.
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
print(json.dumps(owned))' "$lib")"
    allowlist_json="$(UNCLE_LIB="$lib" python3 -B -c '
import json, os, sys
sys.path.insert(0, os.environ["UNCLE_LIB"])
import supervisor
print(json.dumps(list(supervisor.load_config(".uncle/config").files_allowlist)))')"
    steps_json="$(python3 -B -c '
import json, sys
logdir, plan, lib = sys.argv[1], sys.argv[2], sys.argv[3]
steps = []
for n in sys.argv[4:]:
    steps.append({"number": int(n),
                  "log": "%s/implementation-step-%s.log" % (logdir, n),
                  "note": ".uncle/workflow/parallel/notes/step-%s.md" % n,
                  "command": ["bash", "%s/parallel-agent.sh" % lib, n]})
print(json.dumps(steps))' "$logdir" "$plan" "$lib" "$@")"
    printf '{"project": "%s", "owned": %s, "steps": %s, "files_allowlist": %s}\n' \
        "$PWD" "$owned_json" "$steps_json" "${allowlist_json:-[]}" > "$request"
    python3 -B "$lib/parallel_steps.py" "$request" || rc=$?
    rm -f "$request"
    return "$rc"
}
