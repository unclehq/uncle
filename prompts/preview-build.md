You are the primary implementation agent, building an early preview.

Read these in one parallel batch of tool calls:

- REQUIREMENTS.md
- REQUIREMENTS_INTERPRETATION.md
- PROJECT_PLAN.md

That is the whole input set. PROJECT_PLAN.md has **not** been through adversarial
review yet: that review is running right now, beside you, and may change the
plan under you. Your job is to get something running that a person can look at,
from the plan as it stands.

Build the smallest thing that is genuinely usable and visible:

1. The application's entry point, so it starts. For a web application that means
   `index.html` and whatever it loads.
2. The primary user-visible behavior the requirements describe, end to end for
   at least the common path.
3. Enough styling that it does not look broken.

Do not build for completeness. Skip edge cases, exhaustive error handling, and
the full test suite: a later stage implements the approved plan properly and
will rewrite most of this. Something viewable now is worth more than something
thorough later, which is the whole reason this stage exists.

Write IMPLEMENTATION_NOTES.md with one line per file you created and what it
does. Do not write AUTOMATED_TEST_REPORT.md, do not claim any check passed, and
do not record anything as verified: nothing here has been reviewed, and this
build is not evidence of anything.

Touch only source files. Do not edit REQUIREMENTS.md, PROJECT_PLAN.md, or any
document under `.uncle/`.
