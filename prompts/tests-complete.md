You are finishing the defect-injection list of a tests build. The tests and the application source now both exist, and the driver has put
everything you need below: the list as it stands and the source file each entry targets.

Each entry has an `id`, `breaks`, `target` (source module), `spec` and `expected_failing_tests`. The defect-injection runner also needs, per entry:

- `file`: the source path to mutate (normally the entry's `target`);
- `find`: text copied EXACTLY from that file's source (shown below) that occurs EXACTLY ONCE in it;
- `replace`: the wrong implementation that should make the named tests fail. It must differ from `find`.

Rules:

1. Keep every entry, and keep each entry's `id`, `breaks` and `expected_failing_tests` exactly as written. Do not delete, merge or reorder entries. The driver rejects a changed intent.
2. Choose each mutation from the source shown and the entry's `breaks`/`spec`, so that the named tests should reject it. Do not change the source or the tests.
3. Do not read files or run commands: everything is below. Write the completed list with ONE Write call to the list path, as a complete replacement. Pick `find` strings long enough to be unique (a whole line or two). The driver checks that each `find` occurs exactly once and tells you which do not.
4. Edit only the listed files. Do not write workflow documents.
