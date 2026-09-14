import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts/lib/project-git.sh'


class ProjectGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)

    def ensure(self, folder):
        return subprocess.run(['bash','-c','source "$1"; uncle_ensure_project_git','test',str(HELPER)],cwd=folder,env=self.env,capture_output=True,text=True)

    def test_initializes_once_without_commit_or_config_change(self):
        result=self.ensure(self.root)
        self.assertEqual(result.returncode,0,result.stderr)
        config=(self.root/'.git/config').read_bytes()
        head=subprocess.run(['git','rev-parse','--verify','HEAD'],cwd=self.root,env=self.env,capture_output=True)
        self.assertNotEqual(head.returncode,0)
        self.assertEqual(self.ensure(self.root).stdout,'')
        self.assertEqual((self.root/'.git/config').read_bytes(),config)

    def test_parent_repository_is_reused(self):
        self.assertEqual(self.ensure(self.root).returncode,0)
        child=self.root/'project space';child.mkdir()
        self.assertEqual(self.ensure(child).returncode,0)
        self.assertFalse((child/'.git').exists())

    def test_broken_repository_is_not_reinitialized(self):
        (self.root/'.git').write_text('gitdir: missing\n')
        self.assertNotEqual(self.ensure(self.root).returncode,0)
        self.assertEqual((self.root/'.git').read_text(),'gitdir: missing\n')

    def test_complete_workflows_accept_new_repository_without_commits(self):
        for driver, document, state in [('stagegate.sh','REQUIREMENTS.md','COMPLETE'),
                                         ('change-workflow.sh','CHANGE_REQUEST.md','1:COMPLETE')]:
            project=self.root/driver;project.mkdir()
            workflow=project/'.uncle/workflow';workflow.mkdir(parents=True)
            (workflow/'state').write_text(state+'\n')
            (project/document).write_text('# Project\nFixture brief.\n')
            result=subprocess.run(['bash',str(ROOT/'scripts'/driver)],cwd=project,
                env=dict(self.env,UNCLE_PROJECT_ROOT=str(project),WORKFLOW_CLOSE_ISSUE='0'),
                capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue((project/'.git').is_dir())
            head=subprocess.run(['git','rev-parse','--verify','HEAD'],cwd=project,env=self.env,capture_output=True)
            self.assertNotEqual(head.returncode,0)

    def test_help_does_not_initialize(self):
        for driver in ('stagegate.sh','change-workflow.sh'):
            result=subprocess.run(['bash',str(ROOT/'scripts'/driver),'--help'],env=dict(self.env,UNCLE_PROJECT_ROOT=str(self.root)),capture_output=True)
            self.assertEqual(result.returncode,0)
            self.assertFalse((self.root/'.git').exists())


if __name__=='__main__': unittest.main()
