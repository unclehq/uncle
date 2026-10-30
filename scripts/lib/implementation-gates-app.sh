#!/usr/bin/env bash
# App implementation policy bindings. Load implementation-gates.sh first.

build_implementation_review() {
    app_build_implementation_review "$@"
}

verify_implementation_review() {
    app_verify_implementation_review "$@"
}
