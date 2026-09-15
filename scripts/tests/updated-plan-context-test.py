import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('context',Path(__file__).resolve().parents[1]/'lib/updated-plan-context.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Revision(unittest.TestCase):
    def test_family_snapshot_and_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); state=root/'.uncle/workflow'; state.mkdir(parents=True)
            (root/'PROJECT_PLAN.md').write_text('app plan')
            (state/'CHANGE_PLAN.pre-review.md').write_text('original change plan')
            review=root/'ADVERSARIAL_REVIEW.md'; review.write_text('AR-1 original finding')
            app=module.render(root,state,'app'); change=module.render(root,state,'change')
            self.assertIn('app plan',app)
            self.assertNotIn('original change plan',app)
            self.assertIn('original change plan',change)
            review.write_text('AR-2 new finding')
            self.assertNotEqual(app,module.render(root,state,'app'))

    @unittest.skipUnless(shutil.which('bash'),'Bash required')
    def test_validation_retries_do_not_generate_or_replace_snapshot(self):
        root=Path(__file__).resolve().parents[2]
        for script in ('stagegate.sh','change-workflow.sh'):
            source=(root/'scripts'/script).read_text()
            block=source.split('        VALIDATE_UPDATED_PLAN)\n',1)[1].split('        WAIT_UPDATED_PLAN_APPROVAL)',1)[0]
            harness='verify_approval() { :; }; require_file() { test -s "$1"; }; check_document_budget() { test ! -e bad; }; require_artifact() { require_file "$1" && check_document_budget "$1" || exit 1; }; set_state() { echo "$1" > state; }; run_stage() { exit 99; }; run_claude() { exit 99; };\ncase validate in\nvalidate)\n'+block+'esac\n'
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)
                (p/'CHANGE_PLAN.md').write_text('saved plan')
                (p/'UPDATED_PROJECT_PLAN.md').write_text('saved plan')
                (p/'CHANGE_PLAN.pre-review.md').write_text('original')
                (p/'bad').touch()
                for _ in range(2):
                    self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,1)
                (p/'bad').unlink()
                self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,0)
                self.assertEqual((p/'state').read_text().strip(),'WAIT_UPDATED_PLAN_APPROVAL')
                self.assertEqual((p/'CHANGE_PLAN.pre-review.md').read_text(),'original')

if __name__=='__main__': unittest.main()
