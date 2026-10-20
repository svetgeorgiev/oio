"""Remove only the original OIO synthetic fixture and its linked test case.

Run with Python while OIO API is STOPPED. Dry-run by default. No network access.
A verified SQLite backup is created outside the project before changing any data.
"""

import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = PROJECT_ROOT / 'fixtures' / 'sample_posts.json'
DEFAULT_DATABASE = PROJECT_ROOT / 'data.sqlite3'
BACKUP_DIR = PROJECT_ROOT.parent / 'oio-backups'
CONFIRMATION = 'DELETE DEMO DATA'


def fingerprint(text):
    normalized = re.sub(r'\s+', ' ', re.sub(r'https?://\S+', '', text.lower())).strip()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]


def get_fixture(fixture_path):
    rows = json.loads(Path(fixture_path).read_text(encoding='utf-8'))
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError('Expected the original five-post v0.1 demonstration fixture')
    ids = [r['id'] for r in rows]
    if set(ids) != {f'demo-{n}' for n in range(1, 6)}:
        raise ValueError('The fixture has unexpected IDs; refusing to delete data')
    if any(r.get('source') != 'synthetic' for r in rows):
        raise ValueError('The fixture contains non-synthetic posts; refusing')
    return rows


def table_exists(connection, name):
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def inventory(connection, fixture):
    if not table_exists(connection, 'posts'):
        raise ValueError('Not an initialized OIO database (posts table missing)')
    fixture_by_id = {r['id']: r for r in fixture}
    found = [dict(r) for r in connection.execute(
        'SELECT id,source,actor,text,created_at,url,fingerprint FROM posts '
        'WHERE id IN (?,?,?,?,?) ORDER BY id', tuple(sorted(fixture_by_id)))]
    for row in found:
        original = fixture_by_id[row['id']]
        if any(row[k] != original[k] for k in ('source', 'actor', 'text', 'url')):
            raise ValueError(f"Post {row['id']} differs from the known fixture. Aborting safely.")
        if row['fingerprint'] != fingerprint(original['text']):
            raise ValueError(f"Post {row['id']} has a different text fingerprint. Aborting.")
        if table_exists(connection, 'live_post_provenance') and connection.execute(
            'SELECT 1 FROM live_post_provenance WHERE post_id=?', (row['id'],)).fetchone():
            raise ValueError('A fixture ID also has live provenance; refusing to delete')

    # v0.1 deterministic cluster ID: SHA256(text fingerprint + first post ID).
    signal_id = hashlib.sha256((fingerprint(fixture[0]['text']) + '|demo-1').encode('utf-8')).hexdigest()[:12]
    candidate = ('inv-' + signal_id)
    case = None
    if table_exists(connection, 'investigations'):
        match = connection.execute('SELECT * FROM investigations WHERE id=?', (candidate,)).fetchone()
        if match:
            case = dict(match)
            if case['cluster_id'] != signal_id:
                raise ValueError('Investigation ID exists but belongs to another cluster; refusing')
    # Keep any unexpected shared-content cluster and its case rather than wiping non-demo evidence.
    non_demo = connection.execute('SELECT COUNT(*) FROM posts WHERE fingerprint=? AND id NOT IN (?,?,?,?,?)',
        (fingerprint(fixture[0]['text']), *sorted(fixture_by_id))).fetchone()[0]
    if non_demo and case:
        raise ValueError('Other posts share the demo cluster fingerprint; manual review required before deleting case')

    child_counts = {}
    for table, parent in [('investigation_events','investigation_id'), ('evidence_items','investigation_id')]:
        child_counts[table] = (connection.execute(f'SELECT COUNT(*) FROM {table} WHERE {parent}=?', (candidate,)).fetchone()[0]
                               if case and table_exists(connection, table) else 0)
    legacy = (connection.execute('SELECT COUNT(*) FROM reviews WHERE cluster_id=?', (signal_id,)).fetchone()[0]
              if table_exists(connection, 'reviews') else 0)
    live_posts = (connection.execute('SELECT COUNT(*) FROM live_post_provenance').fetchone()[0]
                  if table_exists(connection, 'live_post_provenance') else 0)
    other_posts = connection.execute('SELECT COUNT(*) FROM posts WHERE id NOT IN (?,?,?,?,?)', tuple(sorted(fixture_by_id))).fetchone()[0]
    return {'fixture_ids': tuple(r['id'] for r in found), 'cluster_id': signal_id,
            'investigation_id': candidate if case else None, 'case': case,
            'child_counts': child_counts, 'old_reviews': legacy, 'live_posts': live_posts,
            'other_posts': other_posts}


def backup_sqlite(source, dest):
    # SQLite backup API captures committed WAL content, unlike copying only the .sqlite3 file.
    dest.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(dest)) as archive:
        source.backup(archive)
        result = archive.execute('PRAGMA integrity_check').fetchone()[0]
        if result != 'ok':
            raise RuntimeError('Database backup integrity check failed: ' + str(result))


def cleanup(db_path=DEFAULT_DATABASE, fixture_path=FIXTURE, backup_dir=BACKUP_DIR, apply=False):
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f'Database does not exist: {db_path}. No changes made.')
    fixture = get_fixture(fixture_path)
    with closing(sqlite3.connect(db_path, timeout=2)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout=2000')
        current = inventory(connection, fixture)
        if not apply:
            return current, None
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        backup = Path(backup_dir).resolve() / f'oio-before-demo-cleanup-{timestamp}.sqlite3'
        backup_sqlite(connection, backup)
        try:
            connection.execute('BEGIN IMMEDIATE')
            # Recheck inside the exclusive write transaction.
            current = inventory(connection, fixture)
            if current['investigation_id']:
                inv = current['investigation_id']
                for child in ('investigation_events', 'evidence_items'):
                    if table_exists(connection, child):
                        connection.execute(f'DELETE FROM {child} WHERE investigation_id=?', (inv,))
                connection.execute('DELETE FROM investigations WHERE id=? AND cluster_id=?', (inv, current['cluster_id']))
            if table_exists(connection, 'reviews'):
                connection.execute('DELETE FROM reviews WHERE cluster_id=?', (current['cluster_id'],))
            for post_id in current['fixture_ids']:
                connection.execute("DELETE FROM posts WHERE id=? AND source='synthetic'", (post_id,))
            if inventory(connection, fixture)['fixture_ids']:
                raise RuntimeError('Demo posts remain after removal: rolling back')
            live_after = (connection.execute('SELECT COUNT(*) FROM live_post_provenance').fetchone()[0]
                          if table_exists(connection, 'live_post_provenance') else 0)
            if live_after != current['live_posts']:
                raise RuntimeError('Live-post count changed during cleanup: rolling back')
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return current, backup


def main():
    parser = argparse.ArgumentParser(description='Dry-run / safely remove original OIO demo dataset, not live data')
    parser.add_argument('--apply', action='store_true', help='Back up DB then remove demo records and linked case')
    args = parser.parse_args()
    try:
        current, _ = cleanup()
        print('\nOIO demo data cleanup — ' + ('READY' if args.apply else 'DRY RUN'))
        print('Original fixture posts present:', len(current['fixture_ids']))
        print('Demo cluster:', current['cluster_id'])
        print('Linked test investigation:', current['investigation_id'] or 'none')
        print('Case events:', current['child_counts']['investigation_events'])
        print('Case manual evidence:', current['child_counts']['evidence_items'])
        print('Legacy reviews:', current['old_reviews'])
        print('Preserved live posts:', current['live_posts'])
        print('Other posts preserved:', current['other_posts'])
        if not args.apply:
            print('\nNothing changed. Stop OIO backend and run with --apply to proceed.')
            return
        if not current['fixture_ids'] and not current['investigation_id'] and not current['old_reviews']:
            print('Nothing to remove. The demo data is already absent.')
            return
        print('\nThis also removes the linked demo investigation, notes, and manual evidence.')
        print('A complete SQLite backup will be stored outside your project before deletion.')
        answer = input(f'Type {CONFIRMATION} to proceed: ').strip()
        if answer != CONFIRMATION:
            print('Cancelled. Nothing changed.')
            return
        result, backup = cleanup(apply=True)
        print(f'\nRemoved {len(result["fixture_ids"])} demo posts and linked test records.')
        print('Verified backup:', backup)
        print('Live observations and unrelated cases were not targeted.')
    except (ValueError, RuntimeError, FileNotFoundError, sqlite3.Error) as exc:
        print('STOPPED SAFELY:', exc)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
