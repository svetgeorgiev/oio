// OIO v0.5: pure, offline presentation helpers. Input is already locally captured.
export function hourBuckets(posts, maxBuckets = 24) {
  const counts = new Map();
  for (const post of posts || []) {
    const d = new Date(post.created_at);
    if (Number.isNaN(d.getTime())) continue;
    const key = d.toISOString().slice(0, 13) + ':00';
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts]
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-maxBuckets)
    .map(([key, count]) => ({key, count}));
}

export function researchSearchParams({query = '', scope = 'live', limit = 60, from = '', to = '', profile = 'all', lang = 'all'}) {
  const qs = new URLSearchParams({q: String(query).trim(), scope, limit: String(limit), profile, lang});
  const date = /^\d{4}-\d{2}-\d{2}$/;
  if (from) {
    if (!date.test(from)) throw new Error('From must be a valid UTC date.');
    qs.set('from', from + 'T00:00:00Z');
  }
  if (to) {
    if (!date.test(to)) throw new Error('To must be a valid UTC date.');
    qs.set('to', to + 'T23:59:59Z');
  }
  if (from && to && from > to) throw new Error('From date must be earlier than To date.');
  return qs.toString();
}
