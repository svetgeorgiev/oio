"""OIO v0.3 standard-library tests. Run: python -m unittest discover -v"""
import http.client
import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager, closing
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import (Handler, clusters, database, create_investigation, ingest,
                 investigation_by_id, investigations, update_investigation, FIXTURE)


@contextmanager
def temporary_database():
    with tempfile.TemporaryDirectory() as directory, patch('app.DB', os.path.join(directory, 'test.sqlite3')):
        yield


class DetectionTests(unittest.TestCase):
    def fixture(self):
        with open(FIXTURE, encoding='utf-8') as stream:
            return json.load(stream)

    def test_fixture_and_idempotency(self):
        with temporary_database():
            self.assertEqual(ingest(self.fixture()), 5)
            self.assertEqual(ingest(self.fixture()), 0)
            result = clusters()
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['distinct_actors'], 3)
            self.assertEqual(len(result[0]['evidence']), 3)

    def test_no_false_positive_single_actor(self):
        with temporary_database():
            posts = [{'id': str(i), 'source': 'synthetic', 'actor': 'same',
                      'text': 'identical', 'created_at': f'2026-10-20T08:00:0{i}Z',
                      'url': 'https://example.org'} for i in range(3)]
            ingest(posts)
            self.assertEqual(clusters(), [])

    def test_batch_validation_is_atomic(self):
        with temporary_database():
            posts = self.fixture()
            posts[-1]['created_at'] = 'not a timestamp'
            with self.assertRaises(ValueError):
                ingest(posts)
            with database() as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM posts').fetchone()[0], 0)

    def test_separated_time_windows(self):
        with temporary_database():
            posts = self.fixture()
            for index, p in enumerate(posts[:3]):
                p['id'] = f'earlier-{index}'
                p['created_at'] = f'2026-10-19T08:00:0{index}Z'
            ingest(posts)
            self.assertEqual(clusters()[0]['distinct_actors'], 3)
            self.assertEqual(len(clusters()), 1)


class InvestigationFixture:
    """Isolated fixture shared by unit and HTTP integration tests."""
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_patcher = patch('app.DB', os.path.join(self.directory.name, 'test.sqlite3'))
        self.db_patcher.start()
        with open(FIXTURE, encoding='utf-8') as stream:
            ingest(json.load(stream))
        self.cluster_id = clusters()[0]['id']

    def tearDown(self):
        self.db_patcher.stop()
        self.directory.cleanup()


class InvestigationTests(InvestigationFixture, unittest.TestCase):
    def test_case_create_update_and_audit(self):
        record, created = create_investigation({'cluster_id': self.cluster_id})
        self.assertTrue(created)
        self.assertEqual(record['status'], 'investigating')
        same, created = create_investigation({'cluster_id': self.cluster_id})
        self.assertFalse(created)
        self.assertEqual(record['id'], same['id'])
        self.assertEqual(len(investigations()), 1)
        updated = update_investigation(record['id'], {
            'status': 'needs_context',
            'notes': 'Review evidence against legitimate amplification.',
            'alternative_explanation': 'Coordinated legitimate news sharing'
        })
        self.assertEqual(updated['status'], 'needs_context')
        self.assertEqual(len(updated['events']), 2)
        self.assertEqual(updated['events'][0]['event_type'], 'updated')
        self.assertEqual(clusters()[0]['review']['status'], 'needs_context')
        self.assertEqual(investigation_by_id(record['id'])['notes'], updated['notes'])
        # Identical save must not add audit events.
        update_investigation(record['id'], {'status': 'needs_context'})
        self.assertEqual(len(investigation_by_id(record['id'])['events']), 2)

    def test_dismissal_requires_notes(self):
        record, _ = create_investigation({'cluster_id': self.cluster_id})
        with self.assertRaises(ValueError):
            update_investigation(record['id'], {'status': 'dismissed'})
        result = update_investigation(record['id'], {'status': 'dismissed',
            'notes': 'No supporting evidence of inauthentic behaviour.'})
        self.assertEqual(result['status'], 'dismissed')

    def test_unknown_cluster_and_invalid_data(self):
        with self.assertRaises(LookupError):
            create_investigation({'cluster_id': 'nonexistent'})
        with self.assertRaises(ValueError):
            create_investigation({'cluster_id': self.cluster_id, 'title': ''})

    def test_existing_v01_schema_is_migrated_and_preserved(self):
        # Construct legacy v0.1 db to verify on-disk upgrade preserves data.
        file = os.path.join(self.directory.name, 'legacy.sqlite3')
        with patch('app.DB', file):
            import sqlite3
            with closing(sqlite3.connect(file)) as c:
                c.executescript('''CREATE TABLE posts (id TEXT PRIMARY KEY,source TEXT NOT NULL,actor TEXT NOT NULL,text TEXT NOT NULL,created_at TEXT NOT NULL,url TEXT NOT NULL,fingerprint TEXT NOT NULL);
                  CREATE TABLE reviews (cluster_id TEXT PRIMARY KEY,status TEXT NOT NULL,notes TEXT NOT NULL,updated_at TEXT NOT NULL);''')
                c.execute("INSERT INTO reviews VALUES ('legacy','unreviewed','existing note','2026-10-20T08:00:00Z')")
                c.commit()
            with database() as c:
                self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 7)
                self.assertEqual(c.execute('SELECT notes FROM reviews WHERE cluster_id=?', ('legacy',)).fetchone()[0], 'existing note')
                self.assertEqual(c.execute('SELECT count(*) FROM investigations').fetchone()[0], 0)


class APITests(InvestigationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        super().tearDown()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        data = json.dumps(body).encode() if body is not None else None
        hdr = {'Content-Type': 'application/json'}
        if data is not None:
            hdr['Content-Length'] = str(len(data))
        hdr.update(headers or {})
        conn.request(method, path, body=data, headers=hdr)
        response = conn.getresponse()
        status = response.status
        payload = json.loads(response.read())
        conn.close()
        return status, payload

    def test_api_workflow(self):
        status, stats = self.request('GET', '/api/stats')
        self.assertEqual(status, 200)
        self.assertEqual(stats['candidate_clusters'], 1)
        self.assertEqual(stats['investigations'], 0)
        status, created = self.request('POST', '/api/investigations', {'cluster_id': self.cluster_id})
        self.assertEqual(status, 201)
        identifier = created['investigation']['id']
        status, saved = self.request('POST', f'/api/investigations/{identifier}/review',
                                     {'status': 'needs_context', 'notes': 'Check alternative explanations'})
        self.assertEqual(status, 200)
        self.assertEqual(saved['investigation']['status'], 'needs_context')
        self.assertEqual(self.request('GET', '/api/investigations')[1]['investigations'][0]['id'], identifier)
        self.assertEqual(self.request('GET', f'/api/investigations/{identifier}')[1]['investigation']['id'], identifier)

    def test_dns_rebinding_host_header_is_rejected(self):
        self.assertEqual(self.request('GET', '/api/stats', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/load-fixture', headers={'Host': 'evil.example'})[0], 403)

    def test_evidence_api_roundtrip_export_and_deletion(self):
        status, created = self.request('POST', '/api/investigations', {'cluster_id': self.cluster_id})
        self.assertEqual(status, 201)
        identifier = created['investigation']['id']
        evidence = {'kind': 'context', 'title': 'Independent context',
                    'source_url': 'https://example.org/context', 'notes': 'Possible ordinary news sharing',
                    'observed_at': '2026-10-20T09:00:00Z'}
        route = f'/api/investigations/{identifier}/lab'
        self.assertEqual(self.request('POST', route + '/evidence',
            {'permission_confirmed': True, 'evidence': evidence})[0], 201)
        status, response = self.request('GET', route)
        self.assertEqual(status, 200)
        self.assertEqual(len(response['lab']['evidence_items']), 1)
        item = response['lab']['evidence_items'][0]
        self.assertEqual(item['title'], evidence['title'])
        self.assertEqual(len(response['lab']['timeline']), 4)
        status, exported = self.request('GET', route + '/export')
        self.assertEqual(status, 200)
        self.assertEqual(exported['format'], 'oio-evidence-snapshot')
        self.assertEqual(len(exported['source_posts']), 3)
        self.assertEqual(self.request('POST', route + f'/evidence/{item["id"]}/delete',
            {'reason': 'Reference no longer relevant'})[0], 200)
        self.assertEqual(self.request('GET', route)[1]['lab']['evidence_items'], [])

    def test_evidence_api_rejects_unpermitted_or_malformed_items(self):
        identifier = self.request('POST', '/api/investigations',
                                  {'cluster_id': self.cluster_id})[1]['investigation']['id']
        route = f'/api/investigations/{identifier}/lab'
        evidence = {'kind': 'observation', 'title': 'Public item', 'source_url': 'https://example.org'}
        self.assertEqual(self.request('POST', route + '/evidence',
            {'permission_confirmed': False, 'evidence': evidence})[0], 400)
        self.assertEqual(self.request('POST', route + '/evidence',
            {'permission_confirmed': True, 'evidence': {**evidence, 'source_url': 'http://localhost/private'}})[0], 400)
        self.assertEqual(self.request('GET', '/api/investigations/missing/lab')[0], 404)
        self.assertEqual(self.request('POST', route + '/import', {'permission_confirmed': True,
            'format': 'json', 'content': '[{}]'})[0], 400)
        self.assertEqual(self.request('GET', route)[1]['lab']['evidence_items'], [])

    def test_bad_requests_are_rejected(self):
        self.assertEqual(self.request('POST', '/api/investigations', {'cluster_id': self.cluster_id},
            {'Origin': 'https://untrusted.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/investigations', {'cluster_id': 'missing'})[0], 404)
        self.assertEqual(self.request('POST', '/api/investigations', {'cluster_id': self.cluster_id,
            'title': 123})[0], 400)


if __name__ == '__main__':
    unittest.main()
