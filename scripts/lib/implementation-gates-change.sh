#!/usr/bin/env bash
# Change implementation policy bindings. Load implementation-gates.sh first.

implementation_incomplete_choice() {
    change_implementation_incomplete_choice "$@"
}

build_implementation_review() {
    change_build_implementation_review "$@"
}

verify_implementation_review() {
    change_verify_implementation_review "$@"
}
