#!/usr/bin/env python3
"""Refresh an artifact's canonical JSON from the exact bytes a human gate
just approved.

Approval hashes are still computed over the rendered Markdown -- that is
what the operator reads and can edit before approving, so it is what the
digest has to attest to. But the JSON artifact downstream stages read must
reflect the same approved bytes, not whatever generation first produced:
a human who edits the document at the gate (explicitly supported -- "Edits
you make now are picked up by the next stage") changes the Markdown only,
and nothing re-derives the JSON from that edit without this step.

This is best-effort and silent on failure: called right after an approval
is recorded, for every gated document, whether or not that document has a
JSON schema yet or the edited Markdown still parses. A failure here must
never turn a successful approval into a failed one -- the caller already
committed the approval hash to the exact bytes on disk; this only tries to
keep the JSON mirror in sync with them.
"""
import importlib.util
from pathlib import Path
import sys

_LIB = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), _LIB / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# approval name -> (module filename, export function name). Only artifacts
# with a canonical JSON schema appear here; approving anything else (a diff
# review, an override decision, an artifact without a schema yet) is a
# deliberate no-op until that artifact gets one.
#
# The plan-family entries (PROJECT_PLAN, UPDATED_PROJECT_PLAN, CHANGE_SPEC,
# CHANGE_PLAN) only succeed when the approved document still matches our own
# render_plan()/render_change_plan()/render_change_spec() output exactly --
# see plan_context.py's export_plan()/export_change_plan()/export_change_spec()
# docstrings. A plan an agent wrote directly as Markdown, or a human edit that
# breaks the section structure, fails closed into the same silent no-op this
# module already gives an artifact with no schema at all.
_EXPORTERS = {
    'ADVERSARIAL_REVIEW': ('adversarial-context.py', 'export_json'),
    'REQUIREMENTS_INTERPRETATION': ('requirements-context.py', 'export_json'),
    'MANUAL_CHECKLIST': ('checklist_document.py', 'export_json'),
    'TEST_REVIEW': ('acceptance_context.py', 'export_json'),
    'PREFLIGHT_REPORT': ('acceptance_context.py', 'export_json'),
    'PROJECT_PLAN': ('plan_context.py', 'export_project_plan'),
    'UPDATED_PROJECT_PLAN': ('plan_context.py', 'export_updated_project_plan'),
    'CHANGE_SPEC': ('plan_context.py', 'export_change_spec'),
    'CHANGE_PLAN': ('plan_context.py', 'export_change_plan'),
}


def refresh(name, path, project='.'):
    """Best-effort: re-export NAME's canonical JSON from PATH's approved
    bytes. Returns True if an export ran (regardless of whether it changed
    anything), False if this name has no exporter or the export failed."""
    entry = _EXPORTERS.get(name)
    if entry is None:
        return False
    filename, function = entry
    try:
        module = _load(filename)
        getattr(module, function)(path, project)
        return True
    except Exception:
        # Deliberately broad: a human's edit at the gate may no longer be
        # valid Markdown for that exporter's validator, and that is the
        # exporter's job to reject at generation time, not this refresh's
        # job to enforce retroactively on an already-approved document.
        return False


if __name__ == '__main__':
    refresh(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '.')
