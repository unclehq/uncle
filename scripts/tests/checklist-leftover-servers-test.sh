#!/usr/bin/env bash
# A manual-checklist worker can leave its own `vite preview` running, which then blocks a later run's Playwright
# webServer on the same port. Both drivers' post-workers hook must stop the project's leftovers via port_guard.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FAILED=0
check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else FAILED=1; echo "FAIL $1"; fi; }
for pair in "stagegate.sh:_stagegate_execute_checklist_stop_app_server" "change-workflow.sh:_change_execute_checklist_stop_app_server"; do
    file="${pair%%:*}"; fn="${pair##*:}"
    body="$(sed -n "/^$fn() {/,/^}/p" "$ROOT/scripts/$file")"
    check "$file hook stops the driver's app server" yes "$([[ "$body" == *'app_server.py'*stop* ]] && echo yes || echo no)"
    check "$file hook runs port_guard on the verification commands" yes \
        "$([[ "$body" == *'port_guard.py'* && "$body" == *'green-check.commands'* ]] && echo yes || echo no)"
    check "$file hook cannot fail the stage" yes "$([[ "$body" == *'|| true'* ]] && echo yes || echo no)"
done
exit "$FAILED"
