import unittest, tempfile, os
from unittest.mock import patch
from app import ingest, clusters
class DetectionTests(unittest.TestCase):
 def test_fixture_and_idempotency(self):
  import json
  with tempfile.TemporaryDirectory() as d, patch('app.DB',os.path.join(d,'test.sqlite')):
   from app import FIXTURE
   with open(FIXTURE,encoding='utf-8') as f: posts=json.load(f)
   self.assertEqual(ingest(posts),5)
   self.assertEqual(ingest(posts),0)
   result=clusters()
   self.assertEqual(len(result),1)
   self.assertEqual(result[0]['distinct_actors'],3)
 def test_no_false_positive_single_actor(self):
  with tempfile.TemporaryDirectory() as d, patch('app.DB',os.path.join(d,'test.sqlite')):
   p=[{'id':str(i),'source':'synthetic','actor':'same','text':'identical','created_at':f'2026-10-20T08:00:0{i}Z','url':'https://example.org'} for i in range(3)]
   ingest(p)
   self.assertEqual(clusters(),[])
if __name__=='__main__': unittest.main()
