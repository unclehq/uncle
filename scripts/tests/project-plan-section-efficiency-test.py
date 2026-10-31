#!/usr/bin/env python3
"""Hermetic regressions for section cost, stage ownership and unchanged output."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent
import project_plan_sections as sections
import self_hosted
import worker_schemas

spec = importlib.util.spec_from_file_location('section_fixture', Path(__file__).with_name('project-plan-sections-test.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Efficiency(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.directory = self.root / '.uncle/workflow/project-plan-sections'
        self.directory.mkdir(parents=True)
        self.logs = self.directory.parent / 'logs'
        self.logs.mkdir()
        docs = self.directory.parent / 'documents'
        docs.mkdir()
        (docs / 'REQUIREMENTS_INTERPRETATION.json').write_text('{"requirement":"KEEP EXACT 12.75 THRESHOLD"}')
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.root / 'absent-config'),
                                     'UNCLE_PROJECT_ROOT': str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def prompt(self, name, **mode):
        return sections.build_prompt(name, self.directory,
                                     (ROOT / 'prompts/project-plan-investigate.md').read_text(), **mode)

    def test_full_prompts_have_shared_prefix_inputs_once_and_no_stage_writes(self):
        for mode in ({}, {'json_mode': True}, {'json_mode': True, 'blocks': True}):
            prompts = [self.prompt(n, **mode) for n in sections.WORKERS]
            prefixes = [p.split('## Assigned planning guidance')[0] for p in prompts]
            self.assertEqual(len(set(prefixes)), 1)
            for text in prompts:
                self.assertEqual(text.count('KEEP EXACT 12.75 THRESHOLD'), 1)
                self.assertNotIn('Before finishing this stage, write or update', text)
                self.assertNotIn('Perform a final consistency pass across', text)
                self.assertNotIn('Write your complete plan', text)
                self.assertNotIn('## Launching the finished application', text)
                self.assertNotIn('Your plan must cover:', text)
                self.assertIn('without creating a project commit', text)
                self.assertIn('--no-gpg-sign', text)
                self.assertIn('Do not invent a requirement', text)
            self.assertNotIn('Defect injections are independent', self.prompt('behaviors', **mode))
            self.assertIn('Defect injections are independent', self.prompt('defects', **mode))
            self.assertNotIn('Use this invariant table', self.prompt('design', **mode))
            self.assertIn('Use this invariant table', self.prompt('guards', **mode))

    def test_gate_wrapper_does_not_reintroduce_stage_duties(self):
        source = self.root / 'prompt.md'
        source.write_text(self.prompt('behaviors', blocks=True))
        result = subprocess.run(['bash', '-c', '. "$1/scripts/lib/gates.sh"; LOG_DIR="$2"; gated_prompt "$3" project-plan-section-behaviors',
                                 '_', str(ROOT), str(self.logs), str(source)], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()).read_bytes(), source.read_bytes())

    def test_fixed_stub_assembly_is_byte_identical_to_baseline(self):
        fixture.good_files(self.directory)
        text = sections.assemble(self.directory)
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),
                         '33eb9e660b5248b90956bcfa0ef9e721e857954f24e00c108a6037ce34857be1')

    def setup_packet(self):
        packet = {'schema': 'uncle.artifact/v1', 'kind': worker_schemas.SECTION_MODEL_KIND,
                  'sections': [{'heading': '6. Observable behaviors', 'blocks': [{'kind': 'prose', 'text': 'Exact content.'}]}]}
        setup = self_hosted._http_setup('agent', {}, self.prompt('behaviors', blocks=True), self.root, True, packet['kind'])
        return packet, setup

    def test_section_packet_generated_once_without_closing_request(self):
        packet, (prompt, policy, schema, name, limit, seconds) = self.setup_packet()
        reply = {'choices': [{'message': {'content': json.dumps(packet)}, 'finish_reason': 'stop'}],
                 'usage': {'prompt_tokens': 100, 'completion_tokens': 30}}
        with patch.object(http_agent, 'interruptible_chat', return_value=reply) as chat, \
                patch.object(http_agent, 'constrained_completion', side_effect=AssertionError('duplicate generation')):
            usage = {}
            answer, requests = http_agent.run_agent({}, prompt, policy, limit, final_schema=schema, final_name=name, usage=usage)
        self.assertEqual((chat.call_count, requests, usage['output_tokens']), (1, 1, 30))
        self.assertEqual(json.loads(answer), packet)
        self.assertEqual({t['function']['name'] for t in policy.tools()}, {'read_file', 'grep', 'list_dir'})
        self.assertIn('Deliver it once', chat.call_args.args[2][0]['content'])
        self.assertEqual(http_agent.prefetch_context(prompt, policy), '')

    def test_invalid_packet_is_retained_for_repair_and_still_rejected(self):
        packet, (prompt, policy, schema, name, limit, _) = self.setup_packet()
        bad = json.dumps(dict(packet, sections="not an array"))
        reply = {'choices': [{'message': {'content': bad}, 'finish_reason': 'stop'}]}
        with patch.object(http_agent, 'interruptible_chat', return_value=reply), \
                patch.object(http_agent, 'constrained_completion', side_effect=AssertionError('duplicate generation')) as closing:
            with self.assertRaisesRegex(ValueError, 'Unrepaired draft.*sections must be array'):
                http_agent.run_agent({}, prompt, policy, limit, final_schema=schema, final_name=name)
        self.assertEqual(closing.call_count, 0)
        self.assertEqual((self.root / '.uncle/workflow/http-answer-repair.json').exists(), False)

    def test_all_section_kinds_are_read_only_other_stages_keep_write_tools(self):
        for kind in (worker_schemas.SECTION_KIND, worker_schemas.SECTION_MODEL_KIND, worker_schemas.OUTLINE_KIND):
            policy = self_hosted._http_setup('agent', {}, '', self.root, True, kind)[1]
            self.assertFalse(policy.write)
            self.assertFalse(policy.shell)
        policy = self_hosted._http_setup('agent', {}, '', self.root, True, None)[1]
        self.assertTrue(policy.write)
        self.assertTrue(policy.shell)

    def test_outline_envelope_selects_existing_schema_on_first_request(self):
        prompt = self.prompt('outline', blocks=True)
        self.assertEqual(self_hosted.reviewer_artifact_kind(prompt), worker_schemas.OUTLINE_KIND)
        # The example is itself valid, including strings for numbers and arrays
        # for components/steps; the old prompt had no discoverable envelope.
        example = json.loads(prompt.split('Use this envelope and array/object structure (replace the example values):\n')[1])
        http_agent.conforms(example, worker_schemas.outline_packet())
        self.assertEqual(self_hosted.config_stage('project-plan-stage-duties', {}), 'project-plan')
        result = subprocess.run(['bash', '-c', '. "$1/scripts/lib/stage-config.sh"; uncle_config_stage project-plan-stage-duties',
                                 '_', str(ROOT)], text=True, capture_output=True)
        self.assertEqual((result.returncode, result.stdout), (0, 'project-plan'), result.stderr)

    def finish(self, mode='good'):
        # Stub agent performs one write. No model, server, Git commit or signer.
        shell = '''
ROOT="$1"; LOG_DIR="$2"; directory="$3"; mode="$4"
run_claude() {
    echo call >> calls
    [[ "$mode" != fail ]] || return 1
    if [[ "$mode" == missing ]]; then printf '.DS_Store\n' > .gitignore
    else printf '# Keep user rules\ncustom-cache/\n.env\n.env.*\n.DS_Store\nnode_modules/\ndist/\nbuild/\n' > .gitignore; fi
    printf '%s\n' '{"type":"result","result":"PROJECT_PLAN_STAGE_COMPLETE"}' > "$LOG_DIR/project-plan-stage-duties.jsonl"
}
. "$ROOT/scripts/lib/project-plan-stage.sh"
project_plan_stage_finish "$directory" "$PWD/plan.md"
'''
        return subprocess.run(['bash', '-c', shell, '_', str(ROOT), str(self.logs), str(self.directory), mode],
                              cwd=self.root, text=True, capture_output=True)

    def test_stage_duty_once_and_verified_even_on_reentry(self):
        (self.root / 'plan.md').write_text('Selected stack: npm. Owns: .gitignore')
        for _ in range(3):
            result = self.finish()
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'calls').read_text().splitlines(), ['call'])
        self.assertTrue((self.directory / 'stage-duties.json').exists())
        self.assertIn('custom-cache/', (self.root / '.gitignore').read_text())
        (self.root / '.gitignore').write_text('.DS_Store\n')
        self.assertNotEqual(self.finish().returncode, 0)
        self.assertEqual((self.root / 'calls').read_text().splitlines(), ['call'])
        # A fresh stage directory has a fresh duty, without requiring a commit.
        self.directory = self.directory.parent / 'next-stage'
        self.directory.mkdir()
        self.assertEqual(self.finish().returncode, 0)
        self.assertEqual((self.root / 'calls').read_text().splitlines(), ['call', 'call'])

    def test_ignore_verifier_never_inherits_signing_or_external_excludes(self):
        (self.root / 'plan.md').write_text('Selected stack: npm')
        signer = self.root / 'fake-signer'
        signer.write_text('#!/bin/sh\necho invoked >> "' + str(self.root / 'signer-called') + '"\nexit 99\n')
        signer.chmod(0o755)
        excludes = self.root / 'external-ignores'
        excludes.write_text('*\n')
        with patch.dict(os.environ, {'GIT_CONFIG_COUNT': '3', 'GIT_CONFIG_KEY_0': 'commit.gpgsign',
                                    'GIT_CONFIG_VALUE_0': 'true', 'GIT_CONFIG_KEY_1': 'gpg.program',
                                    'GIT_CONFIG_VALUE_1': str(signer), 'GIT_CONFIG_KEY_2': 'core.excludesFile',
                                    'GIT_CONFIG_VALUE_2': str(excludes)}):
            self.assertNotEqual(self.finish('missing').returncode, 0)
            result = self.finish()
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'signer-called').exists())

    def test_failed_or_missing_ignore_duty_never_records_success(self):
        (self.root / 'plan.md').write_text('Selected stack: npm')
        for mode in ('fail', 'missing'):
            self.assertNotEqual(self.finish(mode).returncode, 0)
            self.assertFalse((self.directory / 'stage-duties.json').exists())
            self.assertFalse((self.directory / 'stage-duties.lock').exists())


if __name__ == '__main__':
    unittest.main()
