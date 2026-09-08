#!/usr/bin/env bash
# Approved path scopes cover tests, fixtures/oracles, helpers and test config.
# Verification may produce reports, but must not change these inputs.
. "$(dirname "${BASH_SOURCE[0]}")/sha256.sh"
VERIFICATION_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The heading is matched the way verify_commands matches its own: by the words
# it contains, at any level, with or without a section number. An exact-string
# match cost a run and a human approval when a plan said "## Protected paths"
# -- the block was there, correct, and unreadable for one missing word.
verification_paths() {
    awk '
        /^#+[ \t]/ {
            h = tolower($0)
            sub(/\r$/, "", h)
            if (index(h, "protected") > 0 && index(h, "paths") > 0) {
                section = 1; sections++; next
            }
        }
        section && /^```/ {
            if (opened) { closed=1; section=0 } else opened=1
            next
        }
        section && opened { sub(/\r$/, ""); if (NF) { print; rows++ }; next }
        section && /^#/ { section=0 }
        END { if (sections != 1 || !opened || !closed || !rows) exit 1 }
    ' "$1"
}

# Prints one deterministic manifest. Directory inventories detect additions
# and deletions as well as edits. Python bytecode is not a verification input.
verification_manifest() {
    case "${WORKFLOW_HASH_BACKEND:-auto}" in
        auto|python)
            if command -v python3 > /dev/null 2>&1 && [[ -f "$VERIFICATION_LIB_DIR/verification_manifest.py" ]]; then
                python3 -B "$VERIFICATION_LIB_DIR/verification_manifest.py" "$1"
                return $?
            elif [[ "${WORKFLOW_HASH_BACKEND:-auto}" == python ]]; then
                echo 'Python manifest backend is unavailable.' >&2
                return 1
            fi
            ;;
        shell) ;;
        *) echo 'WORKFLOW_HASH_BACKEND must be auto, python, or shell.' >&2; return 1 ;;
    esac
    verification_manifest_shell "$1"
}

verification_manifest_shell() {
    local paths="$1" path file component prefix digest links directory_only
    while IFS= read -r path; do
        directory_only=0
        if [[ "$path" == */ ]]; then
            directory_only=1
            path="${path%/}"
        fi
        case "$path" in
            ''|-*|/*|*/../*|../*|*/..|..|.|./*|*/./*|*/.|*//*|*/|*$'\t'*|.git|.git/*|.uncle|.uncle/*)
                echo "Invalid protected verification path: $path" >&2; return 1 ;;
        esac
        # Reject symlinks in any component; otherwise the scope can escape the
        # project or omit inputs because find does not follow directory links.
        prefix=""
        while IFS= read -r component; do
            prefix="${prefix:+$prefix/}$component"
            if [[ -L "$prefix" ]]; then
                echo "Protected verification path uses a symlink: $prefix" >&2; return 1
            fi
        done < <(printf '%s\n' "$path" | tr '/' '\n')
        if [[ -d "$path" ]]; then
            links="$(find "$path" -type l -print)" || return 1
            if [[ -n "$links" ]]; then
                echo "Protected verification directory contains symlinks: $path" >&2; return 1
            fi
            printf 'DIRECTORY\t%s\n' "$path"
            find "$path" -type f ! -name '*.pyc' ! -path '*/__pycache__/*' -print || return 1
        elif [[ -f "$path" && "$directory_only" == 0 ]]; then
            printf '%s\n' "$path"
        else
            echo "Missing protected verification path: $path" >&2; return 1
        fi
    done < "$paths" | LC_ALL=C sort -u | while IFS= read -r file; do
        case "$file" in
            DIRECTORY$'\t'*) printf '%s\n' "$file" ;;
            *$'\t'*) echo "Tabs are not supported in protected paths." >&2; return 1 ;;
            *)
                [[ -f "$file" ]] || return 1
                digest="$(hash_file "$file")" || return 1
                [[ -n "$digest" ]] || return 1
                printf '%s\t%s\n' "$digest" "$file"
                ;;
        esac
    done
}
