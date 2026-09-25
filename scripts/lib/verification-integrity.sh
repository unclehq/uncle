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
    local line rest token candidate emitted raw json_path json_name
    # Plans are JSON-authoritative.  Rendering is for approval/review only;
    # never parse a rendered view when the canonical plan exists.
    json_name="$(basename "$1" .md).json"
    json_path="${STATE_DIR:-.uncle/workflow}/documents/$json_name"
    if [[ -f "$json_path" ]]; then
        python3 - "$json_path" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    payload = json.load(open(path, encoding='utf-8'))
    paths = payload['protected_verification_paths']
except (OSError, ValueError, KeyError, TypeError) as error:
    raise SystemExit('Invalid canonical protected verification paths: %s' % error)
if not isinstance(paths, str) or not paths.strip():
    raise SystemExit('Invalid canonical protected verification paths: expected a nonempty string')
for value in paths.splitlines():
    value = value.strip()
    normalized = value[:-1] if value.endswith('/') else value
    if (not value or ',' in value or value.startswith(('/', '-')) or '//' in value
            or '\\' in value or any(part in ('', '.', '..') for part in normalized.split('/'))
            or normalized == '.git' or normalized.startswith('.git/')
            or normalized == '.uncle' or normalized.startswith('.uncle/')):
        raise SystemExit('Invalid canonical protected verification path: %s' % value)
    print(value)
PY
        return $?
    fi
    raw="$(awk '
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
    ' "$1")" || return 1
    while IFS= read -r line; do
        emitted=0
        rest="$line"
        # Some older plan prompts asked for a prose sentence containing
        # backticked paths.  Recover those explicit paths deterministically;
        # never treat the surrounding sentence as a filesystem path.
        while [[ "$rest" == *'`'*'`'* ]]; do
            rest="${rest#*\`}"
            token="${rest%%\`*}"
            rest="${rest#*\`}"
            case "$token" in
                lockfile) token=package-lock.json ;;
                playwright.config.'*')
                    token=playwright.config.js
                    for candidate in playwright.config.js playwright.config.ts playwright.config.mjs playwright.config.cjs; do
                        if [[ -e "$candidate" ]]; then token="$candidate"; break; fi
                    done
                    ;;
                vite.config.'*')
                    token=vite.config.js
                    for candidate in vite.config.js vite.config.ts vite.config.mjs vite.config.cjs; do
                        if [[ -e "$candidate" ]]; then token="$candidate"; break; fi
                    done
                    ;;
            esac
            [[ -n "$token" ]] || return 1
            printf '%s\n' "$token"
            emitted=1
        done
        [[ "$emitted" == 1 ]] || printf '%s\n' "$line"
    done <<< "$raw"
}

# Prints one deterministic manifest. Directory inventories detect additions
# and deletions as well as edits. Python bytecode is not a verification input.
verification_manifest() {
    local result status
    case "${WORKFLOW_HASH_BACKEND:-auto}" in
        auto|python)
            if command -v python3 > /dev/null 2>&1 && [[ -f "$VERIFICATION_LIB_DIR/verification_manifest.py" ]]; then
                if result=$(python3 -B "$VERIFICATION_LIB_DIR/verification_manifest.py" "$1"); then
                    [[ -z "$result" ]] || printf '%s\n' "$result"
                    return 0
                else
                    status=$?
                fi
                # Keep the successful path to one Python startup. Only probe
                # after failure: a Store alias can exist without working Python.
                # A working interpreter's manifest error must remain fatal.
                if python3 -c 'pass' >/dev/null 2>&1; then
                    return "$status"
                fi
                if [[ "${WORKFLOW_HASH_BACKEND:-auto}" == python ]]; then
                    echo 'Python manifest backend is unavailable.' >&2
                    return "$status"
                fi
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
    local paths="$1" path file component prefix digest links directory_only absent_paths scope
    absent_paths="${WORKFLOW_ALLOW_ABSENT_PROTECTED_DIRECTORIES:-}"
    while IFS= read -r path; do
        scope="$path"
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
        elif [[ -n "$absent_paths" && -f "$absent_paths" ]] \
            && grep -Fqx -- "$scope" "$absent_paths"; then
            # An initial build can legitimately introduce both source/test
            # files and directories named by its approved plan.  Record an
            # absent input explicitly instead of routing a missing pre-build
            # file to REPAIR. Its appearance/disappearance after this first
            # snapshot still changes the manifest.
            printf 'ABSENT\t%s\n' "$path"
        else
            echo "Missing protected verification path: $path" >&2; return 1
        fi
    done < "$paths" | LC_ALL=C sort -u | while IFS= read -r file; do
        case "$file" in
            DIRECTORY$'\t'*|ABSENT$'\t'*) printf '%s\n' "$file" ;;
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
