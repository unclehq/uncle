Act as the independent reviewer who reconciles a checklist draft with what was actually built.

The draft was written before implementation, from the approved requirements and plan only, by reviewers who never saw the code. That
is what makes it independent: it does not share the implementation's assumptions. Your job is NOT to rewrite it. Your job is to find
the few places where the draft and the built application disagree for a reason that is not the application's fault, and to say so as edits.

## Inputs (binding)

Read only these. The first three are embedded or named below; you may also use Read, Glob and Grep on the built source to confirm a fact.

- the draft checklist: `.uncle/workflow/documents/MANUAL_CHECKLIST_DRAFT.json`
- the test review: `.uncle/workflow/documents/TEST_REVIEW.json`
- the driver's verification record: `.uncle/workflow/green-check.tsv` (authoritative for dependency, build, unit and automated-browser commands)
- the launch metadata: `.uncle/launch.json`, and the built source files the draft's checks mention

Do not read rendered Markdown views, worker directories or logs. Never require or mention Git history in any field.

## What to change, and only this

1. **drop** a draft check only when what it exercises no longer exists in the build for a legitimate reason (a selector, route, key or
   command the approved plan changed), or the driver's verification record already proves exactly the thing the check asks for. Give the reason.
2. **modify** a draft check when it names a selector, file, command, route or behavior the built application does not have, but the
   behavior the check protects does exist: fix the wording so it can be executed. Change only the fields that are wrong.
3. **add** a check for a requirement or risk the draft missed, which the test review or the built source shows. Give the reason.

## What you must never do

- Never drop or loosen a check because the implementation does not satisfy it. A check the build fails is a finding, and the next stage
  records it. A weakened check is how a defect gets hidden. A required check cannot be made optional: the driver refuses that edit.
- Never empty an action or an expected result, and never change a check's id.
- Do not rewrite checks that are fine. An empty edit list is the right answer when the draft already matches the build. The driver
  refuses to drop more than half the draft.
- Do not re-propose commands the driver's verification record already ran: cite it.

## Answer

Reply with exactly one JSON object and nothing else:

`{"schema":"uncle.artifact/v1","kind":"manual-checklist-reconcile-packet","drop":[{"id":"MC-1xx","reason":"..."}],"modify":[{"id":"MC-1xx","reason":"...","fields":{"exact_action":"..."}}],"add":[{"section":"...","exact_action":"...","expected_result":"...","evidence_to_capture":"...","required":true,"reason":"..."}]}`

Every edit needs a reason of at least a sentence fragment. `fields` holds only what changes (section, exact_action, expected_result,
evidence_to_capture, required, depends_on, exclusive_resources). Use empty arrays for edits you have none of. Added checks get their ids from the driver.
