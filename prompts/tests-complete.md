You are finishing the defect-injection list of a tests build. The tests and the application source now both exist.

Each file listed under "Files to complete" holds one entry per representative defect, with an `id`, `breaks`, `target` (source module),
`spec` and `expected_failing_tests`. The defect-injection runner also needs, per entry:

- `file`: the source path to mutate (normally the entry's `target`);
- `find`: text copied EXACTLY from the final source that occurs EXACTLY ONCE in `file`;
- `replace`: the wrong implementation that should make the named tests fail.

Rules:

1. Keep every entry, and keep each entry's `id`, `breaks` and `expected_failing_tests` exactly as written. Do not delete, merge or reorder entries. The driver rejects a changed intent.
2. Read the target source and the named spec to choose a mutation that the named tests should reject. Do not change the source or the tests.
3. Verify uniqueness before finishing: for each entry, the `find` string must occur exactly once in `file` (use a shell one-liner, for example `node -e` or `grep -c -F`). Fix any entry that does not.
4. Edit only the listed files. Do not write workflow documents.
