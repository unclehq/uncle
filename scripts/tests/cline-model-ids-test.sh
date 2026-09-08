#!/usr/bin/env bash
# Every model id the Configure picker offers has to be one cline knows.
#
# The picker writes its id straight into .uncle/config and on to `cline -m`,
# where a wrong one fails the stage at startup -- after the operator has
# chosen it, and with an error about model format rather than about the
# picker. cline ships its catalogue in @cline/llms, so the ids can be checked
# against it here instead of at the point of failure.
#
# Skipped when cline is not installed: this checks uncle against a local
# cline, and cannot check it against one that is not there.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if ! command -v cline > /dev/null 2>&1; then
    echo "cline-model-ids-test.sh: skipped, cline is not installed"
    exit 0
fi
resolved="$(command -v cline)"
while [ -L "$resolved" ]; do
    link="$(readlink "$resolved")"
    case "$link" in
        /*) resolved="$link" ;;
        *)  resolved="$(cd "$(dirname "$resolved")" && cd "$(dirname "$link")" && pwd)/$(basename "$link")" ;;
    esac
done
catalog="$(cd "$(dirname "$resolved")/../node_modules/@cline/llms/dist" 2>/dev/null && pwd || true)"
if [[ -z "$catalog" || ! -f "$catalog/models.js" ]]; then
    echo "cline-model-ids-test.sh: skipped, cline's model catalogue was not found"
    exit 0
fi

ids="$(UNCLE_TUI="$ROOT/uncle_tui.py" python3 - <<'PY'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("tui", os.environ["UNCLE_TUI"])
m = importlib.util.module_from_spec(spec); sys.modules["tui"] = m
spec.loader.exec_module(m)
seen = []
for _group, entries in m.MODEL_CATALOG:
    for _label, mid in entries:
        if mid not in seen:
            seen.append(mid)
for mid in seen:
    print(mid)
PY
)"

[ -n "$ids" ] || { echo "FAIL: the picker offers no model ids at all" >&2; exit 1; }

missing=0
count=0
while IFS= read -r id; do
    [ -n "$id" ] || continue
    count=$((count + 1))
    if ! grep -qF -- "\"$id\"" "$catalog"/*.js 2>/dev/null \
        && ! grep -qF -- "$id" "$catalog"/*.js 2>/dev/null; then
        echo "FAIL: $id is offered by the picker but is not in cline's catalogue" >&2
        missing=$((missing + 1))
    fi
done <<< "$ids"

[ "$missing" -eq 0 ] || exit 1

# And a deliberately fake id must be reported missing, or the check above is
# just counting files.
if grep -qF -- "definitely-not-a-vendor/definitely-not-a-model" "$catalog"/*.js 2>/dev/null; then
    echo "FAIL: the catalogue search matches anything" >&2
    exit 1
fi

echo "cline-model-ids-test.sh: all $count picker model ids exist in cline's catalogue"
