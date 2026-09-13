from pathlib import Path
import unittest,json
root=Path(__file__).resolve().parents[2]
source=(root/'scripts/lib/change-pr.sh').read_text().split("<<'PY'",1)[1].split('\n',1)[1].split('\nPY\n',1)[0]
ns={};exec(source[:source.rindex('\ntry:\n    main()')],ns)
class Tests(unittest.TestCase):
 def setUp(self):
  self.j=dict(url='',base_repo='owner/repo',head_repo='owner/repo',head_branch='change',base_branch='main',intended_head='abc',phase='unknown')
  ns.update(validate=lambda j:None,remote_sha=lambda j:'abc',save=lambda j:None)
 def test_absent_recovers(self):
  ns['gh']=lambda *a:'[]';ns['reconcile_absent'](self.j);self.assertEqual(self.j['phase'],'published')
 def test_existing_or_malformed_blocks(self):
  for result in ('[{}]','{}'):
   ns['gh']=lambda *a:result
   with self.assertRaises(ValueError):ns['reconcile_absent'](self.j)
 def test_known_url_blocks(self):
  self.j['url']='https://github.com/owner/repo/pull/1'
  with self.assertRaises(ValueError):ns['reconcile_absent'](self.j)
 def test_remote_drift_blocks(self):
  ns['gh']=lambda *a:'[]';ns['remote_sha']=lambda j:'different'
  with self.assertRaises(ValueError):ns['reconcile_absent'](self.j)
unittest.main()
