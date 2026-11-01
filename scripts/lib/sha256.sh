# Portable sha256 of a file.
#
# The approval records are digests, so every script that opens or checks a gate
# needs one. macOS ships `shasum` (perl) and no `sha256sum`; Linux ships
# `sha256sum` (coreutils) and not always `shasum`; `openssl` covers whatever is
# left. Assuming one of them is how a workflow that runs everywhere stops
# running anywhere.
#
# Sourced by the drivers and by the libs that hash on their own, so it is
# guarded against being sourced twice.

if ! declare -f hash_file > /dev/null 2>&1; then
    # The digest is taken from the tool's own output with parameter expansion, not awk, and sha256sum is tried first: shasum is
    # a Perl script, and hashing a file once cost two launches and ~15 ms against ~2 ms here. The drivers hash on every approval
    # and gate check, so this runs thousands of times in a build. Exit status follows what the old `tool | awk` pipeline gave:
    # the tool's failure counts only when pipefail is on.
    hash_file() {
        local out status=0
        if command -v sha256sum > /dev/null 2>&1; then
            out="$(sha256sum "$1")" || status=$?
            out="${out%% *}"
        elif command -v shasum > /dev/null 2>&1; then
            out="$(shasum -a 256 "$1")" || status=$?
            out="${out%% *}"
        elif command -v openssl > /dev/null 2>&1; then
            out="$(openssl dgst -sha256 "$1")" || status=$?
            out="${out##* }"
        else
            echo "no sha256 tool found: install shasum, sha256sum, or openssl" >&2
            return 1
        fi
        printf '%s\n' "$out"
        if [[ -o pipefail ]]; then return "$status"; fi
        return 0
    }
fi
