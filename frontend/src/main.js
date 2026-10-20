import { createApp, computed, onMounted, onUnmounted, ref } from 'vue';
import './style.css';
import { timelineBuckets, snapshotCSV } from './lab-utils.js';
import {hourBuckets,researchSearchParams} from './research-utils.js';
import {parseLanguageInput,formatRegionTime,profileTimezone} from './region-utils.js';

const STATUS_LABELS = {
  unreviewed: 'Unreviewed',
  investigating: 'Investigating',
  needs_context: 'Needs context',
  dismissed: 'Dismissed',
  closed: 'Closed',
};

function prettyDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    });
  } catch {
    throw new Error('Cannot reach the local API. Start backend/app.py on port 8765.');
  }
  const raw = await response.text();
  let result;
  try { result = JSON.parse(raw); }
  catch { throw new Error('The server returned HTML or invalid JSON. Check the Vite API proxy.'); }
  if (!response.ok) throw new Error(result.error || `API request failed (${response.status})`);
  return result;
}

createApp({
  setup() {
    const page = ref('overview');
    const stats = ref({ posts: 0, candidate_clusters: 0, investigations: 0, open_investigations: 0, published_cases: 0 });
    const clusters = ref([]);
    const cases = ref([]);
    const selectedClusterId = ref(null);
    const selectedCase = ref(null);
    const activeActor = ref(null);
    const draft = ref({ title: '', status: 'investigating', notes: '', alternative_explanation: '' });
    const search = ref('');
    const statusFilter = ref('all');
    const error = ref('');
    const notice = ref('');
    const loading = ref(false);
    const saving = ref(false);
    const busy = ref(false);
    const lab = ref(null);
    const labCaseId = ref('');
    const labBusy = ref(false);
    const labSaving = ref(false);
    const permissionConfirmed = ref(false);
    const evidenceForm = ref({kind:'observation', title:'', source_url:'', observed_at:'', notes:''});
    const importFormat = ref('csv');
    const importContent = ref('');
    const importFilename = ref('');
    const timelineUnit = ref('minute');
    const evidenceFilter = ref('all');
    const researchQuery = ref('');
    const researchScope = ref('live');
    const researchFrom = ref('');
    const researchTo = ref('');
    const researchLimit = ref(60);
    const researchBusy = ref(false);
    const researchData = ref({posts:[],total_matches:0,limit:60,truncated:false});
    const researchType = ref('all');
    const researchProfile = ref('all');
    const researchLanguage = ref('all');
    const researchExpanded = ref(null);
    const liveInfo = ref({session: null, active: false, stored_posts: 0, retention_days: 7});
    const livePosts = ref([]);
    const liveConfig = ref({keyword: '', region: 'us-east', duration_seconds: 60, max_posts: 100, profile_id:'custom', mode:'capture'});
    const regionProfiles = ref([]);
    const profilePostCounts = ref({});
    const liveLanguageInput = ref('');
    const livePermission = ref(false);
    const liveBusy = ref(false);
    let livePolling = null;

    const selectedCluster = computed(() => clusters.value.find(c => c.id === selectedClusterId.value) || null);
    const caseCluster = computed(() => clusters.value.find(c => c.id === selectedCase.value?.cluster_id) || null);
    const filteredClusters = computed(() => clusters.value.filter(c => {
      const term = search.value.trim().toLowerCase();
      const matches = !term || [c.id, c.sample_text, c.pattern, ...c.evidence.map(p => p.actor)].join(' ').toLowerCase().includes(term);
      const state = c.review?.status || 'unreviewed';
      return matches && (statusFilter.value === 'all' || state === statusFilter.value);
    }));
    const filteredCases = computed(() => cases.value.filter(item => {
      const term = search.value.trim().toLowerCase();
      const matches = !term || [item.title, item.id, item.cluster_id, item.notes].join(' ').toLowerCase().includes(term);
      return matches && (statusFilter.value === 'all' || item.status === statusFilter.value);
    }));
    const timeline = computed(() => timelineBuckets(lab.value?.timeline || [], timelineUnit.value));
    const displayedTimeline = computed(() => timeline.value.slice(-32));
    const maxTimelineCount = computed(() => Math.max(1, ...displayedTimeline.value.map(p => p.total)));
    const filteredEvidence = computed(() => (lab.value?.evidence_items || []).filter(item =>
      evidenceFilter.value === 'all' || item.kind === evidenceFilter.value));
    const reviewCount = computed(() => clusters.value.filter(c => !c.investigation_id).length);
    const liveSession = computed(() => liveInfo.value?.session || null);
    const sessionZone = computed(() => profileTimezone(regionProfiles.value, liveSession.value?.profile_id));
    const liveZone = computed(() => profileTimezone(regionProfiles.value, liveConfig.value.profile_id));
    const selectedProfile = computed(() => regionProfiles.value.find(x=>x.id===liveConfig.value.profile_id));
    const liveElapsed = computed(() => liveSession.value?.started_at ? Math.max(0, Math.floor(
      (Date.now() - new Date(liveSession.value.started_at).getTime()) / 1000)) : 0);
    const researchSignals = computed(() => clusters.value.filter(item =>
      researchType.value === 'all' || item.signal_type === researchType.value));
    const researchSignalCounts = computed(() => ({
      exact_text: clusters.value.filter(item=>item.signal_type === 'exact_text').length,
      near_text: clusters.value.filter(item=>item.signal_type === 'near_text').length,
      shared_link: clusters.value.filter(item=>item.signal_type === 'shared_link').length,
    }));
    const researchHours = computed(() => hourBuckets(researchData.value.posts));
    const researchMaxHourly = computed(() => Math.max(1,...researchHours.value.map(x=>x.count)));
    const graphNodes = computed(() => {
      if (!selectedCluster.value) return [];
      const identities = [...new Map(selectedCluster.value.evidence.map(p => [p.source + ':' + p.actor, p])).values()].slice(0,36);
      return identities.map((p, i) => {
        const angle = (-Math.PI / 2) + (i * 2 * Math.PI / identities.length);
        return { ...p, x: 280 + Math.cos(angle) * 165, y: 190 + Math.sin(angle) * 119,
          label: p.actor.length > 15 ? p.actor.slice(0, 14) + '…' : p.actor };
      });
    });
    const chosenActorEvidence = computed(() => selectedCluster.value?.evidence.filter(p => !activeActor.value || p.actor === activeActor.value) || []);

    async function refresh({ silent = false } = {}) {
      if (!silent) loading.value = true;
      try {
        error.value = '';
        const [statResult, clusterResult, casesResult] = await Promise.all([
          api('/stats'), api('/clusters'), api('/investigations'),
        ]);
        stats.value = statResult;
        clusters.value = clusterResult.clusters;
        cases.value = casesResult.investigations;
        if (!selectedClusterId.value || !clusters.value.some(c => c.id === selectedClusterId.value)) {
          selectedClusterId.value = clusters.value[0]?.id || null;
        }
      } catch (e) {
        error.value = e.message;
      } finally { loading.value = false; }
    }

    async function loadProfiles() {
      try {
        const result = await api('/research/profiles');
        regionProfiles.value = result.profiles || [];
        profilePostCounts.value = result.saved_by_selected_profile || {};
      } catch (e) { if (page.value === 'live') error.value = e.message; }
    }
    function selectResearchProfile() {
      const found = regionProfiles.value.find(p=>p.id===liveConfig.value.profile_id);
      if (!found) return;
      liveConfig.value.keyword = found.keywords || '';
      liveLanguageInput.value = (found.languages || []).join(', ');
    }
    async function refreshLive({ silent = false } = {}) {
      if (!silent) liveBusy.value = true;
      try {
        const [status, result] = await Promise.all([api('/live/status'), api('/live/posts')]);
        const wasActive = liveInfo.value?.active;
        liveInfo.value = status;
        livePosts.value = result.posts || [];
        if (!silent) await loadProfiles();
        if (wasActive && !status.active) { await refresh({ silent: true }); await loadProfiles(); }
      } catch (e) { if (page.value === 'live') error.value = e.message; }
      finally { if (!silent) liveBusy.value = false; }
    }

    async function startLive() {
      liveBusy.value = true;
      try {
        error.value = '';
        const result = await api('/live/start', {method: 'POST', body: JSON.stringify({
          ...liveConfig.value, languages: parseLanguageInput(liveLanguageInput.value),
          permission_confirmed: livePermission.value,
        })});
        liveInfo.value = result;
        notice.value = liveConfig.value.mode === 'diagnostic' ? 'Diagnostics-only observation requested. No posts or identifiers will be saved.' : 'Live observation requested. It stops automatically at the configured limit.';
        await refreshLive({ silent: true });
      } catch (e) { error.value = e.message; }
      finally { liveBusy.value = false; }
    }

    async function stopLive() {
      liveBusy.value = true;
      try {
        error.value = '';
        liveInfo.value = await api('/live/stop', {method: 'POST'});
        notice.value = 'Stop requested; the collector will finish and close the connection.';
      } catch (e) { error.value = e.message; }
      finally { liveBusy.value = false; }
    }

    async function clearLivePosts() {
      const confirmation = window.prompt('Delete every locally captured Bluesky post? Type DELETE LIVE POSTS to confirm. Synthetic data, reviewer notes and manual references remain.');
      if (confirmation === null) return;
      liveBusy.value = true;
      try {
        error.value = '';
        const result = await api('/live/purge', {
          method: 'POST', body: JSON.stringify({ confirmation }),
        });
        notice.value = `Removed ${result.deleted} stored live posts. Earlier cases may lose linked detector evidence.`;
        await Promise.all([refreshLive({silent:true}), refresh({silent:true})]);
      } catch (e) { error.value = e.message; }
      finally { liveBusy.value = false; }
    }

    async function refreshResearch() {
      researchBusy.value = true;
      try {
        error.value = '';
        const qs = researchSearchParams({query:researchQuery.value,scope:researchScope.value,
          limit:researchLimit.value,from:researchFrom.value,to:researchTo.value,
          profile:researchProfile.value,lang:researchLanguage.value});
        researchData.value = await api('/research/search?' + qs);
        await refresh({silent:true});
      } catch(e) { error.value = e.message; }
      finally { researchBusy.value = false; }
    }
    function openResearch() { navigate('research'); refreshResearch(); }
    function toggleResearchEvidence(id) { researchExpanded.value = researchExpanded.value === id ? null : id; }
    function signalLabel(kind) {
      return {exact_text:'Exact matching text',near_text:'Similar wording',shared_link:'Shared external link'}[kind] || kind;
    }
    function graphLabel(kind) {
      return {exact_text:'MATCHING TEXT',near_text:'SIMILAR TEXT',shared_link:'SHARED LINK'}[kind] || 'SHARED SIGNAL';
    }
    function goResearchFromLive() { openResearch(); }
    function openLive() { navigate('live'); loadProfiles(); refreshLive(); }

    async function loadDemo() {
      busy.value = true;
      try {
        error.value = '';
        const data = await api('/load-fixture', { method: 'POST' });
        await refresh({ silent: true });
        notice.value = data.inserted ? `Loaded ${data.inserted} synthetic posts.` : 'Demo data already loaded — no duplicates.';
      } catch (e) { error.value = e.message; }
      finally { busy.value = false; }
    }

    function navigate(next) {
      page.value = next;
      search.value = '';
      statusFilter.value = 'all';
      error.value = '';
    }

    function inspectCluster(cluster) {
      selectedClusterId.value = cluster.id;
      activeActor.value = null;
      navigate('network');
    }

    async function openCase(cluster) {
      busy.value = true;
      try {
        error.value = '';
        let identifier = cluster.investigation_id;
        if (!identifier) {
          const result = await api('/investigations', {
            method: 'POST', body: JSON.stringify({ cluster_id: cluster.id }),
          });
          identifier = result.investigation.id;
          notice.value = result.created ? 'Investigation created. Review the supporting evidence.' : 'Existing investigation opened.';
        }
        await refresh({ silent: true });
        await selectCase({ id: identifier });
      } catch (e) { error.value = e.message; }
      finally { busy.value = false; }
    }

    async function selectCase(item) {
      busy.value = true;
      try {
        error.value = '';
        const data = await api(`/investigations/${encodeURIComponent(item.id)}`);
        selectedCase.value = data.investigation;
        draft.value = {
          title: data.investigation.title,
          status: data.investigation.status,
          notes: data.investigation.notes,
          alternative_explanation: data.investigation.alternative_explanation,
        };
        navigate('investigations');
      } catch (e) { error.value = e.message; }
      finally { busy.value = false; }
    }

    async function saveReview() {
      if (!selectedCase.value) return;
      saving.value = true;
      try {
        error.value = '';
        const result = await api(`/investigations/${encodeURIComponent(selectedCase.value.id)}/review`, {
          method: 'POST', body: JSON.stringify(draft.value),
        });
        selectedCase.value = result.investigation;
        await refresh({ silent: true });
        notice.value = 'Investigation saved locally. Audit entry recorded when fields changed.';
      } catch (e) { error.value = e.message; }
      finally { saving.value = false; }
    }

    async function openLab(identifier = null) {
      const id = identifier || labCaseId.value || selectedCase.value?.id || cases.value[0]?.id;
      navigate('laboratory');
      if (!id) { lab.value = null; return; }
      labCaseId.value = id;
      await refreshLab();
    }

    async function refreshLab() {
      if (!labCaseId.value) { lab.value = null; return; }
      labBusy.value = true;
      try {
        error.value = '';
        const data = await api(`/investigations/${encodeURIComponent(labCaseId.value)}/lab`);
        lab.value = data.lab;
      } catch (e) { error.value = e.message; lab.value = null; }
      finally { labBusy.value = false; }
    }

    async function saveEvidence() {
      if (!labCaseId.value) return;
      labSaving.value = true;
      try {
        error.value = '';
        const entry = {...evidenceForm.value};
        if (entry.observed_at) {
          const date = new Date(entry.observed_at);
          if (Number.isNaN(date.getTime())) throw new Error('Choose a valid observation date.');
          entry.observed_at = date.toISOString();
        } else entry.observed_at = null;
        const data = await api(`/investigations/${encodeURIComponent(labCaseId.value)}/lab/evidence`, {
          method: 'POST', body: JSON.stringify({ permission_confirmed: permissionConfirmed.value, evidence: entry }),
        });
        await refreshLab();
        if (data.inserted) evidenceForm.value = {kind:'observation', title:'', source_url:'', observed_at:'', notes:''};
        notice.value = data.inserted ? 'Evidence reference saved and hashed.' : 'Identical evidence already attached.';
      } catch (e) { error.value = e.message; }
      finally { labSaving.value = false; }
    }

    async function onImportFile(event) {
      const file = event.target.files?.[0];
      if (!file) return;
      importFilename.value = file.name;
      importFormat.value = file.name.toLowerCase().endsWith('.json') ? 'json' : 'csv';
      if (file.size > 128 * 1024) { error.value = 'Choose an evidence file under 128 KiB.'; importContent.value = ''; return; }
      importContent.value = await file.text();
      event.target.value = '';
    }

    async function importReferences() {
      if (!labCaseId.value) return;
      labSaving.value = true;
      try {
        error.value = '';
        const data = await api(`/investigations/${encodeURIComponent(labCaseId.value)}/lab/import`, {
          method: 'POST', body: JSON.stringify({format: importFormat.value, content: importContent.value,
            permission_confirmed: permissionConfirmed.value}),
        });
        await refreshLab();
        notice.value = data.inserted ? `Imported ${data.inserted} references; existing duplicates skipped.` : 'No new evidence — identical entries already exist.';
      } catch (e) { error.value = e.message; }
      finally { labSaving.value = false; }
    }

    function saveFile(name, content, mime) {
      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = name;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    async function exportLab(format) {
      if (!labCaseId.value) return;
      labBusy.value = true;
      try {
        error.value = '';
        const snapshot = await api(`/investigations/${encodeURIComponent(labCaseId.value)}/lab/export`);
        const base = `oio-${labCaseId.value}-evidence`;
        if (format === 'json') saveFile(`${base}.json`, JSON.stringify(snapshot, null, 2), 'application/json');
        else saveFile(`${base}.csv`, snapshotCSV(snapshot), 'text/csv;charset=utf-8');
        notice.value = 'Research export downloaded locally. It is not a verified public report.';
      } catch (e) { error.value = e.message; }
      finally { labBusy.value = false; }
    }

    async function removeEvidence(item) {
      const reason = window.prompt(`Why remove reference #${item.id}? (minimum 10 characters)`);
      if (reason === null) return;
      labSaving.value = true;
      try {
        error.value = '';
        await api(`/investigations/${encodeURIComponent(labCaseId.value)}/lab/evidence/${item.id}/delete`, {
          method: 'POST', body: JSON.stringify({ reason }),
        });
        await refreshLab();
        notice.value = `Evidence #${item.id} removed. Deletion recorded in audit history.`;
      } catch (e) { error.value = e.message; }
      finally { labSaving.value = false; }
    }

    function caseBack() { selectedCase.value = null; }
    function statusLabel(status) { return STATUS_LABELS[status] || 'Unreviewed'; }
    function statusClass(status) { return 'status-' + (status || 'unreviewed'); }
    onMounted(() => {
      refresh();
      loadProfiles();
      refreshLive({silent:true});
      livePolling = setInterval(() => {
        if (page.value === 'live' || liveInfo.value?.active) refreshLive({silent:true});
      }, 2500);
    });
    onUnmounted(() => { if (livePolling) clearInterval(livePolling); });

    return {
      page, stats, clusters, cases, selectedCase, selectedCluster, selectedClusterId, caseCluster,
      filteredClusters, filteredCases, graphNodes, activeActor, chosenActorEvidence,
      search, statusFilter, draft, error, notice, loading, saving, busy, reviewCount,
      lab, labCaseId, labBusy, labSaving, permissionConfirmed, evidenceForm, importFormat,
      importContent, importFilename, timelineUnit, evidenceFilter, filteredEvidence,
      timeline, displayedTimeline, maxTimelineCount,
      refresh, loadDemo, navigate, inspectCluster, openCase, selectCase, saveReview, caseBack,
      statusLabel, statusClass, prettyDate, openLab, refreshLab, saveEvidence, onImportFile,
      importReferences, exportLab, removeEvidence,
      liveInfo, livePosts, liveSession, liveElapsed, liveConfig, livePermission, liveBusy,
      regionProfiles,profilePostCounts,liveLanguageInput,liveZone,sessionZone,selectedProfile,
      loadProfiles,selectResearchProfile,parseLanguageInput,formatRegionTime,profileTimezone,
      refreshLive, startLive, stopLive, clearLivePosts, openLive,
      researchQuery,researchScope,researchFrom,researchTo,researchLimit,researchBusy,researchProfile,researchLanguage,
      researchData,researchType,researchExpanded,researchSignals,researchSignalCounts,
      researchHours,researchMaxHourly,refreshResearch,openResearch,toggleResearchEvidence,
      signalLabel,graphLabel,goResearchFromLive,
    };
  },
  template: `
    <div class="app-shell">
      <aside class="sidebar">
        <div class="brand"><div class="brand-logo">◎</div><div><strong>OIO</strong><span>OPEN INFLUENCE<br>OBSERVATORY</span></div></div>
        <div class="sidebar-label">WORKSPACE</div>
        <nav class="side-nav" aria-label="Main navigation">
          <button :class="['nav-item',{active:page==='overview'}]" @click="navigate('overview')"><span class="nav-icon">◫</span> Overview</button>
          <button :class="['nav-item',{active:page==='detections'}]" @click="navigate('detections')"><span class="nav-icon">⌁</span> Detection queue <em>{{stats.candidate_clusters}}</em></button>
          <button :class="['nav-item',{active:page==='network'}]" @click="navigate('network')"><span class="nav-icon">◎</span> Network explorer</button>
          <button :class="['nav-item',{active:page==='investigations'}]" @click="navigate('investigations');caseBack()"><span class="nav-icon">▤</span> Investigations <em>{{stats.investigations}}</em></button>
          <button :class="['nav-item',{active:page==='laboratory'}]" @click="openLab()"><span class="nav-icon">⚗</span> Evidence Laboratory</button>
          <button :class="['nav-item',{active:page==='live'}]" @click="openLive()"><span class="nav-icon">◉</span> Live Data Research <em v-if="liveInfo.active" class="live-active-dot">LIVE</em></button>
          <button :class="['nav-item',{active:page==='research'}]" @click="openResearch()"><span class="nav-icon">⌕</span> Signal Research <em v-if="clusters.length">{{clusters.length}}</em></button>
        </nav>
        <div class="sidebar-label sidebar-section">REFERENCE</div>
        <nav class="side-nav"><button :class="['nav-item',{active:page==='methodology'}]" @click="navigate('methodology')"><span class="nav-icon">ⓘ</span> Methodology</button></nav>
        <div class="sidebar-footer"><span class="pulse"></span> Local research mode <small>Local public research · v0.5.2</small></div>
      </aside>

      <div class="workspace">
        <header class="topbar"><div class="crumb">WORKSPACE <span>/</span> <strong>{{ page === 'overview' ? 'Overview' : page === 'detections' ? 'Detection queue' : page === 'network' ? 'Network explorer' : page === 'investigations' ? 'Investigations' : page === 'laboratory' ? 'Evidence Laboratory' : page === 'live' ? 'Live Data Research' : page === 'research' ? 'Signal Research' : 'Methodology' }}</strong></div><div class="top-actions"><span class="privacy-label">● LOCAL · NOT PUBLIC</span><button class="icon-button" title="Refresh data" :disabled="loading" @click="refresh()">↻</button></div></header>
        <main class="main-content">
          <div v-if="error" role="alert" class="alert error"><strong>Something needs attention</strong><span>{{error}}</span><button @click="error=''">×</button></div>
          <div v-if="notice" role="status" class="alert notice"><span>{{notice}}</span><button @click="notice=''">×</button></div>

          <template v-if="page==='overview'">
            <div class="page-heading"><div><div class="eyebrow">THE RESEARCH DESK</div><h1>Observatory overview<span class="heading-dot">.</span></h1><p>Understand the patterns. Investigate the evidence. Avoid assumptions.</p></div><div class="heading-actions"><button class="btn outline" @click="refresh()">↻ Refresh</button><button class="btn primary" @click="openResearch()">⌕ Search captured posts</button></div></div>
            <div class="hero"><div><span class="hero-label"><i></i> EVIDENCE FIRST / RESEARCH PROTOTYPE</span><h2>Signals are not verdicts.</h2><p>OIO highlights coordination candidates and supports documented human review. Synthetic examples and optional short Bluesky public-data captures. Observed patterns do not establish that accounts are automated or controlled together.</p><button class="btn hero-btn" @click="navigate('detections')">Explore candidate signals <span>↗</span></button></div><div class="hero-orbit" aria-hidden="true"><div class="orbit-ring one"></div><div class="orbit-ring two"></div><div class="orbit-center">◎</div><span class="orbit-node node-a"></span><span class="orbit-node node-b"></span><span class="orbit-node node-c"></span></div></div>
            <div class="stats-grid">
              <article class="stat-card"><div class="stat-top"><span>INGESTED POSTS</span><b>↗</b></div><strong>{{stats.posts}}</strong><div class="stat-bottom">Local observations · {{stats.live_posts || 0}} live</div></article>
              <article class="stat-card"><div class="stat-top"><span>CANDIDATE CLUSTERS</span><b>⌁</b></div><strong>{{stats.candidate_clusters}}</strong><div class="stat-bottom">Patterns requiring human review</div></article>
              <article class="stat-card"><div class="stat-top"><span>OPEN INVESTIGATIONS</span><b>▤</b></div><strong>{{stats.open_investigations}}</strong><div class="stat-bottom">Research notes &amp; context</div></article>
              <article class="stat-card"><div class="stat-top"><span>PUBLISHED REPORTS</span><b>◇</b></div><strong>{{stats.published_cases}}</strong><div class="stat-bottom">Publishing intentionally disabled</div></article>
            </div>
            <div class="overview-grid"><section class="panel"><div class="panel-heading"><div><div class="eyebrow">REVIEW PIPELINE</div><h3>Latest candidate patterns</h3></div><button class="text-link" @click="navigate('detections')">View all →</button></div><div v-if="!clusters.length" class="empty-state"><span>◎</span><strong>No candidate patterns yet</strong><p>Run a permitted public observation, then review the stored data and potential patterns.</p></div><div v-for="c in clusters.slice(0,4)" :key="c.id" class="overview-row"><span class="row-icon">⌁</span><div class="row-main"><b>Cluster {{c.id}}</b><small>{{c.distinct_actors}} distinct actors · {{c.post_count}} posts</small></div><span :class="['status',statusClass(c.review.status)]">{{statusLabel(c.review.status)}}</span><button class="tiny-button" @click="inspectCluster(c)">↗</button></div></section><section class="panel side-info"><div class="eyebrow">RESEARCH PRINCIPLES</div><h3>Built for careful investigation</h3><div class="principle"><span>01</span><div><b>Discover patterns</b><p>Timing and identical text signal possible coordination, not intent.</p></div></div><div class="principle"><span>02</span><div><b>Check counterevidence</b><p>Record legitimate explanations before deciding what a pattern means.</p></div></div><div class="principle"><span>03</span><div><b>Document a review</b><p>Decisions and edits are saved in a local audit trail.</p></div></div></section></div>
          </template>

          <template v-else-if="page==='detections'">
            <div class="page-heading"><div><div class="eyebrow">SIGNAL DETECTION</div><h1>Detection queue<span class="heading-dot">.</span></h1><p>Investigative leads awaiting context and human review.</p></div><button class="btn outline" @click="refresh()">↻ Refresh</button></div>
            <div class="notice-strip">ⓘ &nbsp; Exact text (3 minutes), near-duplicate wording (10 minutes), and full shared URLs (10 minutes) are leads, not bot verdicts. News and campaigns can match organically.</div>
            <div class="toolbar"><input v-model="search" type="search" placeholder="Search cluster, text or actor…" aria-label="Search candidate clusters"><select v-model="statusFilter" aria-label="Filter by review status"><option value="all">All statuses</option><option value="unreviewed">Unreviewed</option><option value="investigating">Investigating</option><option value="needs_context">Needs context</option><option value="dismissed">Dismissed</option><option value="closed">Closed</option></select><span class="results-count">{{filteredClusters.length}} results</span></div>
            <div v-if="!filteredClusters.length" class="empty-state panel"><span>⌁</span><strong>No matching clusters</strong><p>The local sample has not produced a candidate. Capture more permitted public observations or explore saved posts in Signal Research.</p></div>
            <article v-for="c in filteredClusters" :key="c.id" class="cluster-card"><div class="cluster-top"><div class="cluster-number">◎</div><div class="cluster-title"><div><strong>Cluster {{c.id}}</strong><span :class="['status',statusClass(c.review.status)]">{{statusLabel(c.review.status)}}</span></div><small>{{signalLabel(c.signal_type)}} · {{c.pattern}}</small></div><button class="icon-button" title="View network" @click="inspectCluster(c)">↗</button></div><blockquote>{{c.sample_text}}</blockquote><div class="cluster-bottom"><div class="cluster-meta"><span><b>{{c.distinct_actors}}</b> distinct actors</span><span><b>{{c.post_count}}</b> posts</span><span>{{prettyDate(c.first_seen)}}</span></div><div class="cluster-actions"><button class="btn outline" @click="inspectCluster(c)">View evidence &amp; graph</button><button class="btn primary" :disabled="busy" @click="openCase(c)">{{c.investigation_id?'Open investigation':'＋ Start investigation'}}</button></div></div></article>
          </template>

          <template v-else-if="page==='network'">
            <div class="page-heading"><div><div class="eyebrow">RELATIONSHIP VISUALIZATION</div><h1>Network explorer<span class="heading-dot">.</span></h1><p>Explore shared content and timing without implying shared ownership.</p></div><select class="cluster-selector" v-model="selectedClusterId" @change="activeActor=null" aria-label="Select a cluster"><option v-for="c in clusters" :key="c.id" :value="c.id">Cluster {{c.id}}</option></select></div>
            <template v-if="selectedCluster">
              <div class="network-layout"><section class="panel graph-panel"><div class="panel-heading"><div><div class="eyebrow">COORDINATION GRAPH</div><h3>Shared signal network</h3></div><span class="graph-legend"><i></i> Shared pattern <span>●</span> Actor IDs</span></div><svg class="network-svg" viewBox="0 0 560 375" role="img" aria-label="Illustration of candidate cluster with accounts connected through a shared text pattern"><line v-for="(node,idx) in graphNodes" :key="'line'+idx" x1="280" y1="190" :x2="node.x" :y2="node.y" stroke="#32746e" stroke-width="1.5" stroke-dasharray="6 5"/><circle cx="280" cy="190" r="52" fill="#123c3b" stroke="#56d1b2" stroke-width="1.5"/><circle cx="280" cy="190" r="42" fill="#194945"/><text x="280" y="185" font-size="30" fill="#6fe7c9" text-anchor="middle">◎</text><text x="280" y="205" font-size="10" font-weight="700" fill="#c9f3e7" text-anchor="middle">{{graphLabel(selectedCluster.signal_type)}}</text><g v-for="node in graphNodes" :key="node.id" :class="['network-node',{selected:activeActor===node.actor}]" @click="activeActor=activeActor===node.actor?null:node.actor" tabindex="0" role="button" :aria-label="'Inspect actor '+node.actor" @keydown.enter.prevent="activeActor=activeActor===node.actor?null:node.actor" @keydown.space.prevent="activeActor=activeActor===node.actor?null:node.actor"><circle :cx="node.x" :cy="node.y" r="29" :fill="activeActor===node.actor?'#33616e':'#162c3d'" :stroke="activeActor===node.actor?'#9fdff5':'#5b91a6'" stroke-width="2"/><text :x="node.x" :y="node.y+4" font-size="12" font-weight="700" text-anchor="middle" fill="#e7f6ff">●</text><text :x="node.x" :y="node.y+46" font-size="13" fill="#b6cddd" text-anchor="middle">{{node.label}}</text></g></svg><div class="graph-footer"><span>◎ Content fingerprint (center)</span><span>● First 36 actor identifiers (not verified identities)</span></div></section><section class="panel evidence-panel"><div class="eyebrow">CLUSTER DETAILS</div><h3>{{selectedCluster.id}}</h3><div class="details-divider"></div><div class="detail-pair"><span>Pattern</span><b>{{signalLabel(selectedCluster.signal_type)}}</b></div><div class="detail-pair"><span>Actors</span><b>{{selectedCluster.distinct_actors}}</b></div><div class="detail-pair"><span>Posts</span><b>{{selectedCluster.post_count}}</b></div><div class="detail-pair"><span>Window</span><b>{{prettyDate(selectedCluster.first_seen)}}<br>to {{prettyDate(selectedCluster.last_seen)}}</b></div><p v-if="selectedCluster.evidence_truncated" class="small-note">Graph shows a capped subset of the {{selectedCluster.post_count}} recorded posts. Use Signal Research to find the remaining records.</p><div class="details-divider"></div><div class="eyebrow">SHARED CONTENT</div><p class="quoted-text">“{{selectedCluster.sample_text}}”</p><button class="btn primary wide" :disabled="busy" @click="openCase(selectedCluster)">{{selectedCluster.investigation_id?'Open investigation':'＋ Start investigation'}}</button></section></div>
              <section class="panel source-panel"><div class="panel-heading"><div><div class="eyebrow">SOURCE PROVENANCE</div><h3>Supporting records <span class="sub-count">{{chosenActorEvidence.length}}</span></h3></div><button v-if="activeActor" class="text-link" @click="activeActor=null">Clear actor filter ×</button></div><div class="table-wrap"><table><thead><tr><th>ACTOR</th><th>SOURCE</th><th>TIMESTAMP (LOCAL)</th><th>RECORD</th></tr></thead><tbody><tr v-for="p in chosenActorEvidence" :key="p.id"><td><b>{{p.actor}}</b></td><td><span class="source-pill">{{p.source}}</span></td><td>{{prettyDate(p.created_at)}}</td><td><a :href="p.url" target="_blank" rel="noopener noreferrer">Source ↗</a></td></tr></tbody></table></div><p class="small-note">Demo source URLs are placeholders on example.org. They do not represent real social media users.</p></section>
            </template><div v-else class="panel empty-state"><span>◎</span><strong>No clusters available</strong><p>Capture public records to explore relationship graphs; there are no current candidate signals.</p><button class="btn primary" @click="navigate('overview')">Go to Overview</button></div>
          </template>

          <template v-else-if="page==='investigations'">
            <div class="page-heading"><div><div class="eyebrow">CASEWORK / HUMAN REVIEW</div><h1>Investigations<span class="heading-dot">.</span></h1><p>Private local analysis. No automatic accusations or publication.</p></div><button v-if="selectedCase" class="btn outline" @click="caseBack()">← All investigations</button></div>
            <template v-if="!selectedCase"><div class="toolbar"><input v-model="search" type="search" placeholder="Search investigation title or notes…" aria-label="Search investigations"><select v-model="statusFilter" aria-label="Filter investigations"><option value="all">All statuses</option><option value="investigating">Investigating</option><option value="needs_context">Needs context</option><option value="dismissed">Dismissed</option><option value="closed">Closed</option></select><span class="results-count">{{filteredCases.length}} investigations</span></div><div v-if="!filteredCases.length" class="panel empty-state"><span>▤</span><strong>No investigations found</strong><p>Start one from a candidate in the detection queue. Cases are created only when requested by a human.</p><button class="btn primary" @click="navigate('detections')">Open detection queue →</button></div><article v-for="item in filteredCases" :key="item.id" class="case-row" @click="selectCase(item)" @keydown.enter="selectCase(item)" role="button" tabindex="0"><div class="case-badge">▤</div><div class="case-row-main"><strong>{{item.title}}</strong><span>{{item.id}} · Updated {{prettyDate(item.updated_at)}}</span></div><span :class="['status',statusClass(item.status)]">{{statusLabel(item.status)}}</span><span class="case-arrow">↗</span></article></template>
            <template v-else><div class="case-header panel"><div><div class="eyebrow">{{selectedCase.id}}</div><h3>{{selectedCase.title}}</h3><p>Linked to candidate cluster {{selectedCase.cluster_id}}</p></div><span :class="['status',statusClass(selectedCase.status)]">{{statusLabel(selectedCase.status)}}</span></div><div class="case-layout"><section class="panel review-form"><div class="eyebrow">INVESTIGATOR WORKSHEET</div><h3>Document your review</h3><label for="case-title">Investigation title</label><input id="case-title" v-model="draft.title" maxlength="120" placeholder="Short descriptive title"><label for="case-status">Review status</label><select id="case-status" v-model="draft.status"><option value="investigating">Investigating</option><option value="needs_context">Needs context</option><option value="dismissed">Dismissed</option><option value="closed">Closed</option></select><label for="case-notes">Evidence assessment &amp; reviewer notes</label><textarea id="case-notes" v-model="draft.notes" maxlength="5000" rows="6" placeholder="What does the evidence actually show? What is still unknown?"></textarea><label for="case-alt">Alternative or non-malicious explanations</label><textarea id="case-alt" v-model="draft.alternative_explanation" maxlength="5000" rows="4" placeholder="e.g. legitimate coordination, news sharing, copy-and-paste…"></textarea><p class="small-note">Closing or dismissing requires at least 10 characters of notes. Saving does not publish a report.</p><button class="btn primary" :disabled="saving" @click="saveReview()">{{saving?'Saving…':'Save investigation'}}</button><button class="btn outline" style="margin-left:10px" @click="openLab(selectedCase.id)">⚗ Open Evidence Lab →</button></section><aside class="case-side"><section class="panel"><div class="eyebrow">LINKED SIGNAL</div><h3>Supporting evidence</h3><template v-if="caseCluster"><p class="quoted-text">“{{caseCluster.sample_text}}”</p><div class="detail-pair"><span>Distinct actors</span><b>{{caseCluster.distinct_actors}}</b></div><div class="detail-pair"><span>Supporting posts</span><b>{{caseCluster.post_count}}</b></div><button class="btn outline wide" @click="inspectCluster(caseCluster)">Inspect source records ↗</button></template><p v-else>Cluster no longer detected. The local investigation record is preserved.</p></section><section class="panel"><div class="eyebrow">LOCAL AUDIT LOG</div><h3>Case activity</h3><div v-for="event in selectedCase.events" :key="event.id" class="event"><span class="event-bullet"></span><div><b>{{event.summary}}</b><small>{{prettyDate(event.created_at)}}</small></div></div><p class="small-note">Records changes, not reviewer identity. Authentication is not implemented in this local prototype.</p></section></aside></div></template>
          </template>

          <template v-else-if="page==='laboratory'">
            <div class="page-heading"><div><div class="eyebrow">EVIDENCE / LOCAL ANALYSIS</div><h1>Evidence Laboratory<span class="heading-dot">.</span></h1><p>Collect source references, compare timelines, inspect domains, and export reproducible research bundles.</p></div><div class="lab-actions"><button class="btn outline" @click="refreshLab()" :disabled="labBusy">↻ Refresh lab</button><button class="btn outline" @click="exportLab('json')" :disabled="!lab||labBusy">↓ Export JSON</button><button class="btn outline" @click="exportLab('csv')" :disabled="!lab||labBusy">↓ Export CSV</button></div></div>
            <div class="notice-strip lab-warning">⚠ <b>Local analyst workspace.</b> Source URLs and times are supplied by the investigator, not fetched or verified by OIO. No bot verdicts, ownership attribution, internet lookup, or public publication.</div>
            <div v-if="!cases.length" class="panel empty-state"><span>⚗</span><strong>Open an investigation first</strong><p>Evidence lives inside a human-reviewed investigation. Choose a detected pattern and start an investigation.</p><button class="btn primary" @click="navigate('detections')">Go to detection queue →</button></div>
            <template v-else>
              <section class="panel lab-case-selector"><div><div class="eyebrow">ACTIVE INVESTIGATION</div><h3>{{lab?.investigation?.title || 'Select an investigation'}}</h3><p class="small-note">References stay linked to their case; review statuses remain managed in Investigations.</p></div><select v-model="labCaseId" @change="refreshLab()" aria-label="Choose investigation for evidence analysis"><option v-for="item in cases" :key="item.id" :value="item.id">{{item.title}}</option></select></section>
              <template v-if="lab">
                <div class="lab-stats"><article class="lab-stat"><span>Detected source posts</span><strong>{{lab.source_posts.length}}</strong><small>Detector-linked posts</small></article><article class="lab-stat"><span>Analyst references</span><strong>{{lab.evidence_items.length}}</strong><small>Manually recorded</small></article><article class="lab-stat"><span>Dated observations</span><strong>{{lab.timeline.length}}</strong><small>UTC timeline events</small></article><article class="lab-stat"><span>Shared content</span><strong>{{lab.cluster?.distinct_actors || '—'}}</strong><small>Distinct source/actor pairs</small></article></div>
                <div class="lab-grid">
                  <section class="panel lab-editor"><div class="eyebrow">01 / EVIDENCE COLLECTOR</div><h3>Attach a public source reference</h3><p class="small-note">This records metadata and a SHA-256 integrity fingerprint. It does not archive a page, prove authenticity, or make a network request.</p>
                    <form @submit.prevent="saveEvidence()"><div class="lab-form-row"><label>Evidence category<select v-model="evidenceForm.kind"><option value="observation">Observation</option><option value="context">Context</option><option value="counterevidence">Counterevidence</option></select></label><label>Observed at (local time, optional)<input v-model="evidenceForm.observed_at" type="datetime-local"></label></div>
                      <label>Descriptive title<input v-model="evidenceForm.title" maxlength="160" required placeholder="e.g. Public response to announcement"></label>
                      <label>Public source URL<input v-model="evidenceForm.source_url" maxlength="2048" type="url" required placeholder="https://example.org/public-record"></label>
                      <label>What does this source show?<textarea v-model="evidenceForm.notes" maxlength="4000" rows="4" placeholder="Describe observations and uncertainties. Do not copy private information."></textarea></label>
                      <label class="lab-checkbox"><input v-model="permissionConfirmed" type="checkbox"><span>I have permission to use and retain these public references for this local investigation.</span></label>
                      <button class="btn primary" type="submit" :disabled="labSaving||!permissionConfirmed">{{labSaving?'Saving…':'＋ Add evidence reference'}}</button>
                    </form>
                    <div class="lab-divider"></div><div class="eyebrow">BATCH INGESTION</div><h3>Import permitted references</h3><p class="small-note">CSV or JSON list, up to 100 records / 128 KiB. Fields: <code>kind,title,source_url,observed_at,notes</code>. Every row is validated before storage; duplicates are skipped.</p>
                    <div class="lab-form-row"><label>Format<select v-model="importFormat"><option value="csv">CSV</option><option value="json">JSON</option></select></label><label>Choose file<input type="file" accept=".json,.csv,text/csv,application/json" @change="onImportFile($event)"></label></div><p class="small-note">{{importFilename || 'No import file selected'}}</p><button class="btn outline" :disabled="labSaving||!permissionConfirmed||!importContent" @click="importReferences()">↑ Import evidence file</button>
                  </section>
                  <section class="panel lab-timeline-panel"><div class="eyebrow">02 / TIMELINE ANALYZER</div><div class="panel-heading"><h3>Observed activity over time</h3><select v-model="timelineUnit" aria-label="Timeline granularity"><option value="minute">Minute</option><option value="hour">Hour</option><option value="day">Day</option></select></div><p class="small-note">Teal = detector posts. Blue = investigator-supplied timestamps. Bars represent observations, not verified bot activity.</p>
                    <div v-if="!displayedTimeline.length" class="lab-chart-empty">No timestamps available for this case.</div><div v-else class="lab-chart" role="img" :aria-label="'Timeline with '+timeline.length+' nonempty time buckets'"><div v-for="bucket in displayedTimeline" :key="bucket.key" class="lab-chart-col" :title="bucket.key+' UTC · '+bucket.posts+' posts · '+bucket.references+' manual references'"><div class="lab-chart-bar"><span class="lab-bar-reference" :style="{height:(bucket.references/maxTimelineCount*100)+'%'}"></span><span class="lab-bar-posts" :style="{height:(bucket.posts/maxTimelineCount*100)+'%'}"></span></div><span class="lab-chart-label">{{bucket.key.slice(11)||bucket.key.slice(5)}}</span></div></div>
                    <div class="lab-legend"><span><i class="lab-dot posts"></i>Detected posts</span><span><i class="lab-dot references"></i>Manual timestamps</span></div><p v-if="timeline.length>32" class="small-note">Showing the 32 latest non-empty buckets ({{timeline.length}} total).</p>
                    <div class="lab-divider"></div><div class="eyebrow">03 / DOMAIN ANALYSIS</div><h3>Publicly referenced domains</h3><p class="small-note">A shared hostname is not evidence of hosting location or common account ownership. These categories must not be combined.</p>
                    <div class="lab-domain-group"><h4>Manually attached sources</h4><p v-if="!lab.domains.manual_reference_hosts.length" class="small-note">No references attached</p><div v-for="d in lab.domains.manual_reference_hosts" :key="d.domain" class="lab-domain-row"><code>{{d.domain}}</code><b>{{d.count}}</b></div></div>
                    <div class="lab-domain-group"><h4>Detector source-record hosts</h4><p v-if="!lab.domains.post_record_hosts.length" class="small-note">No source records</p><div v-for="d in lab.domains.post_record_hosts" :key="d.domain" class="lab-domain-row"><code>{{d.domain}}</code><b>{{d.count}}</b></div></div>
                    <div class="lab-domain-group"><h4>Links included inside source post text</h4><p v-if="!lab.domains.post_text_link_hosts.length" class="small-note">None in this case's post text</p><div v-for="d in lab.domains.post_text_link_hosts" :key="d.domain" class="lab-domain-row"><code>{{d.domain}}</code><b>{{d.count}}</b></div></div>
                  </section>
                </div>
                <section class="panel lab-registry"><div class="panel-heading"><div><div class="eyebrow">04 / EVIDENCE REGISTER</div><h3>Research references <span class="sub-count">{{lab.evidence_items.length}}</span></h3></div><select v-model="evidenceFilter" aria-label="Filter evidence category"><option value="all">All categories</option><option value="observation">Observations</option><option value="context">Context</option><option value="counterevidence">Counterevidence</option></select></div>
                  <p v-if="!filteredEvidence.length" class="small-note">No matching references yet. Add a source URL above or import a permitted CSV/JSON evidence list.</p>
                  <div v-for="item in filteredEvidence" :key="item.id" class="lab-evidence-item"><div class="lab-evidence-head"><div><span :class="['lab-kind','lab-kind-'+item.kind]">{{item.kind}}</span><strong>#{{item.id}} · {{item.title}}</strong></div><button class="btn danger-quiet" :disabled="labSaving" @click="removeEvidence(item)">Remove</button></div><p v-if="item.notes" class="lab-item-notes">{{item.notes}}</p><a :href="item.source_url" target="_blank" rel="noopener noreferrer">{{item.source_url}} ↗</a><div class="lab-meta"><span>Observed: {{prettyDate(item.observed_at)}}</span><span>Added: {{prettyDate(item.captured_at)}}</span><span title="SHA-256 fingerprint of the canonical evidence metadata">SHA-256: <code>{{item.sha256}}</code></span></div></div>
                </section>
                <div class="lab-grid lab-footer-grid"><section class="panel"><div class="eyebrow">05 / DETECTOR PROVENANCE</div><h3>Linked source posts</h3><div class="table-wrap"><table><thead><tr><th>ACTOR</th><th>SOURCE</th><th>TIME</th><th>RECORD</th></tr></thead><tbody><tr v-for="post in lab.source_posts" :key="post.id"><td>{{post.actor}}</td><td>{{post.source}}</td><td>{{prettyDate(post.created_at)}}</td><td><a :href="post.url" target="_blank" rel="noopener noreferrer">Source ↗</a></td></tr></tbody></table></div><p class="small-note">Demo example.org URLs are placeholders; Bluesky observations are public event-stream records, not verified attribution.</p></section><section class="panel"><div class="eyebrow">06 / RESEARCH BUNDLE</div><h3>Reproducible local export</h3><p class="small-note">JSON includes investigation status and notes, review audit history, source-record snapshots, SHA-256 metadata fingerprints and the detector parameters. CSV contains the post and evidence register, with spreadsheet formula escaping.</p><button class="btn primary" @click="exportLab('json')">↓ Download JSON snapshot</button><button class="btn outline" @click="exportLab('csv')">↓ Download evidence CSV</button><p class="small-note">An integrity hash can detect changes to exported metadata, but cannot prove that a remote page was authentic.</p></section></div>
              </template>
            </template>
          </template>

          <template v-else-if="page==='research'">
            <div class="page-heading"><div><div class="eyebrow">05 / LOCAL PATTERN RESEARCH</div><h1>Signal Research<span class="heading-dot">.</span></h1><p>Search the public posts you've already captured and investigate repeated behaviours—without labelling accounts as bots.</p></div><div class="heading-actions"><button class="btn outline" :disabled="researchBusy" @click="refreshResearch()">↻ Refresh research</button><button class="btn primary" @click="openLive()">◉ New observation</button></div></div>
            <div class="notice-strip live-warning">ⓘ All analysis is local. The research profile and declared-language filters affect the post register below; candidate signals are computed from all saved records. No additional social media requests, user profiling, identity attribution or automated publishing. Matching language and shared links are also common in legitimate news-sharing, fandom and advocacy. A 59-post sample may have no detectable patterns.</div>
            <section class="panel research-search"><div class="eyebrow">01 / SEARCH STORED POSTS</div><h3>Local observation search</h3><p class="small-note">Search posts, public actor identifiers or source links. These are observations saved from the bounded collector, not a platform-wide search or a representative sample.</p>
              <form @submit.prevent="refreshResearch()"><div class="research-controls">
                <label class="research-query">Words or phrase<input type="search" v-model="researchQuery" maxlength="120" placeholder="e.g. news, a repeated phrase, an article URL…"></label>
                <label>Source<select v-model="researchScope"><option value="live">Live Bluesky captures</option><option value="all">All local records</option><option value="synthetic">Synthetic only (testing)</option></select></label>
                <label>Research topic preset<select v-model="researchProfile"><option value="all">All selected profiles</option><option v-for="preset in regionProfiles" :key="preset.id" :value="preset.id">{{preset.name}}</option></select></label>
                <label>Declared post language<select v-model="researchLanguage"><option value="all">Any / unknown</option><option v-for="lang in ['bg','en','de','fr','es','it','pl','ro','el','nl','pt','uk']" :key="lang" :value="lang">{{lang.toUpperCase()}}</option></select></label>
                <label>Maximum rows<select v-model.number="researchLimit"><option :value="30">30</option><option :value="60">60</option><option :value="100">100</option></select></label>
                <label>From (UTC)<input type="date" v-model="researchFrom"></label>
                <label>To (UTC)<input type="date" v-model="researchTo"></label>
                <button class="btn primary" type="submit" :disabled="researchBusy">{{researchBusy?'Searching…':'⌕ Run search'}}</button>
              </div></form>
            </section>
            <div class="research-stats">
              <div class="lab-stat"><span>SEARCH MATCHES</span><strong>{{researchData.total_matches}}</strong><small>Matches within locally saved records</small></div>
              <div class="lab-stat"><span>EXACT TEXT LEADS</span><strong>{{researchSignalCounts.exact_text}}</strong><small>3 actors · within 3 minutes</small></div>
              <div class="lab-stat"><span>SIMILAR TEXT LEADS</span><strong>{{researchSignalCounts.near_text}}</strong><small>3 actors · 10-minute window</small></div>
              <div class="lab-stat"><span>SHARED LINK LEADS</span><strong>{{researchSignalCounts.shared_link}}</strong><small>Same full external URL</small></div>
            </div>
            <div class="research-layout">
              <section class="panel research-signals"><div class="panel-heading"><div><div class="eyebrow">02 / INVESTIGATION LEADS</div><h3>Candidate coordination patterns <span class="sub-count">{{researchSignals.length}}</span></h3></div><select v-model="researchType" aria-label="Filter candidate signal types"><option value="all">All signal types</option><option value="exact_text">Exact matching text</option><option value="near_text">Similar wording</option><option value="shared_link">Shared external link</option></select></div>
                <p class="small-note">These leads are computed from all locally stored posts (not restricted by your search filters) using fixed, conservative criteria. They may reflect completely ordinary public activity. No account is declared fake.</p>
                <div v-if="!researchSignals.length" class="research-empty"><span>⌁</span><strong>No candidate signals found</strong><p>Try additional short, permitted observation sessions or inspect the individual posts below. An empty result does not mean bots are absent.</p></div>
                <article v-for="signal in researchSignals" :key="signal.id" class="research-signal"><div class="research-signal-head"><span class="lab-kind">{{signalLabel(signal.signal_type)}}</span><small>{{prettyDate(signal.first_seen)}}</small></div><strong>{{signal.sample_text}}</strong><p class="small-note">{{signal.distinct_actors}} distinct actors · {{signal.post_count}} posts · {{signal.pattern}}</p><p class="research-caveat">{{signal.reason}}</p>
                  <div class="research-actions"><button class="btn outline" @click="toggleResearchEvidence(signal.id)">{{researchExpanded===signal.id?'Hide records':'View records'}}</button><button class="btn outline" @click="inspectCluster(signal)">Explore graph ↗</button><button class="btn primary" :disabled="busy" @click="openCase(signal)">{{signal.investigation_id?'Open investigation':'Start investigation'}}</button></div>
                  <div v-if="researchExpanded===signal.id" class="research-evidence"><div v-for="p in signal.evidence.slice(0,30)" :key="p.id"><code :title="p.actor">{{p.actor}}</code><span>{{prettyDate(p.created_at)}}</span><a :href="p.url" target="_blank" rel="noopener noreferrer">Source ↗</a></div><p v-if="signal.evidence.length>30||signal.evidence_truncated" class="small-note">Showing {{Math.min(30,signal.evidence.length)}} of {{signal.post_count}} supporting post records. Search locally for further records.</p></div>
                </article>
              </section>
              <section class="panel research-timing"><div class="eyebrow">03 / TIMING INSPECTION</div><h3>Hourly observations (UTC)</h3><p class="small-note">Only the {{researchData.posts.length}} visible search results are charted. This is not network-wide traffic or evidence of automation.</p><div v-if="!researchHours.length" class="research-empty"><p>No dated records to visualize.</p></div><div v-else class="research-timing-chart" role="img" :aria-label="'Activity counts across '+researchHours.length+' hourly buckets'"><div v-for="bucket in researchHours" :key="bucket.key" class="research-hour" :title="bucket.key+' UTC · '+bucket.count+' posts'"><b>{{bucket.count}}</b><div class="research-hour-track"><span :style="{height:(bucket.count/researchMaxHourly*100)+'%'}"></span></div><small>{{bucket.key.slice(11)}}</small></div></div>
                <div class="lab-divider"></div><div class="eyebrow">LIMITATIONS</div><ul class="research-limitations"><li>No algorithm can prove an account is automated using post timing alone.</li><li>Our exact text and URL detectors intentionally miss many patterns.</li><li>Identical campaign language may be legitimate; inspect counterevidence.</li><li>The Bluesky stream is sampled and not independently signature-verified.</li></ul>
              </section>
            </div>
            <section class="panel research-records"><div class="panel-heading"><div><div class="eyebrow">04 / POST REGISTER</div><h3>Matching stored records <span class="sub-count">{{researchData.posts.length}}</span></h3></div><span class="small-note">{{researchData.total_matches}} matching; {{researchData.truncated?'showing first '+researchData.limit:'all visible'}}</span></div>
              <p v-if="!researchData.posts.length" class="research-empty">No saved posts match these filters. Try a broader query or collect another permitted sample.</p>
              <article v-for="post in researchData.posts" :key="post.id" class="live-post"><div class="live-post-top"><span class="lab-kind">{{post.session_id?'LIVE':'LOCAL'}}</span><span v-if="post.session_id" class="research-profile-label">{{post.profile_id || 'custom'}} topic · {{post.declared_langs?.join(', ') || 'unknown language'}}</span><code :title="post.actor">{{post.actor.length>48?post.actor.slice(0,45)+'…':post.actor}}</code><span>{{prettyDate(post.created_at)}}</span></div><p>{{post.text}}</p><div v-if="post.external_links?.length" class="research-external"><span>Links observed in public facets/embeds (not fetched):</span><a v-for="link in post.external_links.slice(0,5)" :key="link" :href="link" target="_blank" rel="noopener noreferrer">{{link}}</a></div><div class="live-post-meta"><span>{{post.session_id?'Jetstream session '+post.session_id:'Local source '+post.source}}</span><a :href="post.url" target="_blank" rel="noopener noreferrer">Source record ↗</a></div></article>
            </section>
          </template>

          <template v-else-if="page==='live'">
            <div class="page-heading"><div><div class="eyebrow">04 / AUTHORIZED PUBLIC STREAM</div><h1>Live Data Research<span class="heading-dot">.</span></h1><p>Run a short, topic-scoped Bluesky public-post observation. Nothing is collected unless you start it.</p></div><div class="heading-actions"><button class="btn outline" :disabled="liveBusy" @click="refreshLive()">↻ Refresh status</button></div></div>
            <div class="notice-strip live-warning">⚠ Jetstream delivers public events but not cryptographic repository proofs. This tool is a bounded sample, not a representative survey or proof of bot activity. Posts can be edited or deleted after observation. No automatic publication, identity tracing or political classifications.</div>
            <div class="live-stats">
              <div class="lab-stat"><span>COLLECTOR STATE</span><strong class="live-state" :class="{'live-on':liveInfo.active}">{{liveSession?.status || 'Idle'}}</strong><small>{{liveInfo.active ? 'A local observation is in progress' : 'No active network observation'}}</small></div>
              <div class="lab-stat"><span>EVENTS OBSERVED</span><strong>{{liveSession?.scanned ?? 0}}</strong><small>Includes non-post event messages; maximum {{liveInfo.max_scanned_events || 50000}}</small></div>
              <div class="lab-stat"><span>FILTERED POST MATCHES</span><strong>{{liveSession?.matched ?? 0}}</strong><small>Matching text and language, not bot evidence</small></div>
              <div class="lab-stat"><span>SAVED LIVE POSTS</span><strong>{{liveInfo.stored_posts || 0}}</strong><small>All local sessions · cap {{liveInfo.storage_limit || 5000}}</small></div>
            </div>
            <section v-if="liveSession?.diagnostics_available" class="panel collector-diagnostics" aria-label="Collector filter diagnostics">
              <div class="panel-heading"><div><div class="eyebrow">COLLECTOR DIAGNOSTICS · LOCAL AGGREGATES</div><h3>Where did the events go?</h3><p class="small-note">These counts describe only this bounded session. No inferred bot identities, account locations or population estimates.</p></div><span class="lab-kind">{{liveSession.mode === 'diagnostic' ? 'DIAGNOSTICS ONLY' : 'CAPTURE + DIAGNOSTICS'}}</span></div>
              <div class="diagnostic-funnel">
                <div><span>Stream events</span><strong>{{liveSession.scanned ?? 0}}</strong><small>All received messages</small></div>
                <div><span>Post creation events</span><strong>{{liveSession.post_creations ?? 0}}</strong><small>Recognized public post creates</small></div>
                <div><span>Text-bearing posts</span><strong>{{liveSession.eligible_text_posts ?? 0}}</strong><small>Eligible text for keyword check</small></div>
                <div><span>Keyword matches</span><strong>{{liveSession.keyword_matches ?? 0}}</strong><small>Before declared-language filtering</small></div>
                <div><span>Rejected by language</span><strong>{{liveSession.language_rejections ?? 0}}</strong><small>Keyword matched, language did not</small></div>
                <div><span>Accepted matches</span><strong>{{liveSession.matched ?? 0}}</strong><small>Matched + valid source metadata</small></div>
              </div>
              <div class="diagnostic-bottom">
                <div><div class="eyebrow">DECLARED LANGUAGES SEEN</div><p class="small-note">Counts include only client-declared language tags on text-bearing posts, even when they did not match your keywords. One post may declare multiple languages. Tags are unverified.</p>
                  <div v-if="Object.keys(liveSession.language_counts || {}).length" class="language-tiles"><span v-for="(count,tag) in liveSession.language_counts" :key="tag" class="language-tile"><code>{{tag}}</code> <b>{{count}}</b></span></div>
                  <p v-else class="small-note">No declared language tags observed in eligible post text yet.</p>
                  <div class="diagnostic-extra"><span>Unknown / undeclared language: <b>{{liveSession.unknown_language_posts ?? 0}}</b></span><span>Malformed stream messages: <b>{{liveSession.malformed_events ?? 0}}</b></span><span>Invalid post records / metadata: <b>{{liveSession.invalid_post_records ?? 0}}</b></span></div>
                </div>
                <div class="diagnostic-explainer"><strong>{{liveSession.mode === 'diagnostic' ? 'Discovery-only: nothing retained about individual posts' : 'Collection: matching posts may be saved'}}</strong><p>Diagnostics keep aggregate counters and language-tag totals with the session report. Discovery-only mode does not store nonmatching or matching post bodies, DIDs or URLs. All modes are time/event-limited, opt-in and local.</p><p v-if="liveSession.mode==='diagnostic'">Saved posts from earlier collection sessions remain untouched.</p></div>
              </div>
            </section>
            <div class="live-layout">
              <section class="panel live-control-panel"><div class="eyebrow">01 / COLLECTION CONTROLS</div><h3>Controlled observation</h3><p class="small-note">Only official Bluesky-hosted Jetstream endpoints are supported. New records are observed from the live tail; no account lookup, private API or historical replay. No background collection on startup.</p>
                <form @submit.prevent="startLive()">
                  <div class="region-panel"><div class="eyebrow">EUROPEAN TOPIC RESEARCH</div>
                    <label>Research preset (topics, not account locations)<select v-model="liveConfig.profile_id" @change="selectResearchProfile" :disabled="liveInfo.active||liveBusy"><option v-for="preset in regionProfiles" :key="preset.id" :value="preset.id">{{preset.flag}} {{preset.name}}</option></select></label>
                    <p class="small-note">{{selectedProfile?.description || 'Choose an optional research preset. The feed is global.'}}</p>
                    <p class="region-warning">Selecting Bulgaria, the UK or an EU topic does not locate a user. Keyword and language filters describe posts, not people.</p>
                    <div class="region-preset-summary"><span>Display timezone: <b>{{liveZone}}</b></span><span>Saved under preset: <b>{{profilePostCounts[liveConfig.profile_id] || 0}}</b></span></div>
                  </div>
                  <label>Research session mode<select v-model="liveConfig.mode" :disabled="liveInfo.active||liveBusy"><option value="capture">Collect matched public posts + diagnostics</option><option value="diagnostic">Diagnostics only — retain no posts or actor identifiers</option></select></label>
                  <p class="small-note">Diagnostics-only still checks your keyword and language filter, but records aggregate counts only; no post bodies, DIDs, URLs, or new detection leads are saved. Existing captures remain unchanged.</p>
                  <label>Declared post languages (optional, comma-separated; blank = any)<input v-model.trim="liveLanguageInput" maxlength="45" placeholder="e.g. bg, en, de" :disabled="liveInfo.active||liveBusy"></label>
                  <p class="small-note">Language tags are supplied by the posting client and can be missing or incorrect. A non-empty filter excludes posts with no declared languages.</p>
                  <label>Keyword(s), separated by | (1–3 literal phrases)<input v-model.trim="liveConfig.keyword" minlength="4" maxlength="90" placeholder="e.g. public announcement | community notice" required :disabled="liveInfo.active||liveBusy"></label>
                  <div class="lab-form-row"><label>Jetstream endpoint (not user geography)<select v-model="liveConfig.region" :disabled="liveInfo.active||liveBusy"><option value="us-east">US East</option><option value="us-west">US West</option></select></label>
                    <label>Observation duration<select v-model.number="liveConfig.duration_seconds" :disabled="liveInfo.active||liveBusy"><option :value="30">30 seconds</option><option :value="60">60 seconds</option><option :value="90">90 seconds</option><option :value="180">3 minutes</option></select></label></div>
                  <label>Maximum posts saved this session (capture mode only)<select v-model.number="liveConfig.max_posts" :disabled="liveInfo.active||liveBusy"><option :value="25">25 posts</option><option :value="50">50 posts</option><option :value="100">100 posts</option><option :value="200">200 posts</option></select></label>
                  <label class="lab-checkbox"><input type="checkbox" v-model="livePermission" :disabled="liveInfo.active||liveBusy"><span>I confirm this is permitted public-data research and understand posts are stored locally for at most 7 days. I will review source permissions and minimize retained personal data.</span></label>
                  <p class="small-note">An OR list matches any of up to three literal phrases in public posts. The stream covers global activity and does not query accounts, target individuals, or broaden the maximum storage limit.</p><div class="live-buttons"><button type="submit" class="btn primary" :disabled="liveInfo.active||liveBusy||!livePermission">◉ Start observation</button><button type="button" class="btn outline" :disabled="!liveInfo.active||liveBusy" @click="stopLive()">■ Stop</button></div>
                </form>
                <p class="small-note">Each session also stops after 50,000 scanned events or at your post cap. Repeated sessions are not a statistically representative sample.</p>
              </section>
              <section class="panel live-session-panel"><div class="eyebrow">02 / SESSION REPORT</div><h3>Source provenance and limits</h3>
                <template v-if="liveSession"><div class="live-kv"><span>Session</span><code>{{liveSession.id}}</code></div><div class="live-kv"><span>Phrase filter</span><strong>{{liveSession.keyword}}</strong></div><div class="live-kv"><span>Observation mode</span><strong>{{liveSession.mode === 'diagnostic' ? 'Aggregate diagnostics only' : 'Matched post capture'}}</strong></div><div class="live-kv"><span>Research profile</span><strong>{{liveSession.profile_id || 'custom'}} (topic only)</strong></div><div class="live-kv"><span>Declared language filter</span><strong>{{liveSession.languages?.join(', ') || 'Any (including unknown)'}}</strong></div><div class="live-kv"><span>Stream endpoint</span><strong>{{liveSession.region}}</strong></div><div class="live-kv"><span>Started ({{sessionZone}})</span><strong>{{formatRegionTime(liveSession.started_at,sessionZone)}}</strong></div><div class="live-kv"><span>Ended ({{sessionZone}})</span><strong>{{formatRegionTime(liveSession.ended_at,sessionZone)}}</strong></div><div class="live-kv"><span>New posts this session</span><strong>{{liveSession.inserted}}</strong></div><div class="live-kv"><span>Deleted / updated during capture</span><strong>{{liveSession.removed || 0}}</strong></div><div class="live-kv"><span>Stop reason</span><strong>{{liveSession.stop_reason || 'In progress'}}</strong></div>
                  <p v-if="liveSession.error" class="live-session-error" role="alert">{{liveSession.error}}</p>
                </template><div v-else class="empty-state"><span>◉</span><strong>No sessions yet</strong><p>Choose a keyword and start a bounded capture to examine real-world public activity.</p></div>
                <div class="lab-divider"></div><div class="eyebrow">DATA RETENTION</div><p class="small-note">OIO deletes captured post bodies and provenance automatically after {{liveInfo.retention_days || 7}} days on backend startup and before each new session. Manually recorded investigation notes and links have separate retention and must be reviewed independently.</p>
                <button class="btn danger-quiet" :disabled="liveInfo.active||liveBusy||!liveInfo.stored_posts" @click="clearLivePosts()">Delete all captured live posts</button>
              </section>
            </div>
            <section class="panel live-records-panel"><div class="panel-heading"><div><div class="eyebrow">03 / OBSERVATION REGISTER</div><h3>Most recent local captures <span class="sub-count">{{livePosts.length}}</span></h3></div><button class="text-link" @click="navigate('detections')">Check detection queue →</button></div>
              <p class="small-note">Showing up to 60 stored public posts. A source link is a reference, not independently verified proof that the remote record still exists. Identifiers are public DIDs, not verified identities.</p>
              <div v-if="!livePosts.length" class="live-record-empty">No live posts stored yet. Try a common literal phrase for a short session; a zero-match result is valid and does not imply an outage.</div>
              <article v-for="post in livePosts" :key="post.id" class="live-post"><div class="live-post-top"><span class="lab-kind">PUBLIC JETSTREAM</span><code :title="post.actor">{{post.actor.length>38 ? post.actor.slice(0,35)+'…' : post.actor}}</code><span>{{formatRegionTime(post.created_at,profileTimezone(regionProfiles,post.profile_id))}}</span></div><p>{{post.text}}</p><div class="region-post-label">{{post.profile_id || 'custom'}} topic · {{post.declared_langs?.join(', ') || 'language not declared'}} · Not geo-located</div><div class="live-post-meta"><span>Observed by {{post.provider}} · CID (unverified): {{post.cid || 'not supplied'}}</span><a :href="post.url" target="_blank" rel="noopener noreferrer">View public record ↗</a></div></article>
            </section>
            <div class="notice-strip live-footnote">OIO v0.5.2 adds filter-funnel diagnostics and an aggregate-only discovery mode. OIO v0.5.1 adds topic presets and declared-language filters; none establish location. OIO v0.5 also checks longer near-duplicate wording and full shared links across observed posts. At least three distinct actor identifiers are still required. These are clues, not bot verdicts. A small keyword sample may produce zero candidates.</div>
          </template>

          <template v-else-if="page==='methodology'"><div class="page-heading"><div><div class="eyebrow">TRANSPARENT METHODS</div><h1>How OIO works<span class="heading-dot">.</span></h1><p>Understand the engine's limitations before interpreting a candidate.</p></div></div><div class="method-grid"><article class="panel"><div class="method-number">01</div><h3>Normalize text</h3><p>Lowercase text, strip URLs, collapse whitespace, then compute a SHA-256 fingerprint. Additional v0.5 token-bigram similarity checks detect some longer text variations, not meaning.</p></article><article class="panel"><div class="method-number">02</div><h3>Group within time</h3><p>Matching text is grouped into non-overlapping 180-second windows anchored to the earliest post, avoiding simple chain-bridging.</p></article><article class="panel"><div class="method-number">03</div><h3>Flag candidate signals</h3><p>Three source/actor pairs are required. v0.5 adds near-duplicate text and full shared external links over 10 minutes. The detector does not determine whether an account is automated.</p></article><article class="panel"><div class="method-number">04</div><h3>Document alternatives</h3><p>Analysts review source records, legitimate explanations and counterevidence. Their notes and status changes are stored locally.</p></article></div><div class="notice-strip large">⚠ This prototype is not an attribution engine or a bot classifier. Optional live collection is explicitly started, keyword-scoped, capped and time-limited. It does not identify illegal data centres or private operators. Keep it on localhost until authentication, retention, source permissions and governance are independently addressed.</div></template>
          <footer>OIO v0.5.2 · Local research mode · Evidence over assumptions · Never a bot verdict</footer>
        </main>
      </div>
    </div>
  `,
}).mount('#app');
