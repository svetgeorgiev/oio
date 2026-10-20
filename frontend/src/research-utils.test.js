import test from 'node:test';
import assert from 'node:assert/strict';
import {hourBuckets, researchSearchParams} from './research-utils.js';

test('hourly chart groups local captures in UTC without assuming bot activity', () => {
  const rows = [
    {created_at:'2026-10-20T19:59:00Z'},
    {created_at:'2026-10-20T21:20:00+01:00'},
    {created_at:'2026-10-20T20:15:00Z'},
    {created_at:'invalid'},
  ];
  assert.deepEqual(hourBuckets(rows), [
    {key:'2026-10-20T19:00', count:1},
    {key:'2026-10-20T20:00', count:2},
  ]);
  assert.equal(hourBuckets(rows,1).length,1);
});

test('search query encodes literal phrases and UTC dates', () => {
  const result = new URLSearchParams(researchSearchParams({
    query:'  shared article & news  ', scope:'live',limit:60,
    from:'2026-10-18',to:'2026-10-20',
  }));
  assert.equal(result.get('q'),'shared article & news');
  assert.equal(result.get('from'),'2026-10-18T00:00:00Z');
  assert.equal(result.get('to'),'2026-10-20T23:59:59Z');
  assert.throws(()=>researchSearchParams({from:'2026-10-21',to:'2026-10-20'}));
});

test('profile and language filters are forwarded without geographic inference',()=>{
  const result = new URLSearchParams(researchSearchParams({profile:'bg',lang:'bg',query:'България'}));
  assert.equal(result.get('profile'),'bg');
  assert.equal(result.get('lang'),'bg');
  assert.equal(result.get('q'),'България');
});
