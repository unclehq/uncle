#!/usr/bin/env bash
# Run the project's own verification commands, from the driver, and compare the
# result against the same commands run before anything changed.
#
# The stage that writes the code is also the stage that reports whether the
# code passes. CHANGE_TEST_REPORT.md and AUTOMATED_TEST_REPORT.md are the
# agent's account of checks the agent ran, and every downstream stage — the
# checklist, the verification report, the audit — reads that account rather
# than the checks. Rule 10 of CLAUDE.md ("never claim a check passed unless it
# was executed") was therefore enforced only by asking.
#
# These functions close that loop: the driver runs the commands itself, with no
# agent in the path, and records the exit statuses.
#
# The command list is not invented here. It is read from a document the human
# has already approved at a gate — BASELINE_REPORT.md for the change pipeline,
# UPDATED_PROJECT_PLAN.md for the new-application pipeline — so what the driver
# executes is what the operator signed off on.
#
# A repository is rarely all green to begin with: a lint rule that has failed
# for a year is not this change's fault, and a gate that blocks on it is a gate
# people turn off. So the same list is run once before implementation, and a
# command only blocks when it passed then and fails now.
#
# bash 3.2 compatible: no associative arrays, no ${var^^}.
GREEN_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$GREEN_LIB_DIR/performance.sh"

# Optional approved groups refer to consecutive, one-based command positions.
# Absence preserves sequential execution. Bad declarations fail before tests.
verify_parallel_groups() {
    local plan="$1" commands="$2"
    awk -v count="$(wc -l < "$commands" | tr -d ' ')" '
        /^## Parallel verification groups[ \t\r]*$/ { active=1; sections++; next }
        active && /^```/ { if (opened) { closed=1; active=0 } else opened=1; next }
        active && /^#/ { bad=1; active=0 }
        active && opened && NF {
            if ($0 !~ /^[0-9 \t\r]+$/ || NF < 2 || $1 <= last || $NF > count) bad=1
            for (i=2; i<=NF; i++) if ($i != $(i-1)+1) bad=1
            last=$NF; rows++; print
        }
        END { if (sections && (sections != 1 || !closed || !rows || bad)) exit 1 }
    ' "$plan"
}

# Shown when a plan's groups cannot be parsed: the shape the parser accepts,
# so whoever amends the plan does not have to read this file to find it.
parallel_groups_format_hint() {
    cat >&2 <<'HINT'
Expected shape, immediately under the heading:

## Parallel verification groups

```text
2 3 4
6 7
```

Bare one-based positions from the Verification commands block: one group per
line, at least two consecutive numbers per line, lines ordered and disjoint.
No bullets, labels, or prose in the block.
HINT
}

# verify_commands <file> — one command per line, from the first fenced block
# under the document's verification-command heading.
#
# Recognised headings, at any level and with or without a section number:
#   ## 8. Exact build and test commands executed   (BASELINE_REPORT.md)
#   ## Verification commands                       (UPDATED_PROJECT_PLAN.md)
#
# Prose, blank lines, comments, and a shell-prompt "$ " prefix are dropped, so
# a block written for a human still parses. Nothing outside the block is read:
# a command has to be somewhere the document promised commands would be.
verify_commands() {
    local file="$1"

    [[ -s "$file" ]] || return 0

    awk '
        # Fences are only meaningful inside the section, and the first block
        # closes it: a later example block elsewhere is not a command list.
        /^[[:space:]]*```/ {
            if (insec) {
                inblock = !inblock
                if (!inblock) { insec = 0; done = 1 }
            }
            next
        }
        inblock { print; next }
        done { next }
        /^#+[[:space:]]/ {
            h = tolower($0)
            insec = (index(h, "verification commands") > 0 \
                  || index(h, "build and test commands") > 0)
        }
    ' "$file" \
        | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^\$[[:space:]]*//' \
        | grep -v '^#' \
        | grep -v '^$' \
        || true
}

# green_run <commands_file> <out_tsv> <log_file> [integrity_guard] — run each command from the
# repository root and record "<exit status>TAB<command>", one per line.
#
# Commands run with the driver's own privileges, exactly as the operator would
# run them by hand. stdin is closed so a command that reads it cannot consume
# the rest of the command list.
green_run() {
    local cmds="$1" out="$2" log="$3"
    local cmd status guard="${4:-}"
    local groups="${5:-}" started

    if [[ -n "$groups" && -s "$groups" ]] \
        && command -v python3 > /dev/null 2>&1 \
        && [[ -f "$GREEN_LIB_DIR/parallel_checks.py" ]] \
        && [[ -z "$guard" || "$guard" == check_verification_inputs ]]; then
        local -a flags=(--commands "$cmds" --out "$out" --log "$log"
                       --groups "$groups" --jobs "${WORKFLOW_VERIFY_JOBS:-2}")
        if [[ -n "$guard" ]]; then
            flags+=(--paths "$STATE_DIR/verification.paths"
                    --expected "$STATE_DIR/verification.manifest"
                    --integrity-log "$STATE_DIR/verification-integrity.log")
        fi
        if [[ "${WORKFLOW_METRICS:-1}" == 1 && -n "${STATE_DIR:-}" ]]; then
            flags+=(--metrics "$STATE_DIR/metrics")
        fi
        status=0
        python3 -B "$GREEN_LIB_DIR/parallel_checks.py" "${flags[@]}" || status=$?
        if [[ "$status" == 3 && -n "$guard" ]]; then verification_integrity_failure; fi
        return "$status"
    fi

    : > "$out"
    : > "$log"

    while IFS= read -r cmd; do
        [[ -n "$cmd" ]] || continue
        if [[ -n "$guard" ]]; then "$guard" || return 1; fi

        printf '\n$ %s\n' "$cmd" >> "$log"

        status=0
        started="$SECONDS"
        bash -c "$cmd" < /dev/null >> "$log" 2>&1 || status=$?
        perf_record check "$cmd" "$((SECONDS-started))" "$status"

        printf '%s\t%s\n' "$status" "$cmd" >> "$out"
        if [[ -n "$guard" ]]; then "$guard" || return 1; fi

        if [[ "$status" -eq 0 ]]; then
            printf '  PASS      %s\n' "$cmd"
        else
            printf '  FAIL(%s)   %s\n' "$status" "$cmd"
        fi
    done < "$cmds"
}

# green_classify <baseline_tsv> <current_tsv> — "<class>TAB<command>" per line.
#
#   PASS         passed now, and passed before or was not run before
#   FIXED        failed before, passes now
#   PREEXISTING  failed before and still fails — not this change's regression
#   REGRESSION   fails now and did not fail before
#
# A command with no baseline entry that fails now is a REGRESSION. That is the
# fail-closed reading: an unrecorded baseline is not evidence of a prior
# failure, and a gate that assumes otherwise passes everything on a missing
# file.
green_classify() {
    local base="$1" cur="$2"

    [[ -s "$cur" ]] || return 0

    awk -v basefile="$base" '
        BEGIN {
            if (basefile != "") {
                while ((getline line < basefile) > 0) {
                    t = index(line, "\t")
                    if (t == 0) continue
                    cm = substr(line, t + 1)
                    b[cm] = substr(line, 1, t - 1)
                    seen[cm] = 1
                }
            }
        }
        {
            t = index($0, "\t")
            if (t == 0) next
            st = substr($0, 1, t - 1)
            cm = substr($0, t + 1)
            known = (cm in seen)
            if (st == "0") {
                if (known && b[cm] != "0") print "FIXED\t" cm
                else                       print "PASS\t" cm
            } else {
                if (known && b[cm] != "0") print "PREEXISTING\t" cm
                else                       print "REGRESSION\t" cm
            }
        }
    ' "$cur"
}

# green_regressions <classified_file> — how many commands regressed.
green_regressions() {
    if [[ ! -s "$1" ]]; then
        printf '0'
        return 0
    fi
    awk '
        { t = index($0, "\t") }
        t > 0 && substr($0, 1, t - 1) == "REGRESSION" { n++ }
        END { printf "%d", n + 0 }
    ' "$1"
}

# green_report <classified_file> <out_md> <source_doc> <log_path> [has_baseline]
# — the table the human reads at the gate.
#
# Written even when nothing ran: "NOT RUN" in front of a human is a result, and
# silently omitting the section would let an unverified change look verified.
#
# has_baseline defaults to 1. Pass 0 for a new application, where nothing was
# passing before: "regressed" would be a claim about a past that never existed,
# so a failure is reported as a failure.
green_report() {
    local classified="$1" out="$2" source_doc="$3" log="$4"
    local has_baseline="${5:-1}"

    {
        echo "## Green check"
        echo

        if [[ ! -s "$classified" ]]; then
            echo "NOT RUN. No verification commands were found in \`$source_doc\`,"
            echo "so the driver could not re-run the project's checks itself."
            echo "The only evidence that the checks passed is the implementation"
            echo "stage's own report."
            return 0
        fi

        echo "Commands read from \`$source_doc\` and run by the driver, with no"
        echo "agent in the path. Full output: \`$log\`."
        echo
        echo "| Result | Command |"
        echo "|---|---|"
        awk -v baseline="$has_baseline" '
            { t = index($0, "\t") }
            t > 0 {
                class = substr($0, 1, t - 1)
                if (baseline != "1" && class == "REGRESSION") class = "FAIL"
                printf "| %s | `%s` |\n", class, substr($0, t + 1)
            }
        ' "$classified"
        echo

        local failures
        failures="$(green_regressions "$classified")"

        if [[ "$has_baseline" != "1" ]]; then
            if [[ "$failures" -gt 0 ]]; then
                echo "**$failures command(s) failed.**"
            else
                echo "All verification commands passed."
            fi
        elif [[ "$failures" -gt 0 ]]; then
            echo "**$failures command(s) regressed**: they passed before this"
            echo "change and fail now."
        else
            echo "No regressions. PREEXISTING rows failed before this change too."
        fi
    } > "$out"
}
