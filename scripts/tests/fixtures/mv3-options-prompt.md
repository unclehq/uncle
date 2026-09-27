# MV-3 scripted runner prompt (Issue 76)

Use this as the implementation-stage task for manual check MV-3.

Before doing anything else, print exactly these lines as your message and then
wait for the operator's answer without taking any other action:

Which test runner should this project use?
Options: 1) jest 2) node:test 3) vitest

When a message arrives that begins with
`[operator answer to runner question`, reply with one line:
`Received answer: <the Answer line from that message>` and stop.
