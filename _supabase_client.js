// ─────────────────────────────────────────────────────────────────────────────
//  Supabase sync
//
//  The dashboard keeps working exactly as before if this is unconfigured or the
//  network is down: localStorage is always the source of truth for the UI, and
//  Supabase is a background sync peer. Writes are debounced into an outbox and
//  merged with last-write-wins per item, keyed on updated_at.
// ─────────────────────────────────────────────────────────────────────────────

const SYNC = {
  // Filled in at build time from supabase-config.json, which is git-ignored so
  // the key stays out of repository history. Blank here means local-only mode.
  url: '__SYNC_URL__',
  anonKey: '__SYNC_KEY__',

  table: { rules: 'rule_state', insp: 'inspection_state', team: 'team_members', meta: 'app_meta' },

  enabled: false,
  online: false,
  status: 'local',          // local | connecting | synced | syncing | offline | error
  lastError: null,
  lastPulledAt: null,
  lastPushedAt: null,

  _outbox: new Map(),       // "table:id" -> row
  _synced: new Map(),       // "table:id" -> updated_at last pushed
  _flushTimer: null,
  _pulling: false,
  _pushing: false
};

function syncConfig() {
  const u = SYNC.url.trim();
  const k = SYNC.anonKey.trim();
  // Accept any http(s) endpoint with a key: covers *.supabase.co, self-hosted
  // stacks and reverse proxies. Blank values simply keep the app local-only.
  let ok = false;
  try {
    const parsed = new URL(u);
    ok = (parsed.protocol === 'http:' || parsed.protocol === 'https:') && k.length > 0;
  } catch (e) { ok = false; }
  SYNC.enabled = ok;
  return ok;
}

// ── HTTP ─────────────────────────────────────────────────────────────────────
// Supabase's newer publishable keys (sb_publishable_...) are not JWTs, while
// the legacy anon key is. Deployments differ in whether the gateway wants the
// key echoed as a bearer token, so send both forms first and fall back to the
// apikey header alone if the gateway rejects the token.
let _authMode = 'bearer';   // 'bearer' | 'apikey-only'

function sbHeaders(prefer) {
  const key = SYNC.anonKey.trim();
  const h = { apikey: key, 'Content-Type': 'application/json' };
  if (_authMode === 'bearer') h.Authorization = 'Bearer ' + key;
  if (prefer && Object.keys(prefer).length) {
    h.Prefer = Object.entries(prefer).map(([k, v]) => `${k}=${v}`).join(', ');
  }
  return h;
}

async function sbFetch(path, opts = {}) {
  const base = SYNC.url.trim().replace(/\/+$/, '');
  const send = mode => {
    const saved = _authMode;
    _authMode = mode;
    const h = sbHeaders(opts.prefer);
    _authMode = saved;
    return fetch(base + '/rest/v1/' + path, {
      method: opts.method || 'GET',
      headers: h,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal
    });
  };

  let res = await send(_authMode);
  // 401/403 with a bearer attempt -> retry once with apikey only
  if ((res.status === 401 || res.status === 403) && _authMode === 'bearer' && SYNC._triedApikeyOnly !== true) {
    SYNC._triedApikeyOnly = true;
    _authMode = 'apikey-only';
    res = await send('apikey-only');
  }

  if (!res.ok) {
    let detail = res.status + ' ' + res.statusText;
    try { const j = await res.json(); if (j && j.message) detail += ' — ' + j.message; } catch (e) {}
    throw new Error(detail);
  }
  if (res.status === 204 || opts.method === 'DELETE') return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

// ── status plumbing ──────────────────────────────────────────────────────────
function setSyncStatus(s, detail) {
  SYNC.status = s;
  const dot = $('sync-dot');
  const label = $('sync-label');
  const pill = $('sync-pill');
  if (!dot || !label || !pill) return;
  const map = {
    local:     ['var(--muted)',  'Local only'],
    connecting:['var(--gold)',   'Connecting…'],
    synced:    ['var(--green)',  'Synced'],
    syncing:   ['var(--gold)',   'Syncing…'],
    offline:   ['var(--gold)',   'Offline — saved locally'],
    error:     ['var(--red)',    'Sync error — saved locally']
  };
  const [color, text] = map[s] || map.local;
  dot.style.background = color;
  dot.style.boxShadow = '0 0 0 3px color-mix(in srgb, ' + color + ' 18%, transparent)';
  label.textContent = detail ? text + ' · ' + detail : text;
  pill.title = SYNC.enabled
    ? 'Supabase: ' + SYNC.url + '\nLast pulled: ' + (SYNC.lastPulledAt || 'never') +
      '\nLast pushed: ' + (SYNC.lastPushedAt || 'never') +
      (SYNC.lastError ? '\nLast error: ' + SYNC.lastError : '')
    : 'Supabase is not configured — progress is stored in this browser only.';
}

// ── local state helpers ──────────────────────────────────────────────────────
function nowIso() { return new Date().toISOString(); }

function touchLocal(item) {
  item.completed_at = item.completed ? (item.completed_at || nowIso()) : null;
  item.updated_at = nowIso();
}

// A row the user has never changed must sort as infinitely old, otherwise a
// default item stamped "now" by a boot that then failed will out-rank real team
// progress and win the last-write-wins merge.
const EPOCH = '1970-01-01T00:00:00.000Z';

function stateRows(arr, isTI) {
  const idKey = isTI ? 'item_id' : 'rule_id';
  return arr.map(x => {
    // Stamp once, then keep it. Generating a fresh timestamp on every call
    // would make every untouched item look dirty and re-push all 239 rows
    // on every keystroke. The stamp is persisted by the caller's save().
    if (!x.updated_at) x.updated_at = isUntouched(x) ? EPOCH : nowIso();
    return {
      [idKey]: x.id,
      completed: !!x.completed,
      note: x.note || '',
      completed_at: x.completed_at || null,
      updated_at: x.updated_at
    };
  });
}

function newerThan(a, b) {
  if (!a) return false;
  if (!b) return true;
  const ta = Date.parse(a) || 0, tb = Date.parse(b) || 0;
  if (ta !== tb) return ta > tb;
  return true; // identical timestamps: prefer incoming so a pull converges
}

// An item the user has never actually changed must always defer to the server.
// Without this, a local item that merely carries a timestamp -- e.g. stamped by
// a sync attempt that then failed -- would out-rank real team progress and the
// user would be left looking at stale, empty state.
function isUntouched(item) {
  return !item.completed && !(item.note || '').trim();
}

// ── pull ─────────────────────────────────────────────────────────────────────
async function syncPull() {
  if (!SYNC.enabled || SYNC._pulling) return false;
  SYNC._pulling = true;
  setSyncStatus('connecting');
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 12000);
  try {
    const [rbRows, tiRows, teamRows, metaRows] = await Promise.all([
      sbFetch(SYNC.table.rules + '?select=*',  { signal: ctrl.signal }),
      sbFetch(SYNC.table.insp  + '?select=*',  { signal: ctrl.signal }),
      sbFetch(SYNC.table.team  + '?select=*&order=created_at', { signal: ctrl.signal }),
      sbFetch(SYNC.table.meta  + '?select=*',  { signal: ctrl.signal })
    ]);

    let changed = false;

    // Rulebook + inspection: last-write-wins per item.
    const merge = (arr, rows, isTI) => {
      const idKey = isTI ? 'item_id' : 'rule_id';
      const byId = new Map((rows || []).map(r => [r[idKey], r]));
      for (const item of arr) {
        const r = byId.get(item.id);
        if (!r) continue;
        if (isUntouched(item) || newerThan(r.updated_at, item.updated_at)) {
          item.completed = !!r.completed;
          item.note = r.note || '';
          item.completed_at = r.completed_at || null;
          item.updated_at = r.updated_at;
          changed = true;
        }
      }
    };
    merge(rules, rbRows, false);
    merge(inspection, tiRows, true);

    // Team: the server is authoritative for membership; the local list is a cache.
    if (Array.isArray(teamRows) && teamRows.length !== team.length) {
      team = teamRows.map(m => ({ id: m.id, name: m.name, role: m.role, created_at: m.created_at }));
      changed = true;
    }

    // Meta: adopt the newest last-saved stamp so the UI reads truthfully.
    const meta = new Map((metaRows || []).map(m => [m.key, m.value]));
    const remoteSaved = meta.get('last_saved');
    if (remoteSaved && remoteSaved.at && (!lastSavedAt || new Date(remoteSaved.at) > new Date(lastSavedAt))) {
      lastSavedAt = remoteSaved.at;
    }

    // Reconcile the outbox against what the server now reports. A queued write
    // that is no newer than the server has already been superseded, so drop it;
    // a genuinely newer offline edit is kept and will still be pushed.
    for (const [table, arr, remote] of [
           [SYNC.table.rules, rules, rbRows],
           [SYNC.table.insp, inspection, tiRows]]) {
      const byId = new Map((remote || []).map(r => [rowKey(r), r]));
      for (const it of arr) {
        const key = table + ':' + it.id;
        if (it.updated_at) SYNC._synced.set(key, it.updated_at);
        const pending = SYNC._outbox.get(key);
        const r = byId.get(it.id);
        if (pending && r && Date.parse(pending.updated_at || 0) <= Date.parse(r.updated_at || 0)) {
          SYNC._outbox.delete(key);
        }
      }
    }

    SYNC.lastPulledAt = nowIso();
    SYNC.lastError = null;
    setSyncStatus('synced');
    if (changed) {
      save();
      initFilters();
      updateDashboard();
      if (currentPage === 'rulebook') renderRulebook();
      if (currentPage === 'inspection') renderInspection();
      if (currentPage === 'team') renderTeam();
    }
    return changed;
  } catch (e) {
    SYNC.lastError = e.message || String(e);
    setSyncStatus(navigator.onLine ? 'error' : 'offline');
    return false;
  } finally {
    clearTimeout(timer);
    SYNC._pulling = false;
  }
}

// ── push ─────────────────────────────────────────────────────────────────────
function rowKey(row) {
  return row.rule_id || row.item_id || row.key || row.id;
}

function queueRow(table, rowOrRows) {
  const rows = Array.isArray(rowOrRows) ? rowOrRows : [rowOrRows];
  for (const row of rows) {
    if (!row) continue;
    const id = rowKey(row);
    if (id == null) continue;
    const key = table + ':' + id;
    const existing = SYNC._outbox.get(key);
    if (existing) Object.assign(existing, row);
    else SYNC._outbox.set(key, row);
  }
  scheduleFlush();
}

// Only queue rows whose updated_at differs from what the server last accepted,
// so a single checkbox tick sends one row instead of all 239.
function queueChanged(table, rows) {
  const dirty = rows.filter(r => SYNC._synced.get(table + ':' + rowKey(r)) !== r.updated_at);
  if (dirty.length) queueRow(table, dirty);
  return dirty.length;
}

function scheduleFlush(delay) {
  if (!SYNC.enabled) return;
  clearTimeout(SYNC._flushTimer);
  SYNC._flushTimer = setTimeout(flushOutbox, delay == null ? 900 : delay);
}

async function flushOutbox() {
  if (!SYNC.enabled || SYNC._pushing || !SYNC._outbox.size) return;
  if (!navigator.onLine) { setSyncStatus('offline'); return; }
  SYNC._pushing = true;
  setSyncStatus('syncing');
  const batch = [...SYNC._outbox.entries()];
  try {
    // group by table so each becomes a single multi-row upsert
    const byTable = new Map();
    for (const [key, row] of batch) {
      const table = key.split(':')[0];
      if (!byTable.has(table)) byTable.set(table, []);
      byTable.get(table).push(row);
    }
    for (const [table, rows] of byTable) {
      await sbFetch(table, {
        method: 'POST',
        prefer: { 'resolution': 'merge-duplicates', 'return': 'minimal' },
        body: rows
      });
    }
    for (const [key, row] of batch) {
      SYNC._outbox.delete(key);
      if (row && row.updated_at) SYNC._synced.set(key, row.updated_at);
    }
    SYNC.lastPushedAt = nowIso();
    SYNC.lastError = null;
    setSyncStatus('synced');
  } catch (e) {
    SYNC.lastError = e.message || String(e);
    setSyncStatus(navigator.onLine ? 'error' : 'offline');
    // keep the batch queued; the next trigger retries it
  } finally {
    SYNC._pushing = false;
    if (SYNC._outbox.size) scheduleFlush(5000);
  }
}

// ── public entry points used by the app ──────────────────────────────────────
function syncOnSave() {
  if (!syncConfig()) { setSyncStatus('local'); return; }
  const stamp = { at: lastSavedAt || nowIso() };
  queueRow(SYNC.table.meta, { key: 'last_saved', value: stamp, updated_at: nowIso() });
  queueChanged(SYNC.table.rules, stateRows(rules, false));
  queueChanged(SYNC.table.insp,  stateRows(inspection, true));
}

function syncOnTeamChange() {
  if (!syncConfig()) return;
  sbFetch(SYNC.table.team, { method: 'POST', body: team.map(m => ({ id: m.id, name: m.name, role: m.role })),
                              prefer: { 'resolution': 'merge-duplicates', 'return': 'minimal' } })
    .then(() => { SYNC.lastPushedAt = nowIso(); setSyncStatus('synced'); })
    .catch(e => { SYNC.lastError = e.message; setSyncStatus('error'); });
}

async function syncOnTeamRemove(id) {
  if (!syncConfig()) return;
  try { await sbFetch(SYNC.table.team + '?id=eq.' + encodeURIComponent(id), { method: 'DELETE' }); }
  catch (e) { SYNC.lastError = e.message; }
}

// stateRows() stamps updated_at on items that have never been touched. Those
// stamps need to reach localStorage or a reload would re-stamp them and make
// every row look dirty again. Write directly so we do not re-enter save().
function persistStamps() {
  try {
    localStorage.setItem(LS.rules, JSON.stringify(rules));
    localStorage.setItem(LS.insp, JSON.stringify(inspection));
  } catch (e) {}
}

async function syncInit() {
  if (!syncConfig()) { setSyncStatus('local'); return; }
  setSyncStatus('connecting');
  await syncPull();
  // Push anything this browser holds that the server has never seen.
  syncOnSave();
  persistStamps();
}

function syncRetry() {
  if (!syncConfig()) return;
  syncPull().then(() => flushOutbox());
}
