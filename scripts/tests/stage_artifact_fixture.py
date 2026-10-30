"""Canonical deliveries for the runner and supervision driver fixtures."""
import json
import os
from pathlib import Path
import sys


def packet(kind, **fields):
    return dict(schema='uncle.artifact/v1', kind=kind, **fields)


def deliver(success):
    target = os.environ.get('UNCLE_ARTIFACT_DELIVERY')
    if not target:
        return
    path = Path(target)
    if path.stem == 'requirements':
        # A syntactically valid delivery with an empty required section reaches
        # the real requirements validator, after the publication boundary.
        sections = {key: 'Fixture content.' for key in (
            'required_functionality', 'optional_functionality', 'constraints',
            'user_visible_behaviors', 'system_behaviors', 'failure_behaviors',
            'ambiguities', 'assumptions', 'explicit_non_goals', 'definition_of_done')}
        if not success:
            sections['required_functionality'] = ''
        payload = packet('requirements-interpretation', sections=sections)
    elif path.stem == 'change-planning-bundle':
        if not success:
            return  # Both planning passes must report their missing delivery.
        payload = packet('change-planning-bundle',
            baseline_report=packet('baseline-report', narrative='# Baseline', verification_commands='true'),
            change_spec=packet('change-spec', narrative='# Specification',
                               acceptance_criteria=[dict(id='AC-1', criterion='Change it.', verification='true')]),
            change_plan=packet('change-plan', narrative='# Change plan'))
    else:
        return  # Later stages intentionally have no fixture delivery.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + '\n')


if __name__ == '__main__':
    deliver(sys.argv[1] == '1')
