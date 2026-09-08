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

# collect_human_inputs <report> <out> <id>... -- ask for each blocker.
#   0 something was provided, 1 nothing was.
#
# Asked with gate_prompt and read, not with a curses window. The TUI runs the
# driver with stdin, stdout and stderr all as pipes, so the driver has no
# terminal to draw on -- and it does not need one: the TUI treats an
# unterminated line on stdout as a question, renders it as a centered dialog
# with an input line, and writes the answer back into the driver's stdin. The
# prompt protocol is the dialog. A bare terminal shows the same questions as
# plain prompts.
collect_human_inputs() {
    local report="$1" out="$2"
    shift 2
    local id answer target payload status evidence suggestion confirm
    local attempts provided=0
    : > "$out" || return 1

    for id in "$@"; do
        status="$(acceptance_row_status "$report" "$id")"
        evidence="$(acceptance_row_evidence "$report" "$id")"
        # The path the blocker needs is usually already written in its own
        # evidence, so it is offered rather than retyped by hand.
        # A path first; failing that a bare filename, which is what evidence
        # often names. A filename with no directory is offered as-is rather
        # than guessed into one.
        suggestion="$(printf '%s' "$evidence" \
            | grep -oE "[A-Za-z0-9_.-]*/[A-Za-z0-9_./-]+[.][A-Za-z0-9]+" \
            | head -1)"
        if [[ -z "$suggestion" ]]; then
            suggestion="$(printf '%s' "$evidence" \
                | grep -oE "[A-Za-z0-9_-]+[.](json|md|pdf|txt|sha256|py|csv)" \
                | head -1)"
        fi

        echo
        echo "$id  [$status]"
        [[ -z "$evidence" ]] || echo "  $evidence"
        gate_prompt "Provide $id now? 's' to record a signed statement, 'f' to copy a file in, Enter to skip: "
        IFS= read -r answer || return 1
        case "$answer" in
            s|S) ;;
            f|F) ;;
            *) echo "  skipped."; continue ;;
        esac

        target=""
        attempts=0
        # Five tries, not three: this is a person typing a path into a
        # dialog, and giving up early throws away the answers they already
        # gave for the other blockers.
        while [[ "$attempts" -lt 5 ]]; do
            attempts=$((attempts + 1))
            gate_prompt "Path to write it to${suggestion:+ [$suggestion]}: "
            IFS= read -r target || return 1
            [[ -n "$target" ]] || target="$suggestion"
            if [[ -z "$target" ]]; then
                echo "  no path given, and none to suggest."
                target=""
                continue
            fi
            # A directory is the answer people give when they mean "here", and
            # it used to be taken literally: the write failed, and because one
            # failure aborted the whole apply, the answers already given for the
            # other blockers were discarded with it.
            case "$target" in
                */|.|..) echo "  $target is a directory; give the file to write."
                         target=""; continue ;;
            esac
            if [[ -d "$target" ]]; then
                echo "  $target is an existing directory; give the file to write."
                target=""
                continue
            fi
            if [[ -n "$suggestion" && "$target" != "$suggestion" ]]; then
                # Writing somewhere else satisfies nothing: the next probe
                # looks where the blocker said, finds it still missing, and
                # blocks on the same prerequisite again.
                echo "  $id names $suggestion, not $target."
                gate_prompt "  Write to $target anyway? [y/N]: "
                IFS= read -r confirm || return 1
                case "$confirm" in
                    y|Y) ;;
                    *) target=""; continue ;;
                esac
            fi
            break
        done
        if [[ -z "$target" ]]; then
            echo "  no usable path given; skipped."
            continue
        fi

        case "$answer" in
            s|S)
                # Recording prose into a path that plainly wants a file is how
                # a sample PDF or a JSON fixture ends up containing the word
                # "brian". The operator may still mean it, so this asks.
                case "$(printf '%s' "${suggestion:-$target}" | tr '[:upper:]' '[:lower:]')" in
                    *.pdf|*.png|*.jpg|*.jpeg|*.zip|*.gz|*.sha256|*.json|*.csv|*.py)
                        echo "  $target looks like a file to supply, not a statement to write."
                        gate_prompt "  Write a typed statement there anyway? [y/N]: "
                        IFS= read -r confirm || return 1
                        case "$confirm" in
                            y|Y) ;;
                            *) echo "  skipped; use 'f' to copy the real file in."; continue ;;
                        esac
                        ;;
                esac
                gate_prompt "Statement -- who approved what, in your words: "
                IFS= read -r payload || return 1
                if [[ -z "$payload" ]]; then
                    echo "  no statement given; skipped."
                    continue
                fi
                printf '%s\tstatement\t%s\t%s\n' "$id" "$target" "$payload" >> "$out"
                ;;
            f|F)
                gate_prompt "Path of the existing file to copy: "
                IFS= read -r payload || return 1
                if [[ -z "$payload" ]]; then
                    echo "  no source given; skipped."
                    continue
                fi
                printf '%s\tcopy\t%s\t%s\n' "$id" "$target" "$payload" >> "$out"
                ;;
        esac
        provided=$((provided + 1))
    done
    [[ "$provided" -gt 0 ]]
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
                if ! mkdir -p "$(dirname "$target")" 2> /dev/null; then
                    echo "  $id: cannot create $(dirname "$target"); skipped" >&2
                    continue
                fi
                {
                    printf '# %s\n\n' "$id"
                    printf 'Recorded by the operator at the preflight gate.\n'
                    printf 'When: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
                    printf 'Prerequisite: %s\n\n' "$id"
                    printf '%s\n' "$payload"
                } > "$target" 2> /dev/null || {
                    echo "  $id: cannot write $target; skipped" >&2
                    continue
                }
                echo "  $id: statement recorded in $target"
                applied=$((applied + 1))
                ;;
            copy)
                if [[ ! -e "$payload" ]]; then
                    echo "  $id: $payload does not exist; nothing copied" >&2
                    continue
                fi
                if ! mkdir -p "$(dirname "$target")" 2> /dev/null; then
                    echo "  $id: cannot create $(dirname "$target"); skipped" >&2
                    continue
                fi
                if ! cp -R "$payload" "$target" 2> /dev/null; then
                    echo "  $id: cannot copy $payload to $target; skipped" >&2
                    continue
                fi
                echo "  $id: copied $payload to $target"
                applied=$((applied + 1))
                ;;
            *) ;;
        esac
    done < "$records"
    [[ "$applied" -gt 0 ]]
}

# human_input_repeating <state-dir> <id>... -- true when this exact set of
# blockers has already been answered once and came back unchanged.
#
# Providing an input re-runs preflight, which is the point. But an answer that
# does not resolve the blocker leaves the same set outstanding, and offering the
# same dialog again produces a loop that only ends when the operator gives up:
# three prerequisites, three statements written to the wrong paths, three
# identical prompts, forever. One attempt per distinct set of blockers, then say
# so and stop.
human_input_repeating() {
    local dir="$1" record signature
    shift
    [[ -n "$dir" ]] || return 1
    record="$dir/human-input-attempted"
    signature="$(printf '%s\n' "$@" | sort -u | tr '\n' ' ')"
    if [[ -s "$record" ]] && [[ "$(cat "$record")" == "$signature" ]]; then
        return 0
    fi
    printf '%s' "$signature" > "$record" 2>/dev/null || true
    return 1
}

# Forget the recorded attempt, so a set that genuinely changes gets a turn.
human_input_reset() {
    rm -f "${1:-}/human-input-attempted" 2>/dev/null || true
}
