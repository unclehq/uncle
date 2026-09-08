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
