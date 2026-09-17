/* ═══════════════════════════════════════════════════════════════
   AGENTUSE SpaceGrid client — every event from the agent core
   streams here over WebSocket and becomes visible, live.
   ═══════════════════════════════════════════════════════════════ */
(() => {
'use strict';

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

const state = {
  seq: 0,                 // last processed event seq
  ws: null,
  core: 'heuristic',
  neural: false,
  mode: localStorage.getItem('au-mode') || 'jarvis',
  voice: false,
  missions: new Map(),    // id -> {goal, mode, status, actions}
  routes: new Map(),      // id -> route
  artifacts: new Map(),   // path -> {bytes}
  actionsTotal: 0,
  eventsTotal: 0,
  buckets: new Array(42).fill(0),
  booted: false,
};

/* ─────────────── utilities ─────────────── */
const fmtTime = (ts) => {
  const d = ts ? new Date(ts * 1000) : new Date();
  return d.toTimeString().slice(0, 8);
};
const fmtBytes = (n) => n > 1024 ? (n / 1024).toFixed(1) + 'K' : String(n | 0);
const nearBottom = (e) => e.scrollHeight - e.scrollTop - e.clientHeight < 120;
const scrollBottom = (e) => { e.scrollTop = e.scrollHeight; };

/* ─────────────── typed thought queue ─────────────── */
const typeQueue = [];
let typing = false;
function enqueueType(textNode, text) {
  typeQueue.push({ textNode, text, i: 0 });
  if (typeQueue.length > 24) {          // flood guard: flush oldest
    const old = typeQueue.shift();
    old.textNode.textContent = old.text;
  }
  if (!typing) typeLoop();
}
function typeLoop() {
  typing = true;
  const t = typeQueue[0];
  if (!t) { typing = false; return; }
  const step = Math.max(2, Math.round(t.text.length / 90));
  t.i = Math.min(t.text.length, t.i + step);
  t.textNode.textContent = t.text.slice(0, t.i);
  const stream = $('stream');
  if (nearBottom(stream)) scrollBottom(stream);
  if (t.i < t.text.length) {
    setTimeout(typeLoop, 13);
  } else {
    const caret = t.textNode.parentNode.querySelector('.caret');
    if (caret) caret.remove();
    typeQueue.shift();
    setTimeout(typeLoop, 30);
  }
}

/* ─────────────── thought stream ─────────────── */
function addLine(cls) {
  const stream = $('stream');
  const stick = nearBottom(stream);
  const ln = el('div', 'ln ' + cls);
  stream.appendChild(ln);
  while (stream.children.length > 400) stream.firstChild.remove();
  if (stick) scrollBottom(stream);
  return ln;
}

function addDivider(text) {
  const ln = addLine('divider');
  ln.textContent = text;
}

function addThought(text) {
  const ln = addLine('thought');
  const span = el('span', null, '');
  ln.appendChild(span);
  ln.appendChild(el('span', 'caret'));
  enqueueType(span, text);
}

function addSys(text, level) {
  const ln = addLine('sysline' + (level ? ' ' + level : ''));
  ln.textContent = '· ' + text;
}

function addActionStart(ev) {
  const p = ev.payload;
  const ln = addLine('action start');
  ln.dataset.key = (ev.mission || 'sys') + ':' + (ev.step || ev.seq);
  const row = el('div', 'a-row');
  row.appendChild(el('span', 'a-spin'));
  row.appendChild(el('span', 'a-tool', p.tool.toUpperCase()));
  row.appendChild(el('span', 'a-label', p.label || p.tool));
  row.appendChild(el('span', 'a-status running', 'RUNNING'));
  const ms = el('span', 'a-ms', '…');
  const t0 = Date.now();
  const timer = setInterval(() => { ms.textContent = ((Date.now() - t0) / 1000).toFixed(1) + 's'; }, 100);
  ln._timer = timer;
  row.appendChild(ms);
  ln.appendChild(row);
  ln.appendChild(el('div', 'a-summary', summarizeArgs(p.args)));
  window.gridPulse && window.gridPulse(p.tool);
  markTool(p.tool, true);
}

function addActionEnd(ev) {
  const p = ev.payload;
  const key = (ev.mission || 'sys') + ':' + (ev.step || '');
  let ln = $('stream').querySelector(`[data-key="${CSS.escape(key)}"]`);
  if (!ln) { ln = addActionStart({ ...ev, payload: { ...p, tool: p.tool, label: p.label } }); }
  if (ln._timer) { clearInterval(ln._timer); ln._timer = null; }
  ln.classList.remove('start');
  ln.classList.add(p.status === 'ok' ? 'ok' : p.status);
  const spin = ln.querySelector('.a-spin'); if (spin) spin.remove();
  const st = ln.querySelector('.a-status');
  if (st) { st.textContent = p.status.toUpperCase(); st.className = 'a-status ' + p.status; }
  const ms = ln.querySelector('.a-ms');
  if (ms) ms.textContent = (p.ms / 1000).toFixed(2) + 's';
  const sum = ln.querySelector('.a-summary');
  if (sum) sum.textContent = p.summary || '';
  markTool(p.tool, false);
}

function summarizeArgs(args) {
  if (!args || !Object.keys(args).length) return '';
  return Object.entries(args).map(([k, v]) => `${k}=${v}`).join('  ').slice(0, 160);
}

function addPlan(steps, mission) {
  const ln = addLine('plan');
  ln.appendChild(el('div', 'p-head', '◈ TACTICAL PLAN'));
  const ol = el('ol');
  steps.forEach(s => ol.appendChild(el('li', null, s)));
  ln.appendChild(ol);
}

/* ─────────────── intel cards ─────────────── */
function addCard(p) {
  const intel = $('intel');
  const c = el('div', 'card');
  const kindLabel = { search: '⌁ SEARCH SWEEP', page: '▤ SOURCE DIGEST', repo: '⌂ GITHUB REPO',
    package: '▣ PACKAGE INTEL', code: '⌨ CODEBOX', answer: '✦ AGENT ANSWER',
    status: '◎ NETWORK MATRIX' }[p.kind] || p.kind.toUpperCase();
  c.appendChild(el('div', 'c-kind', kindLabel));
  const title = el('div', 'c-title');
  if (p.kind === 'repo' && p.url) {
    const a = el('a', null, p.title || p.full_name);
    a.href = p.url; a.target = '_blank'; a.rel = 'noopener';
    title.appendChild(a);
  } else {
    title.textContent = p.title || '';
  }
  c.appendChild(title);

  if (p.kind === 'search') {
    (p.items || []).slice(0, 8).forEach(r => {
      const item = el('div', 'sr');
      const a = el('a', 'sr-title', r.title);
      a.href = r.url; a.target = '_blank'; a.rel = 'noopener';
      item.appendChild(a);
      item.appendChild(el('div', 'sr-url', r.url));
      if (r.snippet) item.appendChild(el('div', 'c-snippet', r.snippet));
      const meta = el('div', 'c-meta');
      meta.appendChild(el('span', 'chiplet src-chip', r.source));
      item.appendChild(meta);
      c.appendChild(item);
    });
    if (!p.items || !p.items.length) c.appendChild(el('div', 'empty', 'no results returned'));
  }

  if (p.kind === 'page') {
    if (p.url) {
      const a = el('a', 'sr-url', p.url);
      a.href = p.url; a.target = '_blank'; a.rel = 'noopener'; a.style.display = 'block';
      a.style.marginBottom = '6px';
      c.appendChild(a);
    }
    if (p.bullets && p.bullets.length) {
      const ul = el('ul', 'c-bullets');
      p.bullets.forEach(b => ul.appendChild(el('li', null, b)));
      c.appendChild(ul);
    }
    const meta = el('div', 'c-meta');
    meta.appendChild(el('span', null, 'words ')); meta.appendChild(el('b', null, String(p.words || 0)));
    meta.appendChild(el('span', null, 'http ')); meta.appendChild(el('b', null, String(p.status || '—')));
    c.appendChild(meta);
    if (p.excerpt) {
      const ex = el('div', 'c-snippet', p.excerpt.slice(0, 400));
      ex.style.marginTop = '7px';
      c.appendChild(ex);
    }
  }

  if (p.kind === 'repo') {
    if (p.desc) c.appendChild(el('div', 'c-snippet', p.desc));
    const meta = el('div', 'c-meta');
    meta.appendChild(el('span', null, '★ ')); meta.appendChild(el('b', null, String(p.stars ?? '—')));
    meta.appendChild(el('span', null, 'forks ')); meta.appendChild(el('b', null, String(p.forks ?? '—')));
    meta.appendChild(el('span', null, 'issues ')); meta.appendChild(el('b', null, String(p.open_issues ?? '—')));
    meta.appendChild(el('span', null, 'lang ')); meta.appendChild(el('b', null, String(p.lang || '—')));
    meta.appendChild(el('span', null, 'push ')); meta.appendChild(el('b', null, String(p.updated || '—')));
    meta.appendChild(el('span', null, 'license ')); meta.appendChild(el('b', null, String(p.license || '—')));
    c.appendChild(meta);
    if (p.topics && p.topics.length) {
      const t = el('div');
      p.topics.forEach(tp => t.appendChild(el('span', 'chiplet', tp)));
      c.appendChild(t);
    }
    if (p.readme_head) {
      const pre = el('pre', null, p.readme_head.slice(0, 420));
      pre.style.cssText = 'font-family:var(--f-mono);font-size:10px;color:var(--dim);margin-top:7px;max-height:86px;overflow:hidden;white-space:pre-wrap;border-top:1px solid rgba(56,189,248,.1);padding-top:6px';
      c.appendChild(pre);
    }
  }

  if (p.kind === 'package') {
    c.appendChild(el('div', 'c-snippet', p.summary || ''));
    const meta = el('div', 'c-meta');
    const put = (k, v) => { meta.appendChild(el('span', null, k + ' ')); meta.appendChild(el('b', null, String(v))); };
    put('version', p.version); put('license', p.license);
    put('releases', p.releases_count); put('deps', p.deps_count);
    put('last upload', p.last_upload);
    if (p.registry) put('registry', p.registry);
    c.appendChild(meta);
    if (p.deps_sample && p.deps_sample.length) {
      const t = el('div');
      p.deps_sample.forEach(d => t.appendChild(el('span', 'chiplet', String(d).slice(0, 40))));
      c.appendChild(t);
    }
    if (p.homepage) {
      const a = el('a', 'sr-url', p.homepage);
      a.href = p.homepage; a.target = '_blank'; a.rel = 'noopener';
      a.style.display = 'block'; a.style.marginTop = '6px';
      c.appendChild(a);
    }
  }

  if (p.kind === 'code') {
    const badges = el('div', 'c-meta');
    badges.appendChild(el('span', 'chiplet', (p.lang || '?').toUpperCase()));
    badges.appendChild(el('span', null, 'exit '));
    badges.appendChild(el('b', null, String(p.exit ?? '—')));
    badges.appendChild(el('span', null, 'ms '));
    badges.appendChild(el('b', null, String(p.ms ?? '—')));
    c.appendChild(badges);
    if (p.stdout) { const pre = el('pre', 'stdout', p.stdout.slice(0, 3000)); c.appendChild(pre); }
    if (p.stderr) { const pre = el('pre', 'stderr', p.stderr.slice(0, 1500)); c.appendChild(pre); }
    if (!p.stdout && !p.stderr) c.appendChild(el('div', 'empty', '(no output)'));
  }

  if (p.kind === 'answer') {
    c.classList.add('answer-card');
    c.appendChild(el('div', 'c-text', p.text || ''));
  }

  if (p.kind === 'status') {
    (p.routes || []).forEach(r => {
      const row = el('div', 'route ' + r.status);
      row.appendChild(el('span', 'r-dot'));
      row.appendChild(el('span', 'r-id', r.id));
      row.appendChild(el('span', 'r-ms', r.status === 'live' ? r.ms + 'ms' : (r.detail || r.status).slice(0, 40)));
      c.appendChild(row);
    });
    const meta = el('div', 'c-meta');
    meta.appendChild(el('span', null, 'live '));
    meta.appendChild(el('b', null, String(p.live ?? 0)));
    meta.appendChild(el('span', null, 'blocked '));
    meta.appendChild(el('b', null, String(p.blocked ?? 0)));
    c.appendChild(meta);
  }

  intel.prepend(c);
  while (intel.children.length > 60) intel.lastChild.remove();
}

/* ─────────────── missions ─────────────── */
function upsertMission(id, patch) {
  const m = state.missions.get(id) || { id, goal: '', mode: state.mode, status: 'running', actions: 0 };
  Object.assign(m, patch);
  state.missions.set(id, m);
  renderMissions();
  return m;
}

function renderMissions() {
  const box = $('missions-list');
  const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 160;
  box.textContent = '';
  const arr = [...state.missions.values()].sort((a, b) =>
    (a.status === 'running' ? -1 : 1) - (b.status === 'running' ? -1 : 1));
  if (!arr.length) { box.appendChild(el('div', 'empty', '// awaiting directives…')); return; }
  for (const m of arr.slice(0, 30)) {
    const d = el('div', 'mission ' + (m.status === 'running' ? 'running' : ''));
    const head = el('div', 'm-head');
    head.appendChild(el('span', 'm-dot status-' + m.status));
    head.appendChild(el('div', 'm-goal', m.goal || m.id));
    d.appendChild(head);
    const meta = el('div', 'm-meta');
    meta.appendChild(el('span', null, (m.mode || '').toUpperCase()));
    meta.appendChild(el('span', null, m.id));
    meta.appendChild(el('span', null, m.actions ? m.actions + ' acts' : ''));
    if (m.status === 'running') {
      const btn = el('button', 'm-cancel', 'ABORT');
      btn.onclick = async () => { await fetch(`/api/missions/${m.id}/cancel`, { method: 'POST' }); };
      meta.appendChild(btn);
    } else {
      meta.appendChild(el('span', null, m.status));
    }
    d.appendChild(meta);
    box.appendChild(d);
  }
  if (stick) box.scrollTop = box.scrollHeight;
}

/* ─────────────── netmap ─────────────── */
function renderNetmap() {
  const box = $('netmap');
  box.textContent = '';
  for (const r of state.routes.values()) {
    const row = el('div', 'route ' + r.status);
    row.appendChild(el('span', 'r-dot'));
    row.appendChild(el('span', 'r-id', r.label || r.id));
    row.appendChild(el('span', 'chiplet', r.kind));
    row.appendChild(el('span', 'r-ms', r.status === 'live' ? r.ms + 'ms' :
      r.status === 'blocked' ? 'BLOCKED' : r.status));
    row.title = r.detail || r.url || '';
    box.appendChild(row);
  }
  const live = [...state.routes.values()].filter(r => r.status === 'live').length;
  $('chip-net').innerHTML = `⌁ NET · <b>${live}/${state.routes.size || '—'}</b>`;
}

/* ─────────────── tools ─────────────── */
const toolEls = new Map();
const TOOL_LABELS = {
  web_search: 'web.search — multi-provider sweep',
  fetch_page: 'web.fetch — open & extract any page',
  github_search: 'github.search — repo sweep',
  github_repo: 'github.repo — deep repo intel',
  pypi_info: 'pypi.intel — package registry',
  npm_info: 'npm.intel — package registry',
  run_code: 'codebox.run — sandboxed python/js',
  write_file: 'fs.write — workspace territory',
  read_file: 'fs.read — workspace territory',
  list_files: 'fs.list — workspace territory',
  memory_write: 'memory.write — durable notes',
  memory_recall: 'memory.recall — durable notes',
  net_probe: 'net.probe — route matrix',
};
function renderTools() {
  const box = $('tools-list');
  box.textContent = '';
  for (const [name, label] of Object.entries(TOOL_LABELS)) {
    const row = el('div', 'tool-row');
    row.dataset.tool = name;
    row.appendChild(el('span', 't-dot'));
    row.appendChild(el('span', 't-name', label));
    box.appendChild(row);
    toolEls.set(name, row);
  }
}
function markTool(tool, hot) {
  const row = toolEls.get(tool);
  if (!row) return;
  if (hot) {
    row.classList.add('hot', 'flash');
    setTimeout(() => row.classList.remove('flash'), 500);
  } else {
    setTimeout(() => row.classList.remove('hot'), 1200);
  }
}

/* ─────────────── syslog ─────────────── */
function addLog(text, level) {
  const box = $('syslog');
  const ln = el('div', 'sl' + (level ? ' ' + level : ''));
  ln.appendChild(el('span', 'sl-t', fmtTime()));
  ln.appendChild(document.createTextNode(text));
  box.appendChild(ln);
  while (box.children.length > 160) box.firstChild.remove();
  box.scrollTop = box.scrollHeight;
}

/* ─────────────── vitals ─────────────── */
function renderVitals() {
  const g = $('vitals-grid');
  g.textContent = '';
  const vital = (num, lbl) => {
    const v = el('div', 'vital');
    v.appendChild(el('div', 'v-num', String(num)));
    v.appendChild(el('div', 'v-lbl', lbl));
    return v;
  };
  const running = [...state.missions.values()].filter(m => m.status === 'running').length;
  g.appendChild(vital(running, 'ACTIVE MISSIONS'));
  g.appendChild(vital(state.missions.size, 'MISSIONS'));
  g.appendChild(vital(state.actionsTotal, 'ACTIONS'));
  g.appendChild(vital(state.eventsTotal, 'EVENTS'));
}

let lastBucket = Date.now();
function bumpSpark() {
  state.buckets[state.buckets.length - 1]++;
}
setInterval(() => {
  state.buckets.push(0); state.buckets.shift();
  drawSpark();
  renderVitals();
}, 1000);

function drawSpark() {
  const cv = $('spark');
  const ctx = cv.getContext('2d');
  const w = cv.clientWidth || 280, h = 46;
  cv.width = w * 2; cv.height = h * 2; ctx.setTransform(2, 0, 0, 2, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const max = Math.max(2, ...state.buckets);
  const bw = w / state.buckets.length;
  const accent = getComputedStyle(document.body).getPropertyValue('--accent').trim();
  state.buckets.forEach((v, i) => {
    const bh = (v / max) * (h - 8);
    ctx.fillStyle = i === state.buckets.length - 1 ? accent : accent + '66';
    ctx.fillRect(i * bw + 1, h - bh - 2, bw - 2, bh);
  });
  ctx.strokeStyle = accent + '33';
  ctx.beginPath(); ctx.moveTo(0, h - 1); ctx.lineTo(w, h - 1); ctx.stroke();
}

/* ─────────────── artifacts ─────────────── */
function addArtifact(p) {
  state.artifacts.set(p.path, p);
  renderArtifacts();
}
function renderArtifacts() {
  const box = $('artifacts');
  box.textContent = '';
  if (!state.artifacts.size) { box.appendChild(el('div', 'empty', '// no artifacts yet')); return; }
  for (const [path, a] of [...state.artifacts.entries()].reverse().slice(0, 20)) {
    const row = el('div', 'artifact');
    row.appendChild(el('span', 'a-ico', '▪'));
    row.appendChild(el('span', null, path));
    row.appendChild(el('span', 'a-size', fmtBytes(a.bytes || 0)));
    row.onclick = () => openArtifact(path);
    box.appendChild(row);
  }
}
async function openArtifact(path) {
  try {
    const r = await fetch('/api/artifact?path=' + encodeURIComponent(path));
    const data = await r.json();
    openModal(path, renderMarkdown(data.content || '(empty)'));
  } catch { openModal(path, 'failed to load'); }
}
function renderMarkdown(md) {
  let h = md.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  h = h.replace(/^### (.*)$/gm, '<h3>$1</h3>')
       .replace(/^## (.*)$/gm, '<h2>$1</h2>')
       .replace(/^# (.*)$/gm, '<h1>$1</h1>')
       .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
       .replace(/`([^`]+)`/g, '<code>$1</code>')
       .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
       .replace(/^- (.*)$/gm, '• $1');
  return h;
}

/* ─────────────── modal ─────────────── */
function openModal(title, html) {
  $('modal-title').textContent = title;
  $('modal-body').innerHTML = html;
  $('modal').classList.remove('hidden');
}
$('modal-close').onclick = () => $('modal').classList.add('hidden');
$('modal').onclick = (e) => { if (e.target === $('modal')) $('modal').classList.add('hidden'); };

/* ─────────────── voice ─────────────── */
let voiceOn = false;
function speak(text) {
  if (!voiceOn || !('speechSynthesis' in window)) return;
  try {
    const u = new SpeechSynthesisUtterance(text.replace(/★/g, 'star '));
    u.rate = 1.04; u.pitch = 0.82; u.volume = 0.95;
    const vs = speechSynthesis.getVoices();
    const pref = vs.find(v => /en[-_](GB|US)/i.test(v.lang) && /male|daniel|david|alex|google uk english male/i.test(v.name)) ||
                 vs.find(v => /en[-_]GB/i.test(v.lang)) || vs.find(v => v.lang.startsWith('en'));
    if (pref) u.voice = pref;
    speechSynthesis.speak(u);
  } catch {}
}
$('chip-voice').onclick = () => {
  voiceOn = !voiceOn;
  $('chip-voice').classList.toggle('on', voiceOn);
  $('chip-voice').innerHTML = `VOICE · <b>${voiceOn ? 'ON' : 'OFF'}</b>`;
  if (voiceOn) speak('Voice interface online. All systems nominal.');
  else if ('speechSynthesis' in window) speechSynthesis.cancel();
};

/* mic */
let rec = null;
$('mic').onclick = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { addSys('speech recognition not supported in this browser', 'warn'); return; }
  if (rec) { rec.stop(); return; }
  rec = new SR();
  rec.lang = 'en-US'; rec.interimResults = false;
  $('mic').classList.add('listening');
  rec.onresult = (e) => {
    $('cmd').value = e.results[0][0].transcript;
    launchFromInput();
  };
  rec.onend = () => { $('mic').classList.remove('listening'); rec = null; };
  rec.onerror = rec.onend;
  rec.start();
};

/* ─────────────── mode ─────────────── */
function setMode(mode) {
  state.mode = mode;
  localStorage.setItem('au-mode', mode);
  document.body.classList.toggle('mode-ultron', mode === 'ultron');
  document.body.classList.toggle('mode-jarvis', mode === 'jarvis');
  $('mode-jarvis').classList.toggle('active', mode === 'jarvis');
  $('mode-ultron').classList.toggle('active', mode === 'ultron');
  $('mode-hint').textContent = mode === 'ultron' ? 'aggressive · parallel' : 'careful · sequential';
  $('cmd-prompt').textContent = mode === 'ultron' ? 'U.L.T.R.O.N ▸' : 'J.A.R.V.I.S ▸';
}
$('mode-jarvis').onclick = () => setMode('jarvis');
$('mode-ultron').onclick = () => setMode('ultron');

/* ─────────────── command bar ─────────────── */
async function launchFromInput() {
  const goal = $('cmd').value.trim();
  if (!goal) return;
  $('cmd').value = '';
  try {
    const r = await fetch('/api/missions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, mode: state.mode }),
    });
    const data = await r.json();
    if (data.error) addSys('rejected: ' + data.error, 'warn');
  } catch (e) {
    addSys('launch failed: ' + e.message, 'error');
  }
}
$('exec').onclick = launchFromInput;
$('cmd').addEventListener('keydown', (e) => { if (e.key === 'Enter') launchFromInput(); });
$('reprobe').onclick = async () => {
  addSys('manual net-probe requested', 'info');
  await fetch('/api/netmap/probe', { method: 'POST' });
};

/* ─────────────── event router ─────────────── */
function handleEvent(ev) {
  if (typeof ev.seq === 'number') {
    if (ev.seq <= state.seq) return;   // replay overlap — already seen
    state.seq = ev.seq;
    state.eventsTotal = ev.seq;
    $('chip-events').innerHTML = `Σ <b>${ev.seq}</b>`;
  }
  bumpSpark();
  const p = ev.payload || {};
  switch (ev.type) {
    case 'mission.created':
      upsertMission(p.id, { goal: p.goal, mode: p.mode, status: 'running' });
      addDivider('MISSION ' + p.id + ' — ' + p.mode.toUpperCase() + ' MODE');
      addSys(`mission ${p.id} created · core=${p.core} · "${p.goal.slice(0, 70)}"`);
      break;
    case 'mission.start':
      break;
    case 'intent':
      addLine('intent').textContent = `⟨intent: ${p.intent} · core: ${p.core}⟩`;
      break;
    case 'plan':
      addPlan(p.steps, ev.mission);
      break;
    case 'thought':
      addThought(p.text);
      break;
    case 'action.start':
      addActionStart(ev);
      break;
    case 'action.end':
      addActionEnd(ev);
      state.actionsTotal++;
      if (ev.mission) {
        const m = state.missions.get(ev.mission);
        if (m) { m.actions = (m.actions || 0) + 1; renderMissions(); }
      }
      break;
    case 'action.batch':
      addSys(`⚡ ULTRON parallel batch: ${p.count} simultaneous actions (${p.label || ''})`, 'info');
      break;
    case 'card':
      addCard(p);
      break;
    case 'artifact':
      addArtifact(p);
      addSys(`artifact written: ${p.path} (${fmtBytes(p.bytes || 0)})`);
      break;
    case 'mission.end':
      upsertMission(p.id, { status: p.status, actions: p.actions });
      const ln = addLine('mission-end ' + p.status);
      ln.textContent = `[ ${p.status.toUpperCase()} · ${(p.ms / 1000).toFixed(1)}s · ${p.actions || 0} actions · ${p.summary || ''} ]`;
      if (p.status === 'done') {
        addLog(`mission ${p.id} complete: ${p.summary || ''}`, 'info');
      } else {
        addLog(`mission ${p.id} ${p.status}: ${p.summary || ''}`, p.status === 'failed' ? 'error' : 'warn');
      }
      break;
    case 'net.route':
      state.routes.set(p.id, p);
      renderNetmap();
      break;
    case 'sys.note':
      addSys(p.text, p.level);
      addLog(p.text, p.level);
      if (/net-probe complete/.test(p.text)) speak(p.text);
      break;
    case 'speech':
      speak(p.text);
      break;
    case 'error':
      addSys(p.text, 'error');
      addLog(p.text, 'error');
      break;
  }
}

/* ─────────────── websocket ─────────────── */
let wsBackoff = 1000;
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  state.ws = ws;
  ws.onopen = () => { /* hello arrives next */ };
  ws.onmessage = (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.type === 'hello') {
      state.core = msg.payload.core;
      state.neural = msg.payload.neural;
      $('chip-core').innerHTML = `◈ CORE · <b>${state.neural ? state.core.toUpperCase() : 'HEURISTIC'}</b>`;
      ws.send(JSON.stringify({ after: state.seq }));
      wsBackoff = 1000;
      $('chip-ws').innerHTML = '◉ LINK · <b>LIVE</b>';
      addSys(`telemetry link established · core: ${state.core}`, 'info');
      return;
    }
    if (msg.type === 'ping') return;
    handleEvent(msg);
  };
  ws.onclose = () => {
    $('chip-ws').innerHTML = '◉ LINK · <b style="color:var(--red)">DOWN</b>';
    setTimeout(connect, wsBackoff);
    wsBackoff = Math.min(wsBackoff * 1.6, 10000);
  };
  ws.onerror = () => ws.close();
}

/* ─────────────── initial state ─────────────── */
async function loadState() {
  try {
    const r = await fetch('/api/state');
    const s = await r.json();
    state.neural = s.core.kind === 'neural';
    state.core = s.core.provider;
    $('chip-core').innerHTML = `◈ CORE · <b>${s.core.kind.toUpperCase()}</b>`;
    (s.netmap || []).forEach(rt => state.routes.set(rt.id, rt));
    renderNetmap();
    (s.missions || []).slice().reverse().forEach(m => {
      state.missions.set(m.id, { goal: m.goal, mode: m.mode, status: m.status, actions: m.steps_done || 0 });
    });
    renderMissions();
    (s.artifacts || []).forEach(a => state.artifacts.set(a.path, a));
    renderArtifacts();
    state.actionsTotal = s.stats?.actions_total || 0;
    state.eventsTotal = s.stats?.events_total || 0;
    renderVitals();
  } catch (e) {
    addSys('state fetch failed — retrying via ws replay', 'warn');
  }
}

/* ─────────────── boot sequence ─────────────── */
const BOOT_LINES = [
  ['POST · power-on self test', 'ok'],
  ['memory sectors ......... OK', 'ok'],
  ['heuristic core ......... ONLINE', 'ok'],
  ['tool registry .......... 13 tools armed', 'ok'],
  ['workspace territory .... data/workspace', 'ok'],
  ['codebox sandbox ........ cpu/ram/time limits set', 'ok'],
  ['net-probe .............. mapping routes…', 'warn'],
  ['spacegrid telemetry .... live', 'ok'],
  ['', ''],
  ['ALL SYSTEMS NOMINAL — awaiting operator directive', 'key'],
];
async function bootSequence() {
  const lines = $('boot-lines');
  const status = $('boot-status');
  const fast = sessionStorage.getItem('au-booted') === '1';
  for (const [text, cls] of BOOT_LINES) {
    const ln = el('div', cls);
    lines.appendChild(ln);
    if (fast) { ln.textContent = text; continue; }
    for (let i = 0; i <= text.length; i += Math.max(2, Math.round(text.length / 26))) {
      ln.textContent = text.slice(0, i);
      await new Promise(r => setTimeout(r, 9));
    }
    ln.textContent = text;
  }
  status.textContent = fast ? '' : '▌ GRID ONLINE';
  sessionStorage.setItem('au-booted', '1');
  await new Promise(r => setTimeout(r, fast ? 60 : 650));
  $('boot').classList.add('done');
  state.booted = true;
  setTimeout(() => $('boot').remove(), 800);
}
$('boot').onclick = () => { sessionStorage.setItem('au-booted', '1'); $('boot').classList.add('done'); setTimeout(() => $('boot').remove(), 700); };

/* ─────────────── init ─────────────── */
setMode(state.mode);
renderTools();
renderMissions();
renderArtifacts();
loadState();
connect();
bootSequence();
drawSpark();

})();
