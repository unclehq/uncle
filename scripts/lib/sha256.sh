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
    hash_file() {
        if command -v shasum > /dev/null 2>&1; then
            shasum -a 256 "$1" | awk '{print $1}'
        elif command -v sha256sum > /dev/null 2>&1; then
            sha256sum "$1" | awk '{print $1}'
        elif command -v openssl > /dev/null 2>&1; then
            openssl dgst -sha256 "$1" | awk '{print $NF}'
        else
            echo "no sha256 tool found: install shasum, sha256sum, or openssl" >&2
            return 1
        fi
    }
fi
