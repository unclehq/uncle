#!/usr/bin/env python3
"""Today's new-application build, stated as an artifact graph.

Phase 1 of docs/ARTIFACT_GRAPH.md: describe what stagegate.sh already does, change nothing. The state list is
checked against stagegate.sh by scripts/tests/driver-graph-test.py, so this file cannot drift from the driver
it describes. Edges here are the build's real data dependencies, not the order the driver happens to walk.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from driver_graph import Graph, Node  # noqa: E402

# Every arm of the main `case` in stagegate.sh, in file order.
STATES = (
    'DERIVE_BRIEF', 'WAIT_DERIVE_APPROVAL', 'REQUIREMENTS', 'VALIDATE_REQUIREMENTS', 'WAIT_REQUIREMENTS_APPROVAL',
    'PROJECT_PLAN', 'CLASSIFY', 'WAIT_PLAN_APPROVAL', 'ADVERSARIAL_REVIEW', 'VALIDATE_ADVERSARIAL_REVIEW',
    'WAIT_REVIEW_ACKNOWLEDGEMENT', 'UPDATED_PLAN', 'VALIDATE_UPDATED_PLAN', 'WAIT_UPDATED_PLAN_APPROVAL',
    'PREFLIGHT', 'MODULE_INTERFACES', 'TESTS', 'IMPLEMENT', 'WAIT_IMPLEMENT_APPROVAL', 'TEST_REVIEW', 'VALIDATE_TEST_REVIEW',
    'REPAIR', 'MANUAL_CHECKLIST', 'VALIDATE_MANUAL_CHECKLIST', 'EXECUTE_CHECKLIST', 'VALIDATE_CHECKLIST',
    'FINAL_AUDIT', 'VALIDATE_AUDIT', 'WAIT_AUDIT_OVERRIDE', 'COMPLETE',
)

# Seconds per workflow stage in a measured build (run 3, 488s wall; .uncle/workflow/performance report).
MEASURED_SECONDS = {
    'requirements': 16.2, 'classify': 3.3, 'project_plan': 73.7, 'adversarial_review': 19.4, 'updated_plan': 28.0,
    'preflight': 0.1, 'implement': 226.1, 'test_review': 46.3, 'manual_checklist': 10.4,
    'execute_checklist': 24.1, 'final_audit': 39.0,
}

EXTERNAL = ('BRIEF', 'PROJECT_TREE')

# Where each artifact shows up in a project, relative to PROJECT_ROOT. SOURCE has no file of its own: the implementation
# notes are written last by the implement stage, so they stand in for it.
ARTIFACT_FILES = {
    'REQUIREMENTS': '.uncle/docs/REQUIREMENTS_INTERPRETATION.md',
    'CLASSIFICATION': '.uncle/workflow/change-class.json',
    'PROJECT_PLAN': '.uncle/docs/PROJECT_PLAN.md',
    'ADVERSARIAL_REVIEW': '.uncle/docs/ADVERSARIAL_REVIEW.md',
    'UPDATED_PROJECT_PLAN': '.uncle/docs/UPDATED_PROJECT_PLAN.md',
    'PREFLIGHT_REPORT': '.uncle/docs/PREFLIGHT_REPORT.md',
    'SOURCE': '.uncle/docs/IMPLEMENTATION_NOTES.md',
    'TEST_REVIEW': '.uncle/docs/TEST_REVIEW.md',
    'MANUAL_CHECKLIST': '.uncle/docs/MANUAL_CHECKLIST.md',
    'VERIFICATION_REPORT': '.uncle/docs/VERIFICATION_REPORT.md',
    'FINAL_AUDIT': '.uncle/docs/FINAL_AUDIT.md',
}


def new_application():
    return Graph([
        Node('requirements', inputs=('BRIEF',), outputs=('REQUIREMENTS',)),
        Node('classify', inputs=('REQUIREMENTS',), outputs=('CLASSIFICATION',)),
        Node('project_plan', inputs=('REQUIREMENTS',), outputs=('PROJECT_PLAN',), approvals=('REQUIREMENTS_INTERPRETATION',),
             speculative_ok=True),
        Node('adversarial_review', inputs=('PROJECT_PLAN',), outputs=('ADVERSARIAL_REVIEW',),
             approvals=('PROJECT_PLAN',), speculative_ok=True),
        Node('updated_plan', inputs=('PROJECT_PLAN', 'ADVERSARIAL_REVIEW'), outputs=('UPDATED_PROJECT_PLAN',),
             approvals=('ADVERSARIAL_REVIEW',), speculative_ok=True),
        Node('preflight', inputs=('UPDATED_PROJECT_PLAN',), outputs=('PREFLIGHT_REPORT',),
             approvals=('UPDATED_PROJECT_PLAN',)),
        Node('implement', inputs=('UPDATED_PROJECT_PLAN', 'PROJECT_TREE'), outputs=('SOURCE',),
             approvals=('UPDATED_PROJECT_PLAN',), writes_source=True),
        Node('test_review', inputs=('SOURCE',), outputs=('TEST_REVIEW',)),
        Node('manual_checklist', inputs=('UPDATED_PROJECT_PLAN', 'SOURCE', 'TEST_REVIEW'),
             outputs=('MANUAL_CHECKLIST',)),
        Node('execute_checklist', inputs=('MANUAL_CHECKLIST', 'SOURCE'), outputs=('VERIFICATION_REPORT',)),
        Node('final_audit', inputs=('VERIFICATION_REPORT', 'TEST_REVIEW', 'SOURCE'), outputs=('FINAL_AUDIT',)),
    ], external=EXTERNAL)


def main():
    graph = new_application()
    total, path = graph.critical_path(MEASURED_SECONDS)
    print('critical path %.0fs: %s' % (total, ' -> '.join(path)))
    print('sum of all stages %.0fs' % sum(MEASURED_SECONDS.values()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
