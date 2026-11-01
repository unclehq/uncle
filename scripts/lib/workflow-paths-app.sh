#!/usr/bin/env bash
# App workflow path policy. ROOT is the installation, STATE_DIR belongs
# to the project. The driver supplies supervision_validation_failed when a
# required file is missing. No paths are resolved until a function is called.

resolve_prompt() {
    local p="$1"
    # A caller can materialize a temporary absolute prompt immediately before
    # invoking us. Preserve that identity even if another process has removed
    # it by the time this check runs: prefixing it with ROOT turns
    # /var/.../batch-4.md into an impossible Cellar-relative pathname.
    # A relative prompt is the driver's own (prompts/...). Resolve it against ROOT first: a project that is itself an Uncle
    # checkout has its own prompts/ directory, and the current directory's copy of a prompt is not the one this driver ships.
    if [[ "$p" != /* && -e "$ROOT/$p" ]]; then
        printf '%s' "$ROOT/$p"
    elif [[ "$p" == /* || -e "$p" ]]; then
        printf '%s' "$p"
    else
        printf '%s' "$ROOT/$p"
    fi
}

# Only workflow artifacts are mapped; ordinary project paths stay literal.
canonical_artifact_path() {
    local path="$1" stem
    case "$path" in
        .uncle/docs/REQUIREMENTS_INTERPRETATION.md|.uncle/docs/PREFLIGHT_REPORT.md|.uncle/docs/TEST_REVIEW.md|.uncle/docs/VERIFICATION_REPORT.md|.uncle/docs/DEFECTS.md|.uncle/docs/MANUAL_CHECKLIST.md|.uncle/docs/FINAL_AUDIT.md|.uncle/docs/IMPLEMENTATION_NOTES.md|.uncle/docs/AUTOMATED_TEST_REPORT.md|.uncle/docs/PROJECT_PLAN.md|.uncle/docs/UPDATED_PROJECT_PLAN.md|.uncle/docs/ADVERSARIAL_REVIEW.md)
            stem="${path##*/}"; stem="${stem%.md}"
            printf '%s/documents/%s.json\n' "${STATE_DIR:-.uncle/workflow}" "$stem" ;;
        *) printf '%s\n' "$path" ;;
    esac
}

# Legacy Markdown is used only when the canonical artifact is absent/empty.
approval_artifact_path() {
    local view="$1" canonical
    canonical="$(canonical_artifact_path "$view")"
    [[ -s "$canonical" ]] && printf '%s\n' "$canonical" || printf '%s\n' "$view"
}

require_file() {
    local requested="$1" canonical
    canonical="$(canonical_artifact_path "$requested")"
    if [[ ! -s "$canonical" ]]; then
        supervision_validation_failed require_file "$canonical" "Required file is missing or empty: $canonical"
        echo "Required file is missing or empty: $canonical"
        exit 1
    fi
}
