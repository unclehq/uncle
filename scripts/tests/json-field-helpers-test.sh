#!/usr/bin/env bash
# json_field.py replaced two inline python scripts in green-check.sh. The originals are kept below as the oracle: for every input the new
# helper must give the same stdout and the same exit status.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok() { PASS=$((PASS + 1)); }
bad() { FAIL=$((FAIL + 1)); echo "FAIL [$1] $2"; }

old_commands() {
python3 - "$1" <<'PY'
import json, sys
try:
    payload = json.load(open(sys.argv[1], encoding='utf-8'))
    commands = payload.get('verification_commands', '')
    if not isinstance(commands, str):
        raise ValueError('verification_commands is not a string')
    print(commands.rstrip())
except Exception:
    raise SystemExit(1)
PY
}
old_narrative() { python3 -c 'import json,sys; sys.stdout.write(json.load(open(sys.argv[1])).get("narrative") or "")' "$1"; }

i=0
while IFS= read -r -d '' body; do
    i=$((i + 1)); printf '%s' "$body" > "$TMP/in.$i"
    for mode in commands narrative; do
        helper_mode=$([[ $mode == commands ]] && echo verification-commands || echo narrative)
        want="$(old_$mode "$TMP/in.$i" 2>/dev/null; echo "rc=$?")"
        got="$(python3 "$ROOT/scripts/lib/json_field.py" "$helper_mode" "$TMP/in.$i" 2>/dev/null; echo "rc=$?")"
        [[ "$want" == "$got" ]] && ok || bad "$mode-$i" "want [$want] got [$got] for $(printf '%q' "$body")"
    done
done < <(printf '%s\0' '{"verification_commands":"bash a.sh\nbash b.sh\n\n","narrative":"## Plan\ntext é ü\n"}' '{"verification_commands":""}' '{}' \
    '{"verification_commands":7,"narrative":null}' '{"verification_commands":null}' '{"narrative":""}' '{"narrative":"no trailing newline"}' \
    '[1,2,3]' 'not json' '' '{"narrative":["a"]}' '{"verification_commands":"  padded  \n  \n"}' '"just a string"' 'null')
for mode in verification-commands narrative; do
    old=$([[ $mode == verification-commands ]] && echo commands || echo narrative)
    want="$(old_$old "$TMP/missing" 2>/dev/null; echo "rc=$?")"; got="$(python3 "$ROOT/scripts/lib/json_field.py" $mode "$TMP/missing" 2>/dev/null; echo "rc=$?")"
    [[ "$want" == "$got" ]] && ok || bad "missing-file-$mode" "want [$want] got [$got]"
done
if [[ "$FAIL" -ne 0 ]]; then echo "json-field-helpers-test.sh: $FAIL failed"; exit 1; fi
echo "json-field-helpers-test.sh: $PASS cases match the inline originals"
