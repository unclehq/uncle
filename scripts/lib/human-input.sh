#!/usr/bin/env bash
# Take the human inputs a preflight blocker is waiting on, at the gate, and put
# them where the next run looks.
#
# The alternative was hand-editing markdown between runs, which is how a path
# ends up spelled two ways and a stage reports "absent" for something that
# exists. The popup collects; this applies. Keeping them apart means the file
# writing is testable without a terminal, and a curses loop never writes to the
# project.
HUMAN_INPUT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# collect_human_inputs <report> <out> <id>... -- draw the dialog.
#   0 something was provided, 1 nothing was, 2 no terminal to draw on.
collect_human_inputs() {
    local report="$1" out="$2"
    shift 2
    local popup="$HUMAN_INPUT_LIB_DIR/human-input-popup.py"
    [[ -f "$popup" ]] || return 2
    command -v python3 > /dev/null 2>&1 || return 2
    local -a specs=()
    local id
    for id in "$@"; do
        # Each blocker reaches the dialog with the evidence it was blocked on,
        # which is where the path it needs is usually already written down.
        specs+=("$(printf '%s\t%s\t%s' "$id" \
            "$(acceptance_row_status "$report" "$id")" \
            "$(acceptance_row_evidence "$report" "$id")")")
    done
    python3 "$popup" --report "$report" --out "$out" "${specs[@]}"
}

# apply_human_inputs <records> -- act on what the dialog collected.
#
# A statement becomes a dated record that says it was entered by the operator
# at the preflight gate. That provenance is the whole value of the file: a
# later stage, and the final audit, must be able to see who said it and when,
# and must not mistake it for something a tool established.
apply_human_inputs() {
    local records="$1" id action target payload applied=0
    [[ -s "$records" ]] || return 1
    while IFS="$(printf '\t')" read -r id action target payload; do
        [[ -n "$id" && -n "$target" ]] || continue
        case "$action" in
            statement)
                mkdir -p "$(dirname "$target")" || return 1
                {
                    printf '# %s\n\n' "$id"
                    printf 'Recorded by the operator at the preflight gate.\n'
                    printf 'When: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                    printf 'Prerequisite: %s\n\n' "$id"
                    printf '%s\n' "$payload"
                } > "$target" || return 1
                echo "  $id: statement recorded in $target"
                applied=$((applied + 1))
                ;;
            copy)
                if [[ ! -e "$payload" ]]; then
                    echo "  $id: $payload does not exist; nothing copied" >&2
                    continue
                fi
                mkdir -p "$(dirname "$target")" || return 1
                cp -R "$payload" "$target" || return 1
                echo "  $id: copied $payload to $target"
                applied=$((applied + 1))
                ;;
            *) ;;
        esac
    done < "$records"
    [[ "$applied" -gt 0 ]]
}
