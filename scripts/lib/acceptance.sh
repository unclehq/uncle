#!/usr/bin/env bash
# Classify the machine-readable table shared by preflight, test review, and
# verification. Unknown/malformed reports never authorize the next stage.
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
            if (id !~ /^[A-Za-z0-9][A-Za-z0-9_.-]*$/ || seen[id]++ || evidence == "" ||
                (required != "YES" && required != "NO") ||
                (status != "PASS" && status != "FAIL" && status != "BLOCKED" && status != "NOT RUN" && status != "N/A")) bad=1
            if (required == "YES") {
                required_ids[id]=1
                mandatory++
                if (status == "FAIL") failed=1
                if (status == "BLOCKED" || status == "NOT RUN" || status == "N/A") blocked=1
            }
        }
        END {
            n=split(expected, ids, " ")
            for (i=1; i<=n; i++) if (!(ids[i] in required_ids)) bad=1
            if (bad || sections != 1 || !separator || !mandatory) print "UNKNOWN"
            else if (blocked) print "BLOCKED"
            else if (failed) print "REPAIR"
            else print "PASS"
        }
    ' "$file"
}
