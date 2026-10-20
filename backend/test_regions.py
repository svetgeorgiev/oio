"""v0.5.1 research profile tests: synthetic event payloads; no external connections."""
import http.client
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import Handler, database, clusters, create_investigation, find_cluster
from laboratory import lab_export
from live_stream import CaptureManager, init_schema, insert_record, normalize_live_event, recent_posts, validate_config
from regions import (PROFILE_BY_ID, capture_languages, observed_languages, declared_language_matches,
                     public_profiles)
from research import search_posts
from test_live_stream import FakeSocket, sample_event, config


class RegionResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch('app.DB', os.path.join(self.tmp.name, 'regional.sqlite3'))
        self.patcher.start()
        with database() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 7)

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_profiles_are_neutral_topic_presets_and_keyword_valid(self):
        self.assertEqual(len(PROFILE_BY_ID), 6)
        self.assertEqual(len(public_profiles()), 6)
        from live_stream import parse_keywords
        for profile in public_profiles():
            if profile['keywords']:
                self.assertTrue(parse_keywords(profile['keywords']))
            self.assertIn('timezone', profile)
        self.assertEqual(PROFILE_BY_ID['bg']['languages'], ['bg'])
        self.assertEqual(PROFILE_BY_ID['eu']['languages'], [])

    def test_language_allowlist_rejects_invalid_and_unknown_does_not_match(self):
        self.assertEqual(capture_languages(['BG','en-GB','bg']), ['bg','en-gb'])
        self.assertEqual(observed_languages(['BG','en-GB','english',7]), ['bg','en-gb'])
        self.assertFalse(declared_language_matches([],['bg']))
        self.assertTrue(declared_language_matches(['en-gb'],['en']))
        self.assertFalse(declared_language_matches(['en-us'],['en-gb']))
        for value in (['english'], ['bg'] * 7, 'bg', [5], ['bg!'], ['xx' * 20]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                capture_languages(value)
        with self.assertRaises(ValueError):
            validate_config(config(profile_id='outside-europe'))
        with self.assertRaises(ValueError):
            validate_config(config(languages=['german']))

    def test_bulgarian_language_filter_excludes_missing_and_english_declared_tags(self):
        bg = sample_event(0, text='България София news research phrase')
        bg['commit']['record']['langs']=['bg']
        en = sample_event(1)
        en['commit']['record']['langs']=['en-GB']
        no_tag = sample_event(2)
        self.assertEqual(normalize_live_event(bg,'България', ['bg'])['provenance']['declared_langs'], ['bg'])
        self.assertIsNone(normalize_live_event(en,'research phrase', ['bg']))
        self.assertIsNone(normalize_live_event(no_tag,'research phrase', ['bg']))
        self.assertIsNotNone(normalize_live_event(no_tag,'research phrase', []))
        # Deletions still apply to previously captured records even when a filter is active.
        delete_event = sample_event(0, operation='delete')
        self.assertEqual(normalize_live_event(delete_event,'България',['bg'])['action'],'remove')

    def test_profile_metadata_persisted_and_queryable_with_case_export(self):
        for i in range(3):
            event=sample_event(i,text='България public research phrase')
            event['commit']['record']['langs']=['bg']
            parsed=normalize_live_event(event,'research phrase',['bg'])
            self.assertEqual(insert_record(database,parsed,'bg-session','jetstream.us-east.bsky.network','bg'),1)
        rows=recent_posts(database)
        self.assertEqual(len(rows),3)
        self.assertTrue(all(row['declared_langs']==['bg'] and row['profile_id']=='bg' for row in rows))
        self.assertEqual(search_posts(database,scope='live',profile='bg',language='bg')['total_matches'],3)
        self.assertEqual(search_posts(database,scope='live',profile='fr')['total_matches'],0)
        self.assertEqual(search_posts(database,scope='live',language='en')['total_matches'],0)
        case,_=create_investigation({'cluster_id':clusters()[0]['id']})
        export=lab_export(database,case['id'],find_cluster)
        data=export['source_posts'][0]['provenance']
        self.assertEqual(data['research_topic_profile_selected_by_analyst'],'bg')
        self.assertEqual(data['declared_post_languages_unverified'],['bg'])
        self.assertEqual(export['application_version'],'0.5.2')
        for kw in ({'profile':'xx'},{'language':'english!'}):
            with self.assertRaises(ValueError):search_posts(database,**kw)

    def test_live_session_rejects_nonmatching_languages_but_retains_data(self):
        feed=[]
        for i, tag in enumerate(('bg','en',None)):
            event=sample_event(i,text='България research phrase')
            if tag: event['commit']['record']['langs']=[tag]
            feed.append(json.dumps(event))
        manager=CaptureManager(database,websocket_factory=lambda _:FakeSocket(feed))
        manager.start(config(keyword='България',profile_id='bg',languages=['bg']))
        manager.thread.join(4)
        state=manager.status()
        self.assertEqual(state['session']['profile_id'],'bg')
        self.assertEqual(state['session']['languages'],['bg'])
        self.assertEqual(state['session']['inserted'],1)
        with database() as c:
            row=c.execute('SELECT profile_id, language_filter FROM live_capture_sessions').fetchone()
            self.assertEqual(row['profile_id'],'bg')
            self.assertEqual(json.loads(row['language_filter']),['bg'])
        # A new process can read the stored session settings.
        recovered=CaptureManager(database).status()['session']
        self.assertEqual(recovered['languages'],['bg'])
        self.assertEqual(recovered['profile_id'],'bg')

    def test_old_v5_schema_migrates_without_erasing_records(self):
        path=os.path.join(self.tmp.name,'old-v5.sqlite3')
        c=sqlite3.connect(path)
        c.executescript('''CREATE TABLE live_capture_sessions (
            id TEXT PRIMARY KEY, keyword TEXT NOT NULL, region TEXT NOT NULL,
            started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL, max_posts INTEGER NOT NULL,
            scanned INTEGER NOT NULL DEFAULT 0, matched INTEGER NOT NULL DEFAULT 0,
            inserted INTEGER NOT NULL DEFAULT 0, removed INTEGER NOT NULL DEFAULT 0,
            stop_reason TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '');
            CREATE TABLE live_post_provenance (
            post_id TEXT PRIMARY KEY, did TEXT NOT NULL, rkey TEXT NOT NULL,
            cid TEXT NOT NULL, event_time_us INTEGER NOT NULL,
            record_created_at TEXT, collection TEXT NOT NULL,
            provider TEXT NOT NULL, session_id TEXT NOT NULL,
            captured_at TEXT NOT NULL, external_links TEXT NOT NULL DEFAULT '[]');
            INSERT INTO live_capture_sessions (id, keyword, region, started_at, status, duration_seconds,max_posts)
            VALUES ('old','news','us-east','2026-10-20T09:00:00+00:00','finished',60,100);
            INSERT INTO live_post_provenance (post_id,did,rkey,cid,event_time_us,collection,provider,session_id,captured_at)
            VALUES ('legacy','did:plc:aaaaaaaaaaaaaaaaaaaaaaaa','r1','cid',123,'app.bsky.feed.post','jetstream.us-east.bsky.network','old','2026-10-20T09:00:00+00:00');
            PRAGMA user_version=5;''')
        init_schema(c)
        self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],7)
        self.assertEqual(c.execute("SELECT profile_id,language_filter FROM live_capture_sessions WHERE id='old'").fetchone(),('custom','[]'))
        self.assertEqual(c.execute("SELECT profile_id,declared_langs FROM live_post_provenance WHERE post_id='legacy'").fetchone(),('custom','[]'))
        init_schema(c)
        self.assertEqual(c.execute('SELECT count(*) FROM live_post_provenance').fetchone()[0],1)
        c.close()

    def test_public_profiles_and_search_api_are_read_only(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            def get(path):
                c=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=3)
                c.request('GET',path)
                r=c.getresponse();status=r.status; body=json.loads(r.read());c.close()
                return status,body
            code,body=get('/api/research/profiles')
            self.assertEqual(code,200)
            self.assertEqual(len(body['profiles']),6)
            self.assertIn('NOT verified geographic origins',body['notice'])
            code,body=get('/api/research/search?scope=live&profile=bg&lang=bg')
            self.assertEqual(code,200)
            self.assertEqual(body['total_matches'],0)
            code,body=get('/api/research/search?profile=no-such-place')
            self.assertEqual(code,400)
        finally:
            server.shutdown();server.server_close();thread.join(3)


if __name__=='__main__': unittest.main()
