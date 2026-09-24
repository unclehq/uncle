#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CompactProjectPlanPrompt(unittest.TestCase):
    def test_self_hosted_requirements_does_not_use_the_merged_two_artifact_prompt(self):
        stagegate = (ROOT / 'scripts/stagegate.sh').read_text(encoding='utf-8')
        self.assertIn('merged_requirements_plan_enabled()', stagegate)
        self.assertIn('! stage_uses_self_hosted requirements AGENT', stagegate)
        self.assertIn('! stage_uses_self_hosted project-plan AGENT', stagegate)
        run_stage = stagegate.index('run_stage()')
        requirements = stagegate[stagegate.index('        REQUIREMENTS)', run_stage):stagegate.index('        PROJECT_PLAN)', run_stage)]
        self.assertIn('if merged_requirements_plan_enabled; then', requirements)

    def test_requirements_runner_inherits_project_plan_runner_with_its_model(self):
        stagegate = (ROOT / 'scripts/stagegate.sh').read_text(encoding='utf-8')
        self.assertIn('requirements|requirements-investigate) printf', stagegate)
        self.assertIn('requirements|requirements-investigate) lookup_stage="project-plan"', stagegate)
        self.assertIn('uncle_effective_stage_effort "$(stage_runner_config_name "$1")"', stagegate)
        self.assertIn('runner_stage="$(stage_runner_config_name "$log_name")"', stagegate)
        self.assertIn('uncle_resolve_stage_runner "$runner_stage" AGENT', stagegate)
    def test_requirements_prompts_embed_the_selected_brief(self):
        stagegate = (ROOT / 'scripts/stagegate.sh').read_text(encoding='utf-8')
        start = stagegate.index('bind_requirements_source()')
        end = stagegate.index('\nrun_claude()', start)
        binding = stagegate[start:end]
        self.assertIn('requirements-plan.md', binding)
        self.assertIn('requirements-investigate.md', binding)
        self.assertIn('requirements-context.py', binding)
        self.assertIn('Interpret this brief, not the workflow prompt', binding)
        self.assertIn('bind_requirements_source "$effective_prompt" "$log_name" "$prompt_file"', stagegate)

    def test_project_plan_bypasses_generic_gates_and_evidence_index(self):
        source = (ROOT / 'scripts/lib/gates.sh').read_text()
        start = source.index('    # Review-parent synthesis')
        end = source.index('\n    local is_plan=', start)
        compact = source[start:end]
        self.assertIn('project-plan|change-plan|updated-plan', compact)
        self.assertIn('project-plan-investigate)', compact)
        self.assertIn('completed investigation and REQUIREMENTS_INTERPRETATION JSON', compact)
        self.assertIn('approved BASELINE_REPORT and CHANGE_SPEC', compact)
        self.assertIn('Do not inspect project source,', compact)
        self.assertIn('return 0', compact)

    def test_adversarial_workers_receive_only_named_canonical_inputs(self):
        app = (ROOT / 'scripts/stagegate.sh').read_text()
        change = (ROOT / 'scripts/change-workflow.sh').read_text()
        self.assertIn('REQUIREMENTS_INTERPRETATION.json` and `.uncle/workflow/documents/PROJECT_PLAN.json', app)
        self.assertIn('CHANGE_PLAN.json` and `.uncle/workflow/documents/CHANGE_SPEC.json', change)
        worker = (ROOT / 'prompts/change/adversarial-review-worker.md').read_text()
        self.assertIn('Return exactly one JSON object', worker)

    def test_self_hosted_project_plan_uses_driver_formatting_not_a_second_model_call(self):
        stagegate = (ROOT / 'scripts/stagegate.sh').read_text(encoding='utf-8')
        start = stagegate.index('        PROJECT_PLAN)', stagegate.index('run_stage()'))
        block = stagegate[start:stagegate.index('        ADVERSARIAL_REVIEW)', start)]
        self.assertIn('export-project-plan', block)
        self.assertIn('render-project-plan', block)
        self.assertIn('Project-plan fast path:', block)
        self.assertNotIn('project-plan-format-prompt.md', block)


if __name__ == '__main__':
    unittest.main()
