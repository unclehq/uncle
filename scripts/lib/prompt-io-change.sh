#!/usr/bin/env bash
# Family prompt wrapper, retained verbatim (app uses upper; change uses tr).

legacy_word_notice() {
    case "$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')" in
        APPROVE|ACKNOWLEDGE)
            echo "This gate now requires 'y' to approve."
            ;;
    esac
}
