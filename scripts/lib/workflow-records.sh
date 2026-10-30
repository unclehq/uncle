#!/usr/bin/env bash
# Shared record leaves. The driver owns ROOT, STATE_DIR, UNATTENDED_FILE,
# GREEN_CLASS and PROJECT_ROOT; completed_verdict remains family-specific.

record_unattended_gate() {
    local what="$1" detail="$2"
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$what" "$detail" \
        >> "$UNATTENDED_FILE" 2>/dev/null || true
}

record_test_failure_disposition() {
    local review_json="$STATE_DIR/documents/TEST_REVIEW.json"
    python3 -B "$ROOT/scripts/lib/test_failure_disposition.py" \
        "$GREEN_CLASS" "$review_json" "$STATE_DIR/documents/TEST_FAILURES.json"
}

finished_build_line() {
    local verdict="$1" skipped=0
    if [[ -s "$UNATTENDED_FILE" ]]; then
        skipped="$(grep -c $'\taudit-finding-skipped\t' "$UNATTENDED_FILE" || true)"
    fi
    printf 'Finished build: verdict=%s skipped=%s path=%s\n' "$verdict" "${skipped:-0}" "$PROJECT_ROOT"
    if [[ "$verdict" == READY && "${skipped:-0}" != 0 ]]; then
        echo "READY - ${skipped} blocking findings WAIVED WITHOUT HUMAN REVIEW (the auditor said NOT READY)"
    fi
}
