/** Pure Evidence Lab helpers. No network access or new dependencies. */
export function timelineBuckets(events = [], unit = 'minute') {
  if (!['minute', 'hour', 'day'].includes(unit)) throw new Error('Unknown time unit');
  const cut = { minute: 16, hour: 13, day: 10 }[unit];
  const map = new Map();
  for (const event of events) {
    const date = new Date(event.at);
    if (Number.isNaN(date.getTime())) continue;
    const key = date.toISOString().slice(0, cut);
    const bucket = map.get(key) || { key, posts: 0, references: 0, total: 0 };
    if (event.kind === 'detected_post') bucket.posts++;
    else if (event.kind === 'analyst_reference') bucket.references++;
    else continue;
    bucket.total++;
    map.set(key, bucket);
  }
  return [...map.values()].sort((a, b) => a.key.localeCompare(b.key));
}

function safeCsvCell(value) {
  const string = String(value ?? '');
  // Prevent formula interpretation by Excel/LibreOffice on exported untrusted text.
  const text = /^[\s\uFEFF]*[=+\-@]/.test(string) || /^[\t\r\n]/.test(string) ? `\u0027${string}` : string;
  return `"${text.replaceAll('"', '""')}"`;
}

export function snapshotCSV(snapshot) {
  const header = ['record_type', 'id', 'kind', 'title_or_actor', 'url', 'observed_at', 'notes', 'sha256'];
  const rows = [header];
  for (const post of snapshot.source_posts || []) {
    rows.push(['detected_post', post.id, post.source, post.actor, post.url, post.created_at, post.text, post.sha256]);
  }
  for (const item of snapshot.evidence_items || []) {
    rows.push(['analyst_reference', item.id, item.kind, item.title, item.source_url,
      item.observed_at || '', item.notes, item.sha256]);
  }
  return '\ufeff' + rows.map(row => row.map(safeCsvCell).join(',')).join('\r\n') + '\r\n';
}
