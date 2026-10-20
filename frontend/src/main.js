import { createApp, computed, onMounted, ref } from 'vue';
import './style.css';

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
    const reviewCount = computed(() => clusters.value.filter(c => !c.investigation_id).length);
    const graphNodes = computed(() => {
      if (!selectedCluster.value) return [];
      const identities = [...new Map(selectedCluster.value.evidence.map(p => [p.source + ':' + p.actor, p])).values()];
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

    function caseBack() { selectedCase.value = null; }
    function statusLabel(status) { return STATUS_LABELS[status] || 'Unreviewed'; }
    function statusClass(status) { return 'status-' + (status || 'unreviewed'); }
    onMounted(refresh);

    return {
      page, stats, clusters, cases, selectedCase, selectedCluster, selectedClusterId, caseCluster,
      filteredClusters, filteredCases, graphNodes, activeActor, chosenActorEvidence,
      search, statusFilter, draft, error, notice, loading, saving, busy, reviewCount,
      refresh, loadDemo, navigate, inspectCluster, openCase, selectCase, saveReview, caseBack,
      statusLabel, statusClass, prettyDate,
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
        </nav>
        <div class="sidebar-label sidebar-section">REFERENCE</div>
        <nav class="side-nav"><button :class="['nav-item',{active:page==='methodology'}]" @click="navigate('methodology')"><span class="nav-icon">ⓘ</span> Methodology</button></nav>
        <div class="sidebar-footer"><span class="pulse"></span> Local research mode <small>Synthetic records only · v0.2</small></div>
      </aside>

      <div class="workspace">
        <header class="topbar"><div class="crumb">WORKSPACE <span>/</span> <strong>{{ page === 'overview' ? 'Overview' : page === 'detections' ? 'Detection queue' : page === 'network' ? 'Network explorer' : page === 'investigations' ? 'Investigations' : 'Methodology' }}</strong></div><div class="top-actions"><span class="privacy-label">● LOCAL · NOT PUBLIC</span><button class="icon-button" title="Refresh data" :disabled="loading" @click="refresh()">↻</button></div></header>
        <main class="main-content">
          <div v-if="error" role="alert" class="alert error"><strong>Something needs attention</strong><span>{{error}}</span><button @click="error=''">×</button></div>
          <div v-if="notice" role="status" class="alert notice"><span>{{notice}}</span><button @click="notice=''">×</button></div>

          <template v-if="page==='overview'">
            <div class="page-heading"><div><div class="eyebrow">THE RESEARCH DESK</div><h1>Observatory overview<span class="heading-dot">.</span></h1><p>Understand the patterns. Investigate the evidence. Avoid assumptions.</p></div><div class="heading-actions"><button class="btn outline" @click="refresh()">↻ Refresh</button><button class="btn primary" :disabled="busy" @click="loadDemo()">{{busy?'Loading…':'＋ Load demo data'}}</button></div></div>
            <div class="hero"><div><span class="hero-label"><i></i> EVIDENCE FIRST / RESEARCH PROTOTYPE</span><h2>Signals are not verdicts.</h2><p>OIO highlights coordination candidates and supports documented human review. Synthetic examples only; no real people or organisations are being assessed.</p><button class="btn hero-btn" @click="navigate('detections')">Explore candidate signals <span>↗</span></button></div><div class="hero-orbit" aria-hidden="true"><div class="orbit-ring one"></div><div class="orbit-ring two"></div><div class="orbit-center">◎</div><span class="orbit-node node-a"></span><span class="orbit-node node-b"></span><span class="orbit-node node-c"></span></div></div>
            <div class="stats-grid">
              <article class="stat-card"><div class="stat-top"><span>INGESTED POSTS</span><b>↗</b></div><strong>{{stats.posts}}</strong><div class="stat-bottom">Synthetic records in local store</div></article>
              <article class="stat-card"><div class="stat-top"><span>CANDIDATE CLUSTERS</span><b>⌁</b></div><strong>{{stats.candidate_clusters}}</strong><div class="stat-bottom">Patterns requiring human review</div></article>
              <article class="stat-card"><div class="stat-top"><span>OPEN INVESTIGATIONS</span><b>▤</b></div><strong>{{stats.open_investigations}}</strong><div class="stat-bottom">Research notes &amp; context</div></article>
              <article class="stat-card"><div class="stat-top"><span>PUBLISHED REPORTS</span><b>◇</b></div><strong>{{stats.published_cases}}</strong><div class="stat-bottom">Publishing intentionally disabled</div></article>
            </div>
            <div class="overview-grid"><section class="panel"><div class="panel-heading"><div><div class="eyebrow">REVIEW PIPELINE</div><h3>Latest candidate patterns</h3></div><button class="text-link" @click="navigate('detections')">View all →</button></div><div v-if="!clusters.length" class="empty-state"><span>◎</span><strong>No candidate patterns yet</strong><p>Load demonstration data to verify the end-to-end detection pipeline.</p></div><div v-for="c in clusters.slice(0,4)" :key="c.id" class="overview-row"><span class="row-icon">⌁</span><div class="row-main"><b>Cluster {{c.id}}</b><small>{{c.distinct_actors}} distinct actors · {{c.post_count}} posts</small></div><span :class="['status',statusClass(c.review.status)]">{{statusLabel(c.review.status)}}</span><button class="tiny-button" @click="inspectCluster(c)">↗</button></div></section><section class="panel side-info"><div class="eyebrow">RESEARCH PRINCIPLES</div><h3>Built for careful investigation</h3><div class="principle"><span>01</span><div><b>Discover patterns</b><p>Timing and identical text signal possible coordination, not intent.</p></div></div><div class="principle"><span>02</span><div><b>Check counterevidence</b><p>Record legitimate explanations before deciding what a pattern means.</p></div></div><div class="principle"><span>03</span><div><b>Document a review</b><p>Decisions and edits are saved in a local audit trail.</p></div></div></section></div>
          </template>

          <template v-else-if="page==='detections'">
            <div class="page-heading"><div><div class="eyebrow">SIGNAL DETECTION</div><h1>Detection queue<span class="heading-dot">.</span></h1><p>Investigative leads awaiting context and human review.</p></div><button class="btn outline" @click="refresh()">↻ Refresh</button></div>
            <div class="notice-strip">ⓘ &nbsp; Identical posts within 180 seconds may be ordinary coordination, breaking news, or quotation. Never infer that these accounts are fake.</div>
            <div class="toolbar"><input v-model="search" type="search" placeholder="Search cluster, text or actor…" aria-label="Search candidate clusters"><select v-model="statusFilter" aria-label="Filter by review status"><option value="all">All statuses</option><option value="unreviewed">Unreviewed</option><option value="investigating">Investigating</option><option value="needs_context">Needs context</option><option value="dismissed">Dismissed</option><option value="closed">Closed</option></select><span class="results-count">{{filteredClusters.length}} results</span></div>
            <div v-if="!filteredClusters.length" class="empty-state panel"><span>⌁</span><strong>No matching clusters</strong><p>Change filters or load the synthetic dataset from Overview.</p></div>
            <article v-for="c in filteredClusters" :key="c.id" class="cluster-card"><div class="cluster-top"><div class="cluster-number">◎</div><div class="cluster-title"><div><strong>Cluster {{c.id}}</strong><span :class="['status',statusClass(c.review.status)]">{{statusLabel(c.review.status)}}</span></div><small>{{c.pattern}}</small></div><button class="icon-button" title="View network" @click="inspectCluster(c)">↗</button></div><blockquote>{{c.sample_text}}</blockquote><div class="cluster-bottom"><div class="cluster-meta"><span><b>{{c.distinct_actors}}</b> distinct actors</span><span><b>{{c.post_count}}</b> posts</span><span>{{prettyDate(c.first_seen)}}</span></div><div class="cluster-actions"><button class="btn outline" @click="inspectCluster(c)">View evidence &amp; graph</button><button class="btn primary" :disabled="busy" @click="openCase(c)">{{c.investigation_id?'Open investigation':'＋ Start investigation'}}</button></div></div></article>
          </template>

          <template v-else-if="page==='network'">
            <div class="page-heading"><div><div class="eyebrow">RELATIONSHIP VISUALIZATION</div><h1>Network explorer<span class="heading-dot">.</span></h1><p>Explore shared content and timing without implying shared ownership.</p></div><select class="cluster-selector" v-model="selectedClusterId" @change="activeActor=null" aria-label="Select a cluster"><option v-for="c in clusters" :key="c.id" :value="c.id">Cluster {{c.id}}</option></select></div>
            <template v-if="selectedCluster">
              <div class="network-layout"><section class="panel graph-panel"><div class="panel-heading"><div><div class="eyebrow">COORDINATION GRAPH</div><h3>Shared content network</h3></div><span class="graph-legend"><i></i> Shared text <span>●</span> Accounts</span></div><svg class="network-svg" viewBox="0 0 560 375" role="img" aria-label="Illustration of candidate cluster with accounts connected through a shared text pattern"><line v-for="(node,idx) in graphNodes" :key="'line'+idx" x1="280" y1="190" :x2="node.x" :y2="node.y" stroke="#32746e" stroke-width="1.5" stroke-dasharray="6 5"/><circle cx="280" cy="190" r="52" fill="#123c3b" stroke="#56d1b2" stroke-width="1.5"/><circle cx="280" cy="190" r="42" fill="#194945"/><text x="280" y="185" font-size="30" fill="#6fe7c9" text-anchor="middle">◎</text><text x="280" y="205" font-size="10" font-weight="700" fill="#c9f3e7" text-anchor="middle">MATCHING TEXT</text><g v-for="node in graphNodes" :key="node.id" :class="['network-node',{selected:activeActor===node.actor}]" @click="activeActor=activeActor===node.actor?null:node.actor" tabindex="0" role="button" :aria-label="'Inspect actor '+node.actor" @keydown.enter.prevent="activeActor=activeActor===node.actor?null:node.actor" @keydown.space.prevent="activeActor=activeActor===node.actor?null:node.actor"><circle :cx="node.x" :cy="node.y" r="29" :fill="activeActor===node.actor?'#33616e':'#162c3d'" :stroke="activeActor===node.actor?'#9fdff5':'#5b91a6'" stroke-width="2"/><text :x="node.x" :y="node.y+4" font-size="12" font-weight="700" text-anchor="middle" fill="#e7f6ff">●</text><text :x="node.x" :y="node.y+46" font-size="13" fill="#b6cddd" text-anchor="middle">{{node.label}}</text></g></svg><div class="graph-footer"><span>◎ Content fingerprint (center)</span><span>● Distinct public-facing actors (synthetic)</span></div></section><section class="panel evidence-panel"><div class="eyebrow">CLUSTER DETAILS</div><h3>{{selectedCluster.id}}</h3><div class="details-divider"></div><div class="detail-pair"><span>Pattern</span><b>Exact text match</b></div><div class="detail-pair"><span>Actors</span><b>{{selectedCluster.distinct_actors}}</b></div><div class="detail-pair"><span>Posts</span><b>{{selectedCluster.post_count}}</b></div><div class="detail-pair"><span>Window</span><b>{{prettyDate(selectedCluster.first_seen)}}<br>to {{prettyDate(selectedCluster.last_seen)}}</b></div><div class="details-divider"></div><div class="eyebrow">SHARED CONTENT</div><p class="quoted-text">“{{selectedCluster.sample_text}}”</p><button class="btn primary wide" :disabled="busy" @click="openCase(selectedCluster)">{{selectedCluster.investigation_id?'Open investigation':'＋ Start investigation'}}</button></section></div>
              <section class="panel source-panel"><div class="panel-heading"><div><div class="eyebrow">SOURCE PROVENANCE</div><h3>Supporting records <span class="sub-count">{{chosenActorEvidence.length}}</span></h3></div><button v-if="activeActor" class="text-link" @click="activeActor=null">Clear actor filter ×</button></div><div class="table-wrap"><table><thead><tr><th>ACTOR</th><th>SOURCE</th><th>TIMESTAMP (LOCAL)</th><th>RECORD</th></tr></thead><tbody><tr v-for="p in chosenActorEvidence" :key="p.id"><td><b>{{p.actor}}</b></td><td><span class="source-pill">{{p.source}}</span></td><td>{{prettyDate(p.created_at)}}</td><td><a :href="p.url" target="_blank" rel="noopener noreferrer">Source ↗</a></td></tr></tbody></table></div><p class="small-note">Demo source URLs are placeholders on example.org. They do not represent real social media users.</p></section>
            </template><div v-else class="panel empty-state"><span>◎</span><strong>No clusters available</strong><p>Load demonstration data to explore the synthetic relationship graph.</p><button class="btn primary" @click="navigate('overview')">Go to Overview</button></div>
          </template>

          <template v-else-if="page==='investigations'">
            <div class="page-heading"><div><div class="eyebrow">CASEWORK / HUMAN REVIEW</div><h1>Investigations<span class="heading-dot">.</span></h1><p>Private local analysis. No automatic accusations or publication.</p></div><button v-if="selectedCase" class="btn outline" @click="caseBack()">← All investigations</button></div>
            <template v-if="!selectedCase"><div class="toolbar"><input v-model="search" type="search" placeholder="Search investigation title or notes…" aria-label="Search investigations"><select v-model="statusFilter" aria-label="Filter investigations"><option value="all">All statuses</option><option value="investigating">Investigating</option><option value="needs_context">Needs context</option><option value="dismissed">Dismissed</option><option value="closed">Closed</option></select><span class="results-count">{{filteredCases.length}} investigations</span></div><div v-if="!filteredCases.length" class="panel empty-state"><span>▤</span><strong>No investigations found</strong><p>Start one from a candidate in the detection queue. Cases are created only when requested by a human.</p><button class="btn primary" @click="navigate('detections')">Open detection queue →</button></div><article v-for="item in filteredCases" :key="item.id" class="case-row" @click="selectCase(item)" @keydown.enter="selectCase(item)" role="button" tabindex="0"><div class="case-badge">▤</div><div class="case-row-main"><strong>{{item.title}}</strong><span>{{item.id}} · Updated {{prettyDate(item.updated_at)}}</span></div><span :class="['status',statusClass(item.status)]">{{statusLabel(item.status)}}</span><span class="case-arrow">↗</span></article></template>
            <template v-else><div class="case-header panel"><div><div class="eyebrow">{{selectedCase.id}}</div><h3>{{selectedCase.title}}</h3><p>Linked to candidate cluster {{selectedCase.cluster_id}}</p></div><span :class="['status',statusClass(selectedCase.status)]">{{statusLabel(selectedCase.status)}}</span></div><div class="case-layout"><section class="panel review-form"><div class="eyebrow">INVESTIGATOR WORKSHEET</div><h3>Document your review</h3><label for="case-title">Investigation title</label><input id="case-title" v-model="draft.title" maxlength="120" placeholder="Short descriptive title"><label for="case-status">Review status</label><select id="case-status" v-model="draft.status"><option value="investigating">Investigating</option><option value="needs_context">Needs context</option><option value="dismissed">Dismissed</option><option value="closed">Closed</option></select><label for="case-notes">Evidence assessment &amp; reviewer notes</label><textarea id="case-notes" v-model="draft.notes" maxlength="5000" rows="6" placeholder="What does the evidence actually show? What is still unknown?"></textarea><label for="case-alt">Alternative or non-malicious explanations</label><textarea id="case-alt" v-model="draft.alternative_explanation" maxlength="5000" rows="4" placeholder="e.g. legitimate coordination, news sharing, copy-and-paste…"></textarea><p class="small-note">Closing or dismissing requires at least 10 characters of notes. Saving does not publish a report.</p><button class="btn primary" :disabled="saving" @click="saveReview()">{{saving?'Saving…':'Save investigation'}}</button></section><aside class="case-side"><section class="panel"><div class="eyebrow">LINKED SIGNAL</div><h3>Supporting evidence</h3><template v-if="caseCluster"><p class="quoted-text">“{{caseCluster.sample_text}}”</p><div class="detail-pair"><span>Distinct actors</span><b>{{caseCluster.distinct_actors}}</b></div><div class="detail-pair"><span>Supporting posts</span><b>{{caseCluster.post_count}}</b></div><button class="btn outline wide" @click="inspectCluster(caseCluster)">Inspect source records ↗</button></template><p v-else>Cluster no longer detected. The local investigation record is preserved.</p></section><section class="panel"><div class="eyebrow">LOCAL AUDIT LOG</div><h3>Case activity</h3><div v-for="event in selectedCase.events" :key="event.id" class="event"><span class="event-bullet"></span><div><b>{{event.summary}}</b><small>{{prettyDate(event.created_at)}}</small></div></div><p class="small-note">Records changes, not reviewer identity. Authentication is not implemented in this local prototype.</p></section></aside></div></template>
          </template>

          <template v-else-if="page==='methodology'"><div class="page-heading"><div><div class="eyebrow">TRANSPARENT METHODS</div><h1>How OIO works<span class="heading-dot">.</span></h1><p>Understand the engine's limitations before interpreting a candidate.</p></div></div><div class="method-grid"><article class="panel"><div class="method-number">01</div><h3>Normalize text</h3><p>Lowercase text, strip URLs, collapse whitespace, then compute a SHA-256 fingerprint. Similar meaning with different wording is not detected.</p></article><article class="panel"><div class="method-number">02</div><h3>Group within time</h3><p>Matching text is grouped into non-overlapping 180-second windows anchored to the earliest post, avoiding simple chain-bridging.</p></article><article class="panel"><div class="method-number">03</div><h3>Flag candidate signals</h3><p>A group must contain at least three distinct source/actor pairs. The detector does not determine whether an actor is human or automated.</p></article><article class="panel"><div class="method-number">04</div><h3>Document alternatives</h3><p>Analysts review source records, legitimate explanations and counterevidence. Their notes and status changes are stored locally.</p></article></div><div class="notice-strip large">⚠ This prototype is not an attribution engine, a bot classifier, or a live surveillance tool. It does not identify illegal data centres or private operators. Keep it on localhost until authentication, retention, source permissions and governance are independently addressed.</div></template>
          <footer>OIO v0.2 · Synthetic research dataset · Evidence over assumptions · Never a bot verdict</footer>
        </main>
      </div>
    </div>
  `,
}).mount('#app');
