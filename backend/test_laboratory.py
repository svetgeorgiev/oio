"""v0.3 Evidence Laboratory tests. No network requests or external services."""
import json
import os
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from app import (clusters, create_investigation, database, find_cluster, ingest,
                 investigation_by_id, FIXTURE)
from laboratory import (add_evidence, delete_evidence, import_evidence, lab_export,
                        lab_snapshot, parse_import, referenced_domains, valid_public_url)


class LabTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patcher = patch('app.DB', os.path.join(self.dir.name, 'test.sqlite3'))
        self.patcher.start()
        with open(FIXTURE, encoding='utf-8') as stream:
            ingest(json.load(stream))
        self.case, _ = create_investigation({'cluster_id': clusters()[0]['id']})
        self.identifier = self.case['id']

    def tearDown(self):
        self.patcher.stop()
        self.dir.cleanup()

    @staticmethod
    def item(title='Research note', url='https://example.org/research/1'):
        return {'kind': 'observation', 'title': title, 'source_url': url,
                'observed_at': '2026-10-20T08:00:30+00:00', 'notes': 'Publicly referenced record.'}

    def add(self, **overrides):
        return add_evidence(database, self.identifier,
                            {'permission_confirmed': True, 'evidence': {**self.item(), **overrides}})

    def test_add_deduplicate_and_audit(self):
        self.assertEqual(self.add(), 1)
        self.assertEqual(self.add(), 0)
        snap = lab_snapshot(database, self.identifier, find_cluster)
        self.assertEqual(len(snap['evidence_items']), 1)
        self.assertEqual(len(snap['timeline']), 4)
        self.assertEqual(len(snap['source_posts']), 3)
        self.assertEqual(len(snap['evidence_items'][0]['sha256']), 64)
        self.assertEqual(len(investigation_by_id(self.identifier)['events']), 2)
        self.assertEqual(snap['domains']['manual_reference_hosts'][0]['domain'], 'example.org')
        self.assertEqual(snap['domains']['post_text_link_hosts'], [])
        # Calling again after reconnect retains data.
        self.assertEqual(len(lab_snapshot(database, self.identifier, find_cluster)['evidence_items']), 1)

    def test_different_kinds_and_source_provenance(self):
        self.assertEqual(self.add(kind='counterevidence', notes='A legitimate event explains the timing'), 1)
        self.assertEqual(self.add(kind='context', title='Context note', observed_at=''), 1)
        snap = lab_snapshot(database, self.identifier, find_cluster)
        self.assertEqual(len(snap['evidence_items']), 2)
        self.assertEqual(len(snap['timeline']), 4)  # undated entry is not falsely dated
        self.assertEqual(snap['evidence_items'][0]['observed_at'], None)

    def test_import_csv_json_duplicate_and_atomic(self):
        header = 'kind,title,source_url,observed_at,notes\n'
        one = 'observation,Imported CSV,https://example.org/a,2026-10-20T12:00:00Z,Test\n'
        two_bad = 'observation,Bad URL,http://127.0.0.1/a,2026-10-20T12:00:00Z,Test\n'
        with self.assertRaises(ValueError):
            import_evidence(database, self.identifier,
                            {'permission_confirmed': True, 'format': 'csv', 'content': header + one + two_bad})
        self.assertEqual(lab_snapshot(database, self.identifier, find_cluster)['evidence_items'], [])
        self.assertEqual(import_evidence(database, self.identifier,
                         {'permission_confirmed': True, 'format': 'csv', 'content': header + one}), 1)
        self.assertEqual(import_evidence(database, self.identifier,
                         {'permission_confirmed': True, 'format': 'csv', 'content': header + one}), 0)
        data = json.dumps([self.item(title='JSON imported', url='https://example.org/b')])
        self.assertEqual(import_evidence(database, self.identifier,
                         {'permission_confirmed': True, 'format': 'json', 'content': data}), 1)
        self.assertEqual(len(lab_snapshot(database, self.identifier, find_cluster)['evidence_items']), 2)

    def test_import_rejects_permission_or_malformed_rows(self):
        with self.assertRaises(ValueError):
            self.add(kind='unknown')
        with self.assertRaises(ValueError):
            add_evidence(database, self.identifier, {'permission_confirmed': False, 'evidence': self.item()})
        with self.assertRaises(ValueError):
            parse_import({'permission_confirmed': True, 'format': 'json', 'content': json.dumps([{}])})
        with self.assertRaises(ValueError):
            parse_import({'permission_confirmed': True, 'format': 'csv', 'content': 'title,title\nx,y\n'})
        with self.assertRaises(ValueError):
            parse_import({'permission_confirmed': True, 'format': 'json', 'content': json.dumps([self.item()] * 101)})
        with self.assertRaises(ValueError):
            self.add(observed_at='2026-10-20T11:00:00')
        with self.assertRaises(ValueError):
            self.add(source_url='javascript:alert(1)')
        with self.assertRaises(ValueError):
            self.add(title='x' * 161)

    def test_delete_requires_reason_and_preserves_audit(self):
        self.add()
        before = lab_snapshot(database, self.identifier, find_cluster)
        item_id = before['evidence_items'][0]['id']
        with self.assertRaises(ValueError):
            delete_evidence(database, self.identifier, item_id, {'reason': 'short'})
        self.assertTrue(delete_evidence(database, self.identifier, item_id,
                                        {'reason': 'Duplicate reference removed'}))
        after = lab_snapshot(database, self.identifier, find_cluster)
        self.assertEqual(len(after['evidence_items']), 0)
        self.assertEqual(after['audit_events'][0]['event_type'], 'evidence_deleted')
        self.assertNotIn('Research note', after['audit_events'][0]['summary'])

    def test_export_has_source_snapshot_hashes_and_parameters(self):
        self.add()
        result = lab_export(database, self.identifier, find_cluster)
        self.assertEqual(result['format'], 'oio-evidence-snapshot')
        self.assertEqual(result['analysis_parameters']['window_seconds'], 180)
        self.assertEqual(result['analysis_parameters']['minimum_distinct_source_actor_pairs'], 3)
        self.assertEqual(len(result['source_posts']), 3)
        self.assertTrue(all(len(p['sha256']) == 64 for p in result['source_posts']))
        self.assertEqual(result['investigation']['id'], self.identifier)
        self.assertEqual(len(result['limitations']), 5)

    def test_wrong_investigation_rejected(self):
        with self.assertRaises(LookupError):
            add_evidence(database, 'missing', {'permission_confirmed': True, 'evidence': self.item()})
        with self.assertRaises(LookupError):
            lab_snapshot(database, 'missing', find_cluster)

    def test_domains_extracted_without_fetching(self):
        self.assertEqual(referenced_domains('https://site.example/a https://site.example/b and http://news.example/x.'),
                         ['news.example', 'site.example'])
        for source_url in ('http://127.0.0.1/admin', 'http://localhost:8080/', 'https://intranet.local',
                           'https://user:secret@example.org/', 'file:///etc/passwd', 'https://example.org:9999'):
            with self.subTest(source_url=source_url), self.assertRaises(ValueError):
                valid_public_url(source_url)

    def test_migration_preserves_v02_investigations(self):
        self.add()
        with database() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 7)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM investigations').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM posts').fetchone()[0], 5)


if __name__ == '__main__':
    unittest.main()
