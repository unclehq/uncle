#!/usr/bin/env bash
# Approved path scopes cover tests, fixtures/oracles, helpers and test config.
# Verification may produce reports, but must not change these inputs.
. "$(dirname "${BASH_SOURCE[0]}")/sha256.sh"

verification_paths() {
    awk '
        /^## Protected verification paths[ \t\r]*$/ { section=1; sections++; next }
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
    local paths="$1" path file component prefix digest links
    while IFS= read -r path; do
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
        elif [[ -f "$path" ]]; then
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
