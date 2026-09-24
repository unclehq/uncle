#!/usr/bin/env python3
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('packets',ROOT/'scripts/lib/test_review_packets.py')
packets=importlib.util.module_from_spec(spec); spec.loader.exec_module(packets)

class TestReviewPacketTests(unittest.TestCase):
 def test_conflicting_duplicate_retains_evidence_and_conservative_status(self):
  rows={}
  packets.merge_row(rows,{'id':'NEGATIVE','status':'PASS','evidence':'one injection passed'},'oracle.json')
  packets.merge_row(rows,{'id':'NEGATIVE','status':'BLOCKED-HUMAN','evidence':'two injections lack evidence'},'oracle.json')
  self.assertEqual(rows['NEGATIVE']['status'],'BLOCKED-HUMAN')
  self.assertIn('one injection passed',rows['NEGATIVE']['evidence'])
  self.assertIn('two injections lack evidence',rows['NEGATIVE']['evidence'])
 def test_malformed_worker_degrades_to_its_assigned_row(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); (root/'coverage.json').write_text('{broken')
   for name, identifier in [('assertions','ASSERTIONS'),('oracle','ORACLE')]:
    rows=[{'id':identifier,'status':'PASS','evidence':'ok'}]
    if name=='oracle': rows.append({'id':'NEGATIVE','status':'PASS','evidence':'ok'})
    (root/(name+'.json')).write_text(json.dumps({'schema':'uncle.artifact/v1','kind':'test-review-worker-packet','rows':rows}))
   old=os.getcwd(); os.chdir(root)
   try:
    packets.main(root,root/'out.json','coverage','assertions','oracle')
   finally: os.chdir(old)
   coverage=next(row for row in json.loads((root/'out.json').read_text())['rows'] if row['id']=='COVERAGE')
   self.assertEqual(coverage['status'],'BLOCKED-SETUP')
 def test_lowercase_known_id_is_normalized(self):
  rows={}; packets.merge_row(rows,{'id':packets.normalized_id('coverage'),'status':'PASS','evidence':'ok'},'coverage.json')
  self.assertIn('COVERAGE',rows)

if __name__=='__main__': unittest.main()
