#!/usr/bin/env bash
# Classify the machine-readable table shared by preflight, test review, and
# verification. Unknown/malformed reports never authorize the next stage.
#
# A blocked row is not one thing. Three unrelated situations used to share the
# word, and the driver could not tell them apart, so all three produced the
# same dead stop:
#
#   BLOCKED-SETUP       one action nobody has taken yet -- an admin command, a
#                       consent dialog, an uncommitted tree. Doable now.
#   BLOCKED-HUMAN       waiting on a person to look and sign. Expected: it is
#                       what a human-gated workflow is for, not a fault.
#   BLOCKED-IMPOSSIBLE  no environment can satisfy it as written. Effort will
#                       not clear it; the plan or the requirement has to change.
#
# Telling them apart is what lets a run finish when only signatures remain,
# batch the setup actions when they are the only thing missing, and stop hard
# -- pointing at the plan rather than at the machine -- when a required check
# cannot be performed at all.
#
# A bare BLOCKED stays valid and means SETUP: that is what the driver already
# did with it, so old reports keep their behavior instead of turning UNKNOWN.
acceptance_result() {
    local file="$1"
    if [[ ! -s "$file" ]]; then
        printf 'UNKNOWN\n'
        return
    fi
    awk -F '|' -v expected="${2:-}" '
        function trim(s) { sub(/^[ \t\r]+/, "", s); sub(/[ \t\r]+$/, "", s); return s }
        /^## Acceptance gate[ \t\r]*$/ { sections++; active=1; next }
        active && /^[ \t\r]*$/ { next }
        active {
            # Prose after the last row is tolerated; a row after prose is not.
            #
            # The rule this replaces rejected any non-table line in the
            # section, which cost three runs in a row to a closing summary
            # paragraph. What it was actually guarding is worth keeping: a row
            # hidden below prose would be silently ignored, so a FAIL could be
            # buried. That property survives -- anything containing a pipe
            # after prose has started is still a malformed report.
            if (rows > 0 && index($0, "|") == 0) { prose=1; next }
            if (prose) { bad=1; next }
            if (NF != 6 || trim($1) != "" || trim($6) != "") { bad=1; next }
            id=trim($2); required=trim($3); status=trim($4); evidence=trim($5)
            if (!header) {
                if (id != "ID" || required != "Required" || status != "Status" || evidence != "Evidence") bad=1
                header=1; next
            }
            if (!separator) {
                for (i=2; i<=5; i++) if (trim($i) !~ /^:?-{3,}:?$/) bad=1
                separator=1; next
            }
            if (id !~ /^[A-Za-z0-9][A-Za-z0-9_.\/-]*$/ || seen[id]++ || evidence == "" ||
                (required != "YES" && required != "NO") ||
                (status != "PASS" && status != "FAIL" && status != "BLOCKED" &&
                 status != "BLOCKED-SETUP" && status != "BLOCKED-HUMAN" &&
                 status != "BLOCKED-IMPOSSIBLE" && status != "NOT RUN" && status != "N/A")) bad=1
            rows++
            if (required == "YES") {
                required_ids[id]=1
                mandatory++
                if (status == "FAIL") failed=1
                else if (status == "BLOCKED-IMPOSSIBLE") impossible=1
                else if (status == "BLOCKED-HUMAN") human=1
                # A bare BLOCKED, a NOT RUN, and an N/A on a required row are
                # all unclassified: treated as setup, which is the pause the
                # driver already performed for them.
                else if (status == "BLOCKED" || status == "BLOCKED-SETUP" ||
                         status == "NOT RUN" || status == "N/A") setup=1
            }
        }
        END {
            n=split(expected, ids, " ")
            for (i=1; i<=n; i++) if (!(ids[i] in required_ids)) bad=1
            if (bad || sections != 1 || !separator || !mandatory) print "UNKNOWN"
            else if (failed) print "REPAIR"
            else if (impossible) print "BLOCKED-IMPOSSIBLE"
            else if (setup) print "BLOCKED-SETUP"
            else if (human) print "BLOCKED-HUMAN"
            else print "PASS"
        }
    ' "$file"
}

# acceptance_blocked_ids <file> <status> -- the required rows carrying one
# status, so the driver can name them, batch them, or check them against
# recorded waivers instead of printing a verdict and stopping.
acceptance_blocked_ids() {
    local file="$1" want="$2"
    [[ -s "$file" ]] || return 0
    awk -F '|' -v want="$want" '
        function trim(s) { sub(/^[ \t\r]+/, "", s); sub(/[ \t\r]+$/, "", s); return s }
        /^## Acceptance gate[ \t\r]*$/ { active=1; next }
        active && NF == 6 {
            id=trim($2); required=trim($3); status=trim($4)
            if (id == "ID" || trim($2) ~ /^:?-{3,}:?$/) next
            if (required != "YES") next
            if (status == want) print id
            else if (want == "BLOCKED-SETUP" &&
                     (status == "BLOCKED" || status == "NOT RUN" || status == "N/A")) print id
        }
    ' "$file"
}

# Every blocked class, for a caller that just needs to know whether anything
# is outstanding.
acceptance_is_blocked() {
    case "$1" in
        BLOCKED|BLOCKED-*) return 0 ;;
        *) return 1 ;;
    esac
}

# acceptance_row_status <file> <id> / acceptance_row_evidence <file> <id> --
# one row's status and evidence, for a caller that has to say what a specific
# check is waiting on rather than just how many are.
acceptance_row_field() {
    local file="$1" want="$2" field="$3"
    [[ -s "$file" ]] || return 0
    awk -F '|' -v want="$want" -v field="$field" '
        function trim(s) { sub(/^[ \t\r]+/, "", s); sub(/[ \t\r]+$/, "", s); return s }
        /^## Acceptance gate[ \t\r]*$/ { active=1; next }
        active && NF == 6 {
            if (trim($2) != want) next
            print trim($(field))
            exit
        }
    ' "$file"
}

acceptance_row_status() { acceptance_row_field "$1" "$2" 4; }
acceptance_row_evidence() { acceptance_row_field "$1" "$2" 5; }

# acceptance_problem <file> -- why the table did not parse, with a line number.
#
# UNKNOWN on its own is unactionable: the report is one of a dozen rules away
# from valid and the operator cannot tell which. Every rule below mirrors one in
# acceptance_result, so a rejected report says what to fix rather than that it
# was rejected. Reported for the operator, never used to decide a gate.
acceptance_problem() {
    local file="$1"
    if [[ ! -s "$file" ]]; then
        printf '%s is missing or empty.\n' "$file"
        return 0
    fi
    awk '
        function trim(s) { sub(/^[ \t\r]+/, "", s); sub(/[ \t\r]+$/, "", s); return s }
        function say(msg) { printf "line %d: %s\n", NR, msg; found++ }
        /^## Acceptance gate[ \t\r]*$/ {
            sections++
            if (sections > 1) say("a second \"## Acceptance gate\" section; there must be exactly one")
            active = 1; next
        }
        active && /^[ \t\r]*$/ { next }
        active {
            n = split($0, cells, "|")
            if (rows > 0 && index($0, "|") == 0) { prose=1; next }
            if (prose && index($0, "|") > 0) {
                say("a table row after prose: \"" substr(trim($0), 1, 40) "\". Anything with a pipe below the closing text would be read as a row and ignored, so move the text after every row")
                next
            }
            if (n != 6 || trim(cells[1]) != "" || trim(cells[6]) != "") {
                say("a row with " (n - 2) " cells, not 4. Every row is \"| ID | Required | Status | Evidence |\", and no cell may contain a literal pipe")
                next
            }
            id = trim(cells[2]); required = trim(cells[3]); status = trim(cells[4]); evidence = trim(cells[5])
            if (!header) {
                if (id != "ID" || required != "Required" || status != "Status" || evidence != "Evidence")
                    say("the header must read exactly \"| ID | Required | Status | Evidence |\"")
                header = 1; next
            }
            if (!separator) {
                for (i = 2; i <= 5; i++)
                    if (trim(cells[i]) !~ /^:?-{3,}:?$/) { say("the separator row must be \"|---|---|---|---|\""); break }
                separator = 1; next
            }
            if (id !~ /^[A-Za-z0-9][A-Za-z0-9_.\/-]*$/) say("id \"" id "\" is not a plain identifier")
            else if (seen[id]++) say("id \"" id "\" appears twice")
            if (evidence == "") say("id \"" id "\" has empty Evidence; every row needs observed output or a recorded arrangement")
            if (required != "YES" && required != "NO") say("id \"" id "\" has Required \"" required "\"; it must be YES or NO")
            if (status != "PASS" && status != "FAIL" && status != "BLOCKED" &&
                status != "BLOCKED-SETUP" && status != "BLOCKED-HUMAN" &&
                status != "BLOCKED-IMPOSSIBLE" && status != "NOT RUN" && status != "N/A")
                say("id \"" id "\" has Status \"" status "\"; it must be PASS, FAIL, BLOCKED-SETUP, BLOCKED-HUMAN, BLOCKED-IMPOSSIBLE, NOT RUN, or N/A")
            rows++
            if (required == "YES") mandatory++
        }
        END {
            if (!sections) print "no \"## Acceptance gate\" section at all."
            else if (!separator) print "the Acceptance gate section has no header and separator row."
            else if (!mandatory) print "no row has Required YES; at least one is required."
            else if (!found) print "the table parses; the report was rejected for another reason."
        }
    ' "$file"
}
