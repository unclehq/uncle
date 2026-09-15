import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('context',Path(__file__).resolve().parents[1]/'lib/adversarial-context.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CLEAN='## Overall assessment\nNo findings.\n'
FINDING='## AR-001: Missing behavior\n- Severity: High\n- References: REQ-1\n- Failure: Missing output\n- Fix: Add output\n- Verify: Assert output\n'+CLEAN.replace('No findings.','Revision required.')

class Review(unittest.TestCase):
    def test_formats(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'review'
            for text in (CLEAN,FINDING, FINDING.replace("## Overall assessment", "## 5. Overall assessment"), CLEAN.replace("## Overall assessment", "## 5) **Overall assessment**")):
                p.write_text(text); module.validate(p)
            for text in ('Compacting report', '## Overall assessment\n\n## Another heading\nNo findings.',FINDING.replace('- Verify: Assert output\n',''),FINDING+FINDING):
                p.write_text(text)
                with self.assertRaises(ValueError): module.validate(p)

    def test_packet_selects_family_and_refreshes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'PROJECT_PLAN.md').write_text('app plan')
            (root/'CHANGE_PLAN.md').write_text('change plan')
            self.assertNotIn('change plan',module.render(root,'app'))
            self.assertIn('change plan',module.render(root,'change'))
            first=module.render(root,'app')
            (root/'PROJECT_PLAN.md').write_text('changed')
            self.assertNotEqual(first,module.render(root,'app'))

    @unittest.skipUnless(shutil.which('bash'),'Bash required')
    def test_resume_does_not_regenerate(self):
        root=Path(__file__).resolve().parents[2]
        for script,nextcase,target in [('stagegate.sh','WAIT_REVIEW_ACKNOWLEDGEMENT','WAIT_REVIEW_ACKNOWLEDGEMENT'),('change-workflow.sh','WAIT_PLAN_APPROVAL','WAIT_PLAN_APPROVAL')]:
            text=(root/'scripts'/script).read_text()
            block=text.split('        VALIDATE_ADVERSARIAL_REVIEW)\n',1)[1].split('        '+nextcase+')',1)[0]
            harness=f'STATE_DIR=.\nsupervision_validation_failed() {{ :; }};\nROOT="{root}"\nverify_approval() {{ :; }}; check_document_budget() {{ :; }}; set_state() {{ echo "$1" > state; }}; run_codex() {{ exit 99; }}; run_stage() {{ exit 99; }}\ncase validate in\nvalidate)\n'+block+'esac\n'
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'ADVERSARIAL_REVIEW.md'
                p.write_text('bad')
                for _ in range(2):
                    self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,1)
                p.write_text(CLEAN)
                self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,0)
                self.assertEqual((Path(d)/'state').read_text().strip(),target)

if __name__=='__main__': unittest.main()
