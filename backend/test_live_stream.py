"""v0.4 live research tests: no real network or production database access."""
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import Handler, database, ingest, clusters, create_investigation, find_cluster
from laboratory import lab_export
from live_stream import (CaptureManager, init_schema, insert_record, normalize_live_event,
                         recent_posts, live_count, prune_expired, validate_config)

DIDS = [f'did:plc:{ch * 24}' for ch in 'abc']


def sample_event(index=0, text='Example research phrase', operation='create'):
    return {'kind':'commit', 'did':DIDS[index % 3], 'time_us':int(time.time()*1_000_000),
            'commit':{'operation':operation, 'collection':'app.bsky.feed.post',
                      'rkey':f'example{index}', 'cid':'bafyexamplecid',
                      'record':{'$type':'app.bsky.feed.post', 'text':text,
                                'createdAt':datetime.now(timezone.utc).isoformat()}}}


def config(**override):
    return {'keyword':'research phrase', 'region':'us-east', 'duration_seconds':15,
            'max_posts':5, 'permission_confirmed':True, **override}


class FakeSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.closed = False
    def settimeout(self, seconds): self.timeout = seconds
    def recv(self):
        if self.messages: return self.messages.pop(0)
        return None
    def close(self): self.closed = True


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch('app.DB', os.path.join(self.tmp.name, 'test.sqlite3'))
        self.patcher.start()
        with database() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 7)

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_config_limits_and_permission(self):
        for override in [dict(keyword='x'), dict(region='localhost'), dict(duration_seconds=181),
                         dict(max_posts=201), dict(permission_confirmed=False),
                         dict(max_posts=True), dict(keyword='new\nline')]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                validate_config(config(**override))
        self.assertEqual(validate_config(config())['keyword'], 'research phrase')

    def test_bounded_or_phrases_preserve_existing_keyword_semantics(self):
        from live_stream import parse_keywords
        self.assertEqual(parse_keywords('news | community update'), ['news','community update'])
        self.assertEqual(validate_config(config(keyword='research phrase|community alert'))['keyword'],
                         'research phrase|community alert')
        self.assertIsNotNone(normalize_live_event(sample_event(text='community alert about the station'),
                                                   'research phrase|community alert'))
        self.assertIsNone(normalize_live_event(sample_event(text='completely unrelated content'),
                                               'research phrase|community alert'))
        for value in ('news||updates', 'short|a', 'one|two|three|four', 'x'*91, 'news|more\nnews'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_config(config(keyword=value))

    def test_normalize_create_delete_and_invalid(self):
        event=sample_event()
        post=normalize_live_event(event, 'RESEARCH PHRASE')
        self.assertEqual(post['action'],'create')
        self.assertEqual(post['post']['source'],'bluesky-jetstream')
        self.assertIn('bsky.app/profile/did:plc:', post['post']['url'])
        self.assertEqual(normalize_live_event(event,'unmatched'),None)
        event['commit']['operation']='delete'
        self.assertEqual(normalize_live_event(event, 'unmatched')['action'],'remove')
        event['did']='bad-identifier'
        self.assertIsNone(normalize_live_event(event,'research phrase'))

    def test_jetstream_facet_links_are_preserved_separately_and_grouped(self):
        for i in range(3):
            event=sample_event(i)
            event['commit']['record']['facets']=[{'features':[
                {'$type':'app.bsky.richtext.facet#link',
                 'uri':f'https://news.example.net/report?id=7&utm_source={i}'}]}]
            normalized=normalize_live_event(event,'research phrase')
            self.assertEqual(normalized['post']['text'],'Example research phrase')
            self.assertEqual(len(normalized['provenance']['external_links']),1)
            self.assertEqual(insert_record(database, normalized, 'observed-session', 'jetstream.us-east.bsky.network'),1)
        leads=[c for c in clusters() if c['signal_type']=='shared_link']
        self.assertEqual(len(leads),1)
        self.assertEqual(leads[0]['sample_text'],'news.example.net/report?id=7')
        case,_=create_investigation({'cluster_id':leads[0]['id']})
        bundle=lab_export(database,case['id'],find_cluster)
        self.assertEqual(len(bundle['source_posts'][0]['provenance']['facet_and_embed_urls_unverified']),1)
        self.assertEqual(len(recent_posts(database)),3)
        self.assertTrue(recent_posts(database)[0]['external_links'].startswith('['))

    def test_embed_external_link_and_legacy_database_upgrade(self):
        import sqlite3
        from live_stream import extract_record_links
        record={'embed':{'$type':'app.bsky.embed.recordWithMedia',
               'media':{'$type':'app.bsky.embed.external',
                        'external':{'uri':'https://publisher.example.org/story'}}}}
        self.assertEqual(extract_record_links(record), ['https://publisher.example.org/story'])
        self.assertEqual(extract_record_links({'embed':{'$type':'app.bsky.embed.external',
                 'external':{'uri':'http://127.0.0.1/private'}}}),[])
        legacy=os.path.join(self.tmp.name,'legacy.sqlite')
        c=sqlite3.connect(legacy)
        c.executescript('''CREATE TABLE live_post_provenance (
            post_id TEXT PRIMARY KEY, did TEXT NOT NULL, rkey TEXT NOT NULL,
            cid TEXT NOT NULL, event_time_us INTEGER NOT NULL,
            record_created_at TEXT, collection TEXT NOT NULL, provider TEXT NOT NULL,
            session_id TEXT NOT NULL, captured_at TEXT NOT NULL);
            INSERT INTO live_post_provenance VALUES
            ('legacy','did:plc:aaaaaaaaaaaaaaaaaaaaaaaa','post1','cid',1,NULL,
             'app.bsky.feed.post','provider','session','2026-10-20T18:00:00+00:00');
            PRAGMA user_version=4;''')
        init_schema(c)
        self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],7)
        self.assertEqual(c.execute("SELECT external_links FROM live_post_provenance WHERE post_id='legacy'").fetchone()[0],'[]')
        c.close()

    def test_bounded_session_idempotency_and_provenance(self):
        feed=[json.dumps(sample_event(i)) for i in range(3)]
        manager=CaptureManager(database, websocket_factory=lambda url: FakeSocket(feed))
        state=manager.start(config())
        self.assertTrue(state['session'])
        self.assertEqual(manager.thread.name,'oio-jetstream')
        manager.thread.join(4)
        report=manager.status()
        self.assertEqual(report['session']['inserted'],3)
        self.assertEqual(report['session']['status'],'finished')
        self.assertEqual(report['stored_posts'],3)
        self.assertEqual(report['session']['stop_reason'],'stream_closed')
        self.assertEqual(len(clusters()),1)  # detector accepts live posts without claiming bots
        self.assertEqual(len(recent_posts(database)),3)
        with database() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM live_capture_sessions').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM live_post_provenance').fetchone()[0],3)
        # Re-ingest same records into a new session after cooldown; stable IDs skip duplicates.
        manager.last_start -= 4
        manager.websocket_factory=lambda url: FakeSocket(feed)
        manager.start(config())
        manager.thread.join(4)
        self.assertEqual(manager.status()['session']['inserted'],0)
        self.assertEqual(live_count(database),3)
        with self.assertRaises(ValueError): manager.purge({'confirmation':'DELETE'})
        self.assertEqual(manager.purge({'confirmation':'DELETE LIVE POSTS'})['deleted'],3)
        self.assertEqual(len(clusters()),0)
        self.assertEqual(live_count(database),0)

    def test_record_update_or_delete_within_stream(self):
        create=sample_event()
        delete=sample_event(operation='delete')
        manager=CaptureManager(database, websocket_factory=lambda url: FakeSocket([json.dumps(create),json.dumps(delete)]))
        manager.start(config())
        manager.thread.join(4)
        self.assertEqual(manager.status()['session']['removed'],1)
        self.assertEqual(live_count(database),0)

    def test_retention_does_not_delete_synthetic_posts(self):
        item=normalize_live_event(sample_event(),'research phrase')
        insert_record(database,item,'session-test','jetstream.us-east.bsky.network')
        ingest([{'id':'demo','source':'synthetic','actor':'synthetic-a','text':'example',
                 'created_at':datetime.now(timezone.utc).isoformat(),'url':'https://example.org/demo'}])
        old=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
        with database() as c:
            c.execute('UPDATE live_post_provenance SET captured_at=?', (old,))
        self.assertEqual(prune_expired(database),1)
        with database() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM posts').fetchone()[0],1)

    def test_failure_reported_not_server_crash(self):
        def failure(url): raise ConnectionError('offline test')
        manager=CaptureManager(database, websocket_factory=failure)
        manager.start(config())
        manager.thread.join(4)
        self.assertEqual(manager.status()['session']['status'],'error')
        self.assertIn('offline test',manager.status()['session']['error'])

    def test_session_capped_by_max_posts(self):
        events = [json.dumps(sample_event(i, text='research phrase record')) for i in range(12)]
        manager = CaptureManager(database, websocket_factory=lambda url: FakeSocket(events))
        manager.start(config())
        manager.thread.join(4)
        self.assertEqual(manager.status()['session']['inserted'], 5)
        self.assertEqual(manager.status()['session']['stop_reason'], 'post_limit')
        self.assertEqual(live_count(database), 5)

    def test_source_provenance_in_investigation_export(self):
        for i in range(3):
            insert_record(database, normalize_live_event(sample_event(i), 'research phrase'),
                          'test-live-session', 'jetstream.us-east.bsky.network')
        group = clusters()[0]
        case, created = create_investigation({'cluster_id': group['id']})
        self.assertTrue(created)
        exported = lab_export(database, case['id'], find_cluster)
        self.assertEqual(exported['application_version'], '0.5.2')
        self.assertEqual(len(exported['source_posts']), 3)
        item = exported['source_posts'][0]
        self.assertEqual(item['provenance']['session_id'], 'test-live-session')
        self.assertEqual(item['provenance']['cid_unverified'], 'bafyexamplecid')
        self.assertEqual(len(item['sha256']), 64)

    def test_manual_stop_and_no_parallel_sessions(self):
        class WaitingSocket:
            def settimeout(self, seconds): pass
            def recv(self):
                time.sleep(.02)
                raise TimeoutError('idle')
            def close(self): pass
        manager=CaptureManager(database, websocket_factory=lambda url: WaitingSocket())
        manager.start(config())
        with self.assertRaises(RuntimeError):
            manager.start(config())
        with self.assertRaises(RuntimeError):
            manager.purge({'confirmation':'DELETE LIVE POSTS'})
        self.assertTrue(manager.stop()['session'])
        manager.thread.join(4)
        self.assertEqual(manager.status()['session']['stop_reason'],'user_stopped')

    def test_interrupted_session_is_not_auto_resumed(self):
        with database() as c:
            c.execute('INSERT INTO live_capture_sessions '
                      '(id,keyword,region,started_at,status,duration_seconds,max_posts) '
                      'VALUES (?,?,?,?,?,?,?)',
                      ('old1','test','us-west',datetime.now(timezone.utc).isoformat(),'running',60,100))
        manager=CaptureManager(database)
        manager.reconcile()
        self.assertEqual(manager.status()['session']['status'],'interrupted')
        self.assertFalse(manager.status()['active'])

    def test_api_status_posts_and_invalid_controls(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            port=server.server_address[1]
            def get(url):
                conn=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
                conn.request('GET',url)
                result=conn.getresponse(); data=json.loads(result.read()); conn.close()
                return result.status,data
            status, info=get('/api/live/status')
            self.assertEqual(status,200)
            self.assertEqual(info['retention_days'],7)
            status, items=get('/api/live/posts')
            self.assertEqual(status,200)
            self.assertEqual(items['posts'],[])
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
            body=json.dumps(config(permission_confirmed=False))
            conn.request('POST','/api/live/start',body,headers={'Content-Type':'application/json'})
            self.assertEqual(conn.getresponse().status,400)
            conn.close()
        finally:
            server.shutdown();server.server_close();thread.join(3)


if __name__=='__main__': unittest.main()
