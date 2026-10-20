"""v0.5.2 diagnostics: fake public events, no external WebSocket or production data."""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import database
from live_stream import (CaptureManager, inspect_filter_path, compact_language_counts,
                         validate_config, live_count)
from test_live_stream import FakeSocket, sample_event, config


def create_event(index, text, language=None):
    event = sample_event(index=index, text=text)
    if language:
        event['commit']['record']['langs'] = language
    return json.dumps(event)


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch('app.DB', os.path.join(self.tmp.name, 'diagnostics.sqlite3'))
        self.patcher.start()
        with database() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 7)

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def stream(self):
        invalid = sample_event(index=1, text='България')
        invalid['commit']['record']['text'] = None
        return [
            '{not json',
            json.dumps({'kind': 'identity', 'did': 'did:plc:dummy'}),
            create_event(0, 'Разговор за София и България', ['en']),
            create_event(1, 'Разговор за София и България', ['bg']),
            create_event(2, 'An unrelated public conversation about research'),
            json.dumps(invalid),
        ]

    def test_filter_counters_capture_and_persistence(self):
        manager = CaptureManager(database, websocket_factory=lambda _: FakeSocket(self.stream()))
        manager.start(config(keyword='България', languages=['bg'], profile_id='bg', mode='capture'))
        manager.thread.join(4)
        stats = manager.status()['session']
        self.assertEqual(stats['scanned'], 6)
        self.assertEqual(stats['malformed_events'], 1)
        self.assertEqual(stats['post_creations'], 4)
        self.assertEqual(stats['eligible_text_posts'], 3)
        self.assertEqual(stats['keyword_matches'], 2)
        self.assertEqual(stats['language_rejections'], 1)
        self.assertEqual(stats['matched'], 1)
        self.assertEqual(stats['inserted'], 1)
        self.assertEqual(stats['unknown_language_posts'], 1)
        self.assertEqual(stats['language_counts'], {'en': 1, 'bg': 1})
        self.assertEqual(stats['mode'], 'capture')
        self.assertGreaterEqual(stats['invalid_post_records'], 1)
        self.assertEqual(live_count(database), 1)
        # Rehydrate from completed persisted sessions with no active worker.
        restarted = CaptureManager(database).status()['session']
        for field in ('post_creations', 'keyword_matches', 'language_rejections',
                      'eligible_text_posts', 'unknown_language_posts'):
            self.assertEqual(restarted[field], stats[field])
        self.assertEqual(restarted['language_counts'], stats['language_counts'])

    def test_diagnostic_session_never_stores_post_data(self):
        feed = self.stream()
        manager = CaptureManager(database, websocket_factory=lambda _: FakeSocket(feed))
        manager.start(config(keyword='България', languages=['bg'], mode='diagnostic'))
        manager.thread.join(4)
        stats = manager.status()['session']
        self.assertEqual(stats['matched'], 1)
        self.assertEqual(stats['inserted'], 0)
        self.assertEqual(stats['mode'], 'diagnostic')
        self.assertEqual(live_count(database), 0)
        with database() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM posts').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM live_post_provenance').fetchone()[0], 0)
            row = c.execute('SELECT * FROM live_capture_sessions').fetchone()
            for column in ('keyword', 'region', 'mode'):
                self.assertIn(column, row.keys())
            # No account IDs, source URLs or post bodies in the session record.
            values = json.dumps(dict(row), ensure_ascii=False)
            self.assertNotIn('Разговор', values)
            self.assertNotIn('did:plc:', values)
            self.assertNotIn('bsky.app/', values)

    def test_diagnostic_mode_does_not_hit_saved_post_limit(self):
        feed = [create_event(i, 'България news', ['bg']) for i in range(18)]
        manager = CaptureManager(database, websocket_factory=lambda _: FakeSocket(feed))
        manager.start(config(keyword='България',mode='diagnostic',max_posts=5))
        manager.thread.join(4)
        stats = manager.status()['session']
        self.assertEqual(stats['scanned'], 18)
        self.assertEqual(stats['matched'], 18)
        self.assertEqual(stats['inserted'], 0)
        self.assertEqual(stats['stop_reason'], 'stream_closed')

    def test_zero_keyword_matches_still_shows_language_distribution(self):
        feed = [create_event(i, 'Unrelated ordinary conversation', ['bg'] if i % 2 else ['en'])
                for i in range(8)]
        manager = CaptureManager(database, websocket_factory=lambda _: FakeSocket(feed))
        manager.start(config(keyword='България', languages=[], mode='diagnostic'))
        manager.thread.join(4)
        stats = manager.status()['session']
        self.assertEqual(stats['post_creations'], 8)
        self.assertEqual(stats['eligible_text_posts'], 8)
        self.assertEqual(stats['keyword_matches'], 0)
        self.assertEqual(stats['language_rejections'], 0)
        self.assertEqual(stats['matched'], 0)
        self.assertEqual(stats['inserted'], 0)
        self.assertEqual(stats['language_counts'], {'bg': 4, 'en': 4})
        self.assertEqual(live_count(database), 0)

    def test_filter_statistics_handle_unlabelled_and_multi_tags(self):
        event = sample_event(text='Testing Bulgaria')
        event['commit']['record']['langs'] = ['en-GB', 'bg', 'bg']
        result = inspect_filter_path(event,['Bulgaria'], ['bg'])
        self.assertTrue(result['valid_text'])
        self.assertTrue(result['keyword'])
        self.assertTrue(result['language'])
        self.assertEqual(result['tags'], ['en-gb', 'bg'])
        result = inspect_filter_path(event,['Bulgaria'], ['fr'])
        self.assertTrue(result['keyword'])
        self.assertFalse(result['language'])
        self.assertIsNone(inspect_filter_path({'kind': 'identity'},['news'], []))

    def test_config_rejects_invalid_mode(self):
        self.assertEqual(validate_config(config())['mode'], 'capture')
        self.assertEqual(validate_config(config(mode='diagnostic'))['mode'], 'diagnostic')
        for mode in (None, True, 10, 'shadow', []):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                validate_config(config(mode=mode))

    def test_compact_histogram_is_bounded_deterministically(self):
        counts = {f'x{i:02}': i + 1 for i in range(40)}
        compact = compact_language_counts(counts)
        self.assertLessEqual(len(compact), 21)
        self.assertEqual(sum(compact.values()), sum(counts.values()))
        self.assertIn('(other tags)', compact)

    def test_migrate_existing_v6_capture_metadata_without_deleting_it(self):
        with database() as c:
            c.execute('''INSERT INTO live_capture_sessions
                (id,keyword,region,started_at,status,duration_seconds,max_posts,profile_id,language_filter)
                VALUES ('previous','България','us-east','2026-10-20T18:00:00+00:00','finished',60,100,'bg','["bg"]')''')
            before = c.execute('SELECT COUNT(*) FROM live_capture_sessions').fetchone()[0]
        from live_stream import init_schema
        with database() as c:
            init_schema(c)
            after = c.execute('SELECT COUNT(*) FROM live_capture_sessions').fetchone()[0]
            old = c.execute("SELECT * FROM live_capture_sessions WHERE id='previous'").fetchone()
        self.assertEqual((before, after), (1, 1))
        self.assertEqual(old['mode'], 'capture')
        self.assertEqual(old['diagnostics_available'], 0)
        self.assertEqual(old['keyword'], 'България')
        self.assertEqual(json.loads(old['language_counts']), {})


if __name__ == '__main__':
    unittest.main()
