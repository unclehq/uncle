#!/usr/bin/env bash
# Explicit source lists for workflow harnesses. Callers supply state and hooks;
# this helper never sources a driver or initializes a repository.
workflow_fixture_source() {
    local workflow_fixture_module
    for workflow_fixture_module in "$@"; do
        . "$workflow_fixture_module" || return
    done
}

# Write a harness entry point with an explicit, ordered module list. Absolute
# paths keep it usable when a test deliberately supplies a different ROOT.
workflow_fixture_write() {
    local out="$1"
    shift
    [[ "$#" -gt 0 ]] || { echo "FATAL: empty fixture module list" >&2; return 2; }
    {
        printf '. %q\n' "$ROOT/scripts/tests/workflow_fixture.sh"
        printf 'workflow_fixture_source'
        printf ' %q' "$@"
        printf '\n'
    } > "$out"
}

# Transitional only: remove a name from this interface in the same change
# that moves its production definition into a sourceable library.
extract_fns() {
    local script="$1" out="$2"
    shift 2
    [[ "$#" -gt 0 ]] || { echo "FATAL: empty fixture function list" >&2; return 2; }
    : > "$out"
    local fn
    for fn in "$@"; do
        awk -v fn="$fn" '
            $0 == fn "() {" { p = 1 }
            p { print }
            p && /^\}$/ { exit }
        ' "$script" >> "$out"
        printf '\n' >> "$out"
        if ! grep -q "^${fn}() {" "$out"; then
            echo "FATAL: could not extract $fn from $script" >&2
            exit 2
        fi
    done
    if ! bash -n "$out"; then
        echo "FATAL: extracted functions from $script are not valid bash" >&2
        exit 2
    fi
}
