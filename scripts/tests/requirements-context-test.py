import importlib.util
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('requirements_context',Path(__file__).resolve().parents[1]/'lib/requirements-context.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Requirements(unittest.TestCase):
    def document(self):
        return '\n'.join('## '+name+'\nNo additional interpretation.\n' for name in module.SECTIONS)

    def test_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'report.md'
            p.write_text(self.document())
            module.validate(p)
            for text in ['Compacting report', self.document()+'\n## Constraints\nDuplicate',self.document()+'\n```\nunclosed']:
                p.write_text(text)
                with self.assertRaises(ValueError): module.validate(p)

    def test_packet_is_shallow_and_refreshes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'nested').mkdir()
            (root/'nested/secret.txt').write_text('not part of inventory')
            brief=root/'REQUIREMENTS.md'
            brief.write_text('Hello world')
            first=module.render(root)
            self.assertIn('Hello world',first)
            self.assertNotIn('secret.txt',first)
            brief.write_text('Changed brief')
            self.assertNotEqual(first,module.render(root))

    @unittest.skipUnless(shutil.which('bash'), 'Bash required')
    def test_resume_validates_without_generation(self):
        root=Path(__file__).resolve().parents[2]
        block=(root/'scripts/stagegate.sh').read_text().split('        VALIDATE_REQUIREMENTS)\n',1)[1].split('        WAIT_REQUIREMENTS_APPROVAL)',1)[0]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'REQUIREMENTS_INTERPRETATION.md'
            harness=f'ROOT="{root}"\nrequire_artifact() {{ test -s "$1"; }}; set_state() {{ echo "$1" > state; }}; run_stage() {{ exit 99; }}\ncase validate in\nvalidate)\n'+block+'esac\n'
            p.write_text('bad')
            for _ in range(2):
                self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,1)
            p.write_text(self.document())
            self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,0)
            self.assertEqual((Path(d)/'state').read_text().strip(),'WAIT_REQUIREMENTS_APPROVAL')

if __name__=='__main__': unittest.main()
