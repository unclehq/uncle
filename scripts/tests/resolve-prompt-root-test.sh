#!/usr/bin/env bash
# A relative driver prompt resolves to the driver's copy, even from a project that has its own prompts/ directory.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
mkdir -p "$work/project/prompts/change"; echo stale > "$work/project/prompts/change/test-review.md"
echo mine > "$work/project/local-only.md"
fail=0
for family in app change; do
    got="$(cd "$work/project" && ROOT="$ROOT" bash -c ". '$ROOT/scripts/lib/workflow-paths-$family.sh'; resolve_prompt prompts/change/test-review.md")"
    [[ "$got" == "$ROOT/prompts/change/test-review.md" ]] || { echo "FAIL: $family resolved to $got" >&2; fail=1; }
    got="$(cd "$work/project" && ROOT="$ROOT" bash -c ". '$ROOT/scripts/lib/workflow-paths-$family.sh'; resolve_prompt local-only.md")"
    [[ "$got" == local-only.md ]] || { echo "FAIL: $family changed a project-local relative path to $got" >&2; fail=1; }
    got="$(cd "$work/project" && ROOT="$ROOT" bash -c ". '$ROOT/scripts/lib/workflow-paths-$family.sh'; resolve_prompt /abs/x.md")"
    [[ "$got" == /abs/x.md ]] || { echo "FAIL: $family changed an absolute path to $got" >&2; fail=1; }
done
[[ $fail == 0 ]] && echo "resolve-prompt-root-test.sh: ok"
exit $fail
