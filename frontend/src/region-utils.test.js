import test from 'node:test';
import assert from 'node:assert/strict';
import {parseLanguageInput,formatRegionTime,profileTimezone} from './region-utils.js';

test('declared language filter validation trims and deduplicates',()=>{
  assert.deepEqual(parseLanguageInput(' BG, en , bg,fr '),['bg','en','fr']);
  assert.deepEqual(parseLanguageInput(''),[]);
  assert.deepEqual(parseLanguageInput('en-GB,fr'),['en-gb','fr']);
  assert.throws(()=>parseLanguageInput('english'),/six language tags/);
  assert.throws(()=>parseLanguageInput('bg, en, de, fr, es, it, pl'),/six language tags/);
  assert.throws(()=>parseLanguageInput('bg;en'),/six language tags/);
});

test('selected research profile zone formats independently of browser locale',()=>{
  const profiles = [{id:'bg',timezone:'Europe/Sofia'},{id:'uk',timezone:'Europe/London'}];
  assert.equal(profileTimezone(profiles,'bg'),'Europe/Sofia');
  assert.equal(profileTimezone(profiles,'unknown'),'UTC');
  assert.match(formatRegionTime('2026-01-20T09:00:00Z','Europe/Sofia'),/11:00:00/);
  assert.match(formatRegionTime('2026-07-20T09:00:00Z','Europe/Sofia'),/12:00:00/);
  assert.match(formatRegionTime('2026-07-20T09:00:00Z','Europe/London'),/10:00:00/);
});
