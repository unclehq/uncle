import importlib.util
from pathlib import Path
import tempfile
import subprocess
import shutil
import unittest
spec = importlib.util.spec_from_file_location('audit_context', Path(__file__).resolve().parents[1]/'lib/final-audit-context.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
HEADER = '## Findings\n\n| ID | Evidence | Required correction | Blocks |\n|---|---|---|---|\n'

class Audit(unittest.TestCase):
    def test_formats(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'audit.md'
            for text in [HEADER+'\nREADY\n', HEADER+'| FA-1 | file:1 | repair | YES |\n\nNOT READY\n']:
                p.write_text(text)
                module.validate(p)
            for text in ['READY', HEADER+'| FA-1 | file:1 | repair | YES |\nREADY\n', HEADER+'\nNOT READY\n', HEADER+'| FA-1 | x | y | maybe |\nREADY\n']:
                p.write_text(text)
                with self.assertRaises((ValueError, IndexError)):
                    module.validate(p)

    @unittest.skipUnless(shutil.which('bash'), 'Bash required')
    def test_saved_validation_does_not_invoke_reviewer(self):
        root = Path(__file__).resolve().parents[2]
        for script in ('stagegate.sh', 'change-workflow.sh'):
            source = (root/'scripts'/script).read_text()
            block = source.split('        VALIDATE_AUDIT)\n', 1)[1].split('        WAIT_AUDIT_OVERRIDE)', 1)[0]
            with tempfile.TemporaryDirectory() as d:
                path = Path(d)
                (path/'verification.manifest').write_text('snapshot')
                preamble = f'ROOT="{root}"\nSTATE_DIR=.\nVERDICT_FILE=verdict\nDIFF_GATE=0\nAUDIT_GATE=1\n'
                preamble += 'require_file() { test -s "$1"; }; check_verification_inputs() { :; }; hash_file() { echo hash; }; classify_audit_verdict() { echo READY; }; set_state() { echo "$1" > state; }; change_pr_engine() { :; }; git() { return 1; }; run_codex() { exit 99; }; run_stage() { exit 99; };\n'
                harness = preamble + 'case VALIDATE_AUDIT in\nVALIDATE_AUDIT)\n' + block + 'esac\n'
                audit = path/'FINAL_AUDIT.md'
                audit.write_text('malformed')
                for _ in range(2):
                    result = subprocess.run(['bash', '-c', harness], cwd=d, capture_output=True)
                    self.assertEqual(result.returncode, 1)
                    self.assertFalse((path/'state').exists())
                audit.write_text(HEADER+'\nREADY\n')
                result = subprocess.run(['bash', '-c', harness], cwd=d, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((path/'state').read_text().strip(), 'COMPLETE')

    def test_packet_refreshes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/'VERIFICATION_REPORT.md'
            p.write_text('old evidence')
            first=module.render(root,root/'.uncle/workflow')
            p.write_text('new evidence')
            second=module.render(root,root/'.uncle/workflow')
            self.assertIn('new evidence',second)
            self.assertNotEqual(first,second)

if __name__=='__main__': unittest.main()
