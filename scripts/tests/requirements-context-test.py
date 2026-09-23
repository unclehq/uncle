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

    def test_direct_json_response_is_validated_exported_and_rendered(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            interp=root/'REQUIREMENTS_INTERPRETATION.md'
            payload={'schema':'uncle.artifact/v1','kind':'requirements-interpretation',
                     'sections':{name.lower().replace(' ','_').replace('-','_'):'No additional interpretation.'
                                 for name in module.SECTIONS}}
            import json
            interp.write_text(json.dumps(payload))
            module.validate(interp, root)
            text=interp.read_text()
            self.assertIn('## 1. Required functionality', text)
            stored=json.loads((root/'.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json').read_text())
            self.assertIn('required_functionality', stored['sections'])

    def test_direct_json_response_missing_section_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            interp=Path(d)/'REQUIREMENTS_INTERPRETATION.md'
            import json
            interp.write_text(json.dumps({'schema':'uncle.artifact/v1','kind':'requirements-interpretation','sections':{}}))
            with self.assertRaises(ValueError):
                module.validate(interp, Path(d))

    def test_fenced_json_response_still_validates(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            interp=root/'REQUIREMENTS_INTERPRETATION.md'
            payload={'schema':'uncle.artifact/v1','kind':'requirements-interpretation',
                     'sections':{name.lower().replace(' ','_').replace('-','_'):'No additional interpretation.'
                                 for name in module.SECTIONS}}
            import json
            interp.write_text('```json\n'+json.dumps(payload)+'\n```')
            module.validate(interp, root)
            self.assertIn('## 1. Required functionality', interp.read_text())

    def test_json_export_and_render_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); docs=root/'.uncle/docs'; docs.mkdir(parents=True)
            interpretation=docs/'REQUIREMENTS_INTERPRETATION.md'
            interpretation.write_text(self.document())
            module.export_json(interpretation, root)
            self.assertTrue((root/'.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json').is_file())
            module.render_json(root)
            module.validate(interpretation)

    def test_json_export_rejects_invalid_document(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); docs=root/'.uncle/docs'; docs.mkdir(parents=True)
            interpretation=docs/'REQUIREMENTS_INTERPRETATION.md'
            interpretation.write_text('Compacting report')
            with self.assertRaises(ValueError):
                module.export_json(interpretation, root)
            self.assertFalse((root/'.uncle/workflow/documents/REQUIREMENTS_INTERPRETATION.json').exists())

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
            (Path(d)/'.uncle/docs').mkdir(parents=True)
            p=Path(d)/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md'
            harness=f'ROOT="{root}"\nrequire_artifact() {{ test -s "$1"; }}; set_state() {{ echo "$1" > state; }}; run_stage() {{ exit 99; }}\ncase validate in\nvalidate)\n'+block+'esac\n'
            p.write_text('bad')
            for _ in range(2):
                self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,1)
            p.write_text(self.document())
            self.assertEqual(subprocess.run(['bash','-c',harness],cwd=d,capture_output=True).returncode,0)
            self.assertEqual((Path(d)/'state').read_text().strip(),'WAIT_REQUIREMENTS_APPROVAL')

if __name__=='__main__': unittest.main()
