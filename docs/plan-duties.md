# Change plan duties

The new-application flow finishes its sectioned plan with `project-plan-stage-duties`: a consistency check, then `.gitignore` duties.
A change request now has its counterpart, `change-plan-stage-duties`, as its own timed state (`CHANGE_PLAN_DUTIES`) right after
planning and before the analysis approval gate. It differs on purpose: the check is deterministic (a file the plan mentions that no
step owns, that does not exist, and that sits beside files a step does own: one file with two names), the model is asked for a fix
only when there is a finding, so a consistent plan costs no model call, and there is no `.gitignore` duty, because a change request
must not make unrelated edits to an existing repository. The fix is a patch applied to the canonical `CHANGE_PLAN.json`. The stage is
fail-open (a model that fails leaves the plan as it was, with the findings shown at the approval gate). `WORKFLOW_PLAN_DUTIES=0` turns it
off, and `change-plan-stage-duties.runner|model|effort` configure it (default: the `change-plan` stage's).

