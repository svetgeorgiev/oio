// Pure presentation helpers; selected profiles and language tags are NOT geolocation.
export function parseLanguageInput(value) {
  if (!String(value ?? '').trim()) return [];
  const list = String(value).split(',').map(v=>v.trim().toLowerCase());
  if (list.length > 6 || list.some(v=>!/^[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,2}$/.test(v))) {
    throw new Error('Enter up to six language tags separated by commas (e.g. bg, en, de).');
  }
  return [...new Set(list)];
}

export function formatRegionTime(value, timeZone = 'UTC') {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Invalid timestamp';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone, day:'2-digit', month:'short', year:'numeric',
      hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false,
      timeZoneName:'short',
    }).format(date);
  } catch {
    return new Intl.DateTimeFormat('en-GB', {timeZone:'UTC', dateStyle:'medium', timeStyle:'medium'}).format(date)+' UTC';
  }
}

export function profileTimezone(profiles, id) {
  return profiles.find(p=>p.id===id)?.timezone || 'UTC';
}
