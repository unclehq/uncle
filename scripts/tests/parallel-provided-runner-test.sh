#!/usr/bin/env bash
set -euo pipefail

# A step that owns only the defect-injection runner is supplied by the driver
# (parallel-provided.sh, no model call); any other step still goes to an agent.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT/scripts/lib/parallel-implement.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
LIB="$TMP/lib"
mkdir -p "$LIB"
for f in "$ROOT"/scripts/lib/*; do ln -s "$f" "$LIB/$(basename "$f")"; done
rm "$LIB/parallel_steps.py"
printf 'import json, sys\njson.dump(json.load(open(sys.argv[1])), open("request.json", "w"))\n' > "$LIB/parallel_steps.py"

mkdir -p "$TMP/p/.uncle" && cd "$TMP/p"
cat > plan.md <<'P'
## Implementation sequence

1. Core — Owns: `src/a.js`
2. Mutation runner — Owns: `tests/mutations/run.mjs`
3. Mutations and core — Owns: `tests/mutations/run.mjs`, `src/b.js`
P

fail=0
run() { rm -f request.json; parallel_run_group "$LIB" "$TMP/logs" plan.md 1 2 3 > /dev/null 2>&1 || true; }
cmd() { python3 -B -c 'import json,sys; s={x["number"]:x["command"] for x in json.load(open("request.json"))["steps"]}; print(" ".join(s[int(sys.argv[1])]))' "$1"; }

run
case "$(cmd 1)" in *parallel-agent.sh\ 1) ;; *) echo "FAIL: ordinary step must go to an agent" >&2; fail=1 ;; esac
case "$(cmd 2)" in *parallel-provided.sh\ 2\ tests/mutations/run.mjs) ;; *) echo "FAIL: runner-only step must be driver-supplied: $(cmd 2)" >&2; fail=1 ;; esac
case "$(cmd 3)" in *parallel-agent.sh\ 3) ;; *) echo "FAIL: a step with other files must go to an agent" >&2; fail=1 ;; esac

WORKFLOW_PROVIDED_MUTATION_RUNNER=0 run
case "$(cmd 2)" in *parallel-agent.sh\ 2) ;; *) echo "FAIL: switch off must send the step to an agent" >&2; fail=1 ;; esac

[[ "$fail" == 0 ]] && echo "OK"
exit "$fail"
