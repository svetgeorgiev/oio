import test from 'node:test';
import assert from 'node:assert/strict';
import { snapshotCSV, timelineBuckets } from './lab-utils.js';

test('minute buckets separate synthetic posts from analyst timestamps', () => {
  const events = [
    { at: '2026-10-20T08:00:30Z', kind: 'detected_post' },
    { at: '2026-10-20T08:00:50Z', kind: 'detected_post' },
    { at: '2026-10-20T08:01:00+00:00', kind: 'analyst_reference' },
    { at: 'bad', kind: 'detected_post' },
  ];
  assert.deepEqual(timelineBuckets(events), [
    { key: '2026-10-20T08:00', posts: 2, references: 0, total: 2 },
    { key: '2026-10-20T08:01', posts: 0, references: 1, total: 1 },
  ]);
  assert.equal(timelineBuckets(events, 'hour').length, 1);
});

test('export CSV protects spreadsheet formulas, commas and quotes', () => {
  const csv = snapshotCSV({source_posts: [], evidence_items: [
    { id: 1, kind: 'context', title: '=SUM(1,2)', source_url: 'https://example.org',
      observed_at: '', notes: 'Hello, "world"', sha256: 'abc' },
  ]});
  assert.match(csv, /"'=SUM\(1,2\)"/);
  assert.match(csv, /"Hello, ""world"""/);
  assert.match(csv, /record_type/);
  assert.ok(csv.startsWith('\ufeff'));
});
