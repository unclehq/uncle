"""Where a workflow-generated document actually lives: .uncle/docs/<name>.

These 18 names are never operator input -- REQUIREMENTS.md and
CHANGE_REQUEST.md are the two exceptions (generated_input.py) that a human
may place at the project root by hand, so they alone are resolved by
checking root first. Everything here is pure workflow output with no such
ambiguity, so it always lives under .uncle/docs, unconditionally.
"""
from pathlib import Path

WORKFLOW_DOCS = frozenset((
    'REQUIREMENTS_INTERPRETATION.md', 'PROJECT_PLAN.md', 'UPDATED_PROJECT_PLAN.md',
    'BASELINE_REPORT.md', 'CHANGE_SPEC.md', 'CHANGE_PLAN.md',
    'UPDATED_CHANGE_PLAN.md', 'ADVERSARIAL_REVIEW.md', 'IMPLEMENTATION_NOTES.md',
    'CHANGE_TEST_REPORT.md', 'AUTOMATED_TEST_REPORT.md', 'MANUAL_CHECKLIST.md',
    'VERIFICATION_REPORT.md', 'DEFECTS.md', 'FINAL_AUDIT.md', 'PREFLIGHT_REPORT.md',
    'TEST_REVIEW.md',
))


def workflow_doc_path(name, root='.'):
    """The on-disk path for a workflow document, whether or not it exists
    yet. A name outside WORKFLOW_DOCS (a project's own file, an operator
    input) is returned unchanged, resolved against root."""
    root = Path(root)
    base = Path(name).name
    if base in WORKFLOW_DOCS:
        return root / '.uncle' / 'docs' / base
    return root / name
