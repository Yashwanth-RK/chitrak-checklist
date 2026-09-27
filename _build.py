# -*- coding: utf-8 -*-
"""Generates the replacement <script> block for the Chitrak dashboard."""
import io, json, os
from _data_rules import RULES
from _data_ti import INSPECTION

RULES_JS = json.dumps(RULES, ensure_ascii=False, indent=2)
TI_JS = json.dumps(INSPECTION, ensure_ascii=False, indent=2)

JS_TEMPLATE = r'''<script>
// ─────────────────────────────────────────────────────────────────────────────
//  CHITRAK — Rulebook & Technical Inspection Control
//  Rule data transcribed from the official SIEP E-Bike Challenge documents:
//    · Rulebook-V-1.0.pdf  (last updated 25 Feb 2024)
//    · TI SHEET.pdf        (SIEP E-Bike Challenge 2025)
//  The rulebook remains the authoritative source; this is a tracking interface.
// ─────────────────────────────────────────────────────────────────────────────

__SUPABASE__

const RULES_SEED = __RULES__;

const INSPECTION_SEED = __TI__;

const SECTIONS = ['All', ...new Set(RULES_SEED.map(r => r.section))];
const TI_SECTIONS = ['All', ...new Set(INSPECTION_SEED.map(i => i.section))];

// ── STATE ────────────────────────────────────────────────────────────────────
let rules = [];
let inspection = [];
let team = [];
let currentPage = 'dashboard';
let collapsedSections = new Set();
let expandedItems = new Set();
let noteEditing = new Set();
let lastSavedAt = null;
let commandIndex = 0;
let commandMatches = [];
let focusIndex = -1;

const LS = {
  rules: 'ck_rules', insp: 'ck_insp', team: 'ck_team',
  meta: 'ck_meta', sidebar: 'ck_sidebar_collapsed'
};

// ── UTILITIES ────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// scrollIntoView is not implemented in every environment (e.g. test DOMs)
function scrollTo(el, block = 'nearest') {
  if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block });
}

function uid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

function progress(items) {
  const total = items.length;
  const done = items.filter(i => i.completed).length;
  return { done, total, pct: total ? Math.round(done / total * 100) : 0 };
}

const CIRC = 2 * Math.PI * 34;

// Colour ramp for a completion percentage: orange → amber → green
function pctColor(pct) {
  if (pct >= 100) return 'var(--green)';
  if (pct >= 60) return 'var(--gold)';
  if (pct >= 25) return 'var(--orange)';
  return 'var(--red)';
}

function pctLabel(pct) {
  if (pct >= 100) return 'Complete';
  if (pct >= 75) return 'Near ready';
  if (pct >= 40) return 'In progress';
  if (pct > 0) return 'Early stage';
  return 'Not started';
}

function showToast(message) {
  const el = $('toast');
  if (!el) return;
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => el.classList.remove('show'), 1900);
}

// ── PERSISTENCE ──────────────────────────────────────────────────────────────
function hydrate(seed, saved) {
  const byId = new Map((saved || []).map(x => [x.id, x]));
  return seed.map(r => {
    const s = byId.get(r.id);
    return {
      ...r,
      completed: s ? !!s.completed : false,
      note: s && typeof s.note === 'string' ? s.note : '',
      completed_at: s ? s.completed_at || null : null,
      updated_at: s ? s.updated_at || null : null
    };
  });
}

function save() {
  try {
    localStorage.setItem(LS.rules, JSON.stringify(rules));
    localStorage.setItem(LS.insp, JSON.stringify(inspection));
    localStorage.setItem(LS.team, JSON.stringify(team));
    touchSave();
    if (typeof syncOnSave === 'function') syncOnSave();
  } catch (e) {
    showToast('Could not save — storage may be full');
  }
}

function touchSave() {
  lastSavedAt = new Date().toISOString();
  try { localStorage.setItem(LS.meta, JSON.stringify({ lastSavedAt })); } catch (e) {}
  updateLastSaved();
}

function load() {
  try {
    const sr = localStorage.getItem(LS.rules);
    const si = localStorage.getItem(LS.insp);
    const st = localStorage.getItem(LS.team);
    const sm = localStorage.getItem(LS.meta);
    if (sm) lastSavedAt = JSON.parse(sm).lastSavedAt || null;
    rules = hydrate(RULES_SEED, sr ? JSON.parse(sr) : null);
    inspection = hydrate(INSPECTION_SEED, si ? JSON.parse(si) : null);
    team = st ? JSON.parse(st) : [];
  } catch (e) {
    rules = hydrate(RULES_SEED, null);
    inspection = hydrate(INSPECTION_SEED, null);
    team = [];
  }
}

function updateLastSaved() {
  const el = $('last-saved');
  if (!el) return;
  if (!lastSavedAt) { el.textContent = 'Updated just now'; return; }
  const mins = Math.max(0, Math.floor((Date.now() - new Date(lastSavedAt).getTime()) / 60000));
  el.textContent = mins === 0 ? 'Updated just now'
    : mins === 1 ? 'Updated 1 min ago'
    : `Updated ${mins} min ago`;
}

// ── NAVIGATION ───────────────────────────────────────────────────────────────
function nav(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const target = $('page-' + page);
  if (!target) return;
  target.classList.add('active');
  $('nav-' + page).classList.add('active');
  currentPage = page;
  focusIndex = -1;
  // Release any focused field on the page we are leaving, otherwise a search box
  // keeps DOM focus and single-key shortcuts get treated as typing.
  if (document.activeElement && document.activeElement !== document.body
      && typeof document.activeElement.blur === 'function') document.activeElement.blur();
  $('main').scrollTop = 0;
  closeCommandPalette();
  closeShortcuts();
  if (page === 'dashboard') updateDashboard();
  if (page === 'rulebook') renderRulebook();
  if (page === 'inspection') renderInspection();
  if (page === 'team') renderTeam();
  syncQuickChips('rb', getStatusValue('rb-status'));
  syncQuickChips('ti', getStatusValue('ti-status'));
}

function toggleSidebar() {
  const collapsed = document.body.classList.toggle('sidebar-collapsed');
  try { localStorage.setItem(LS.sidebar, collapsed ? '1' : '0'); } catch (e) {}
}

// ── FILTER PLUMBING ──────────────────────────────────────────────────────────
function initFilters() {
  const rb = $('rb-filter');
  if (rb) rb.innerHTML = SECTIONS.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
  const ti = $('ti-filter');
  if (ti) ti.innerHTML = TI_SECTIONS.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
}

function setStatusFilter(id, value) { const el = $(id); if (el) el.value = value; }
function getStatusValue(id) { const el = $(id); return el ? el.value : 'all'; }

function setQuickStatus(prefix, value, btn) {
  setStatusFilter(prefix + '-status', value);
  syncQuickChips(prefix, value, btn);
  prefix === 'rb' ? renderRulebook() : renderInspection();
}

function syncQuickChips(prefix, value, explicit) {
  const root = $('page-' + (prefix === 'rb' ? 'rulebook' : 'inspection'));
  if (!root) return;
  const buttons = [...root.querySelectorAll('.filter-chip[data-status]')];
  buttons.forEach(b => b.classList.remove('active'));
  if (explicit) { explicit.classList.add('active'); return; }
  const labels = { all: 'All', pending: 'Pending', done: prefix === 'ti' ? 'Cleared' : 'Completed' };
  const hit = buttons.find(b => b.textContent.trim() === labels[value]);
  if (hit) hit.classList.add('active');
}

function clearSearch(prefix) {
  const el = $(prefix + '-search');
  if (el) el.value = '';
  prefix === 'rb' ? renderRulebook() : renderInspection();
  if (el) el.focus();
}

function toggleSection(encoded) {
  const key = decodeURIComponent(encoded);
  if (collapsedSections.has(key)) collapsedSections.delete(key);
  else collapsedSections.add(key);
  key.startsWith('rb::') ? renderRulebook() : renderInspection();
}

function setAllSections(prefix, open) {
  const arr = prefix === 'rb' ? rules : inspection;
  [...new Set(arr.map(x => x.section))].forEach(s => {
    const key = prefix + '::' + s;
    if (open) collapsedSections.delete(key); else collapsedSections.add(key);
  });
  prefix === 'rb' ? renderRulebook() : renderInspection();
}

// ── FILTERING ────────────────────────────────────────────────────────────────
function matches(item, isTI, q, sec, status) {
  if (sec !== 'All' && item.section !== sec) return false;
  if (status === 'done' && !item.completed) return false;
  if (status === 'pending' && item.completed) return false;
  if (!q) return true;
  // Search rule/number code, title, official text, subsection and team note.
  return [item.rule_code, item.item_number, item.title, item.description,
          item.subsection, item.note]
    .some(f => f && String(f).toLowerCase().includes(q));
}

function groupBy(arr, keyFn) {
  const out = new Map();
  for (const it of arr) {
    const k = keyFn(it);
    if (!out.has(k)) out.set(k, []);
    out.get(k).push(it);
  }
  return out;
}

// ── ITEM RENDERING ───────────────────────────────────────────────────────────
function renderItem(item, isTI) {
  const code = isTI ? item.item_number : item.rule_code;
  const open = expandedItems.has(item.id);
  const editing = noteEditing.has(item.id);

  let detail = '';
  if (open) {
    const desc = item.description
      ? `<div class="cl-desc">${esc(item.description)}</div>`
      : `<div class="cl-placeholder">Official rule text not available in the supplied document. Add it manually as a note.</div>`;

    const note = editing
      ? `<textarea class="cl-note-area" id="note-${item.id}" rows="2" placeholder="Add a short note, e.g. &quot;BMS installed and tested — Rahul, 26 Sep&quot;">${esc(item.note || '')}</textarea>
         <div class="cl-btn-row">
           <button class="btn btn-orange" onclick="saveNote('${item.id}', ${isTI})">Save note</button>
           <button class="btn btn-ghost" onclick="cancelNote('${item.id}')">Cancel</button>
         </div>`
      : `<div class="cl-note-wrap">
           ${item.note ? `<div class="cl-note-display">${esc(item.note)}</div>` : ''}
           <button class="btn btn-ghost" onclick="editNote('${item.id}')">${item.note ? 'Edit note' : '+ Note'}</button>
         </div>`;

    const meta = `<div class="cl-meta">
        <span>${isTI ? 'Inspection item' : 'Rule'} <b>${esc(code)}</b></span>
        <span>${esc(item.section)}</span>
        <span>${esc(item.subsection)}</span>
      </div>`;

    detail = `<div class="cl-detail" id="detail-${item.id}">${desc}${meta}${note}</div>`;
  }

  return `<div class="cl-item${item.completed ? ' done' : ''}" id="item-${item.id}" data-item="${item.id}">
    <div class="cl-row">
      <div class="cl-check${item.completed ? ' done' : ''}" role="checkbox" tabindex="0"
           aria-checked="${item.completed}" aria-label="Mark ${esc(item.title)} ${item.completed ? 'incomplete' : 'complete'}"
           onclick="toggleItem('${item.id}', ${isTI})"
           onkeydown="if(event.key===' '||event.key==='Enter'){event.preventDefault();toggleItem('${item.id}', ${isTI})}">
        ${item.completed ? '<svg width="10" height="8" viewBox="0 0 9 7" fill="none"><path d="M1 3.5L3.5 6 8 1" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' : ''}
      </div>
      <div class="cl-body" onclick="toggleExpand('${item.id}', ${isTI})">
        <div class="cl-code">${esc(code)}</div>
        <div class="cl-title">${esc(item.title)}</div>
      </div>
      ${item.note ? '<div class="note-dot" title="Has note"></div>' : ''}
      <button class="cl-expand${open ? ' open' : ''}" onclick="toggleExpand('${item.id}', ${isTI})"
              aria-label="${open ? 'Collapse' : 'Expand'} ${esc(item.title)}" aria-expanded="${open}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9 18l6-6-6-6"/></svg>
      </button>
    </div>
    ${detail}
  </div>`;
}

function sectionHeader(label, kind, done, total, isTI) {
  const key = kind + '::' + label;
  const collapsed = collapsedSections.has(key);
  const pct = total ? Math.round(done / total * 100) : 0;
  const encoded = encodeURIComponent(key);
  return `<div class="sec-hd" data-section="${esc(label)}">
    <button class="sec-toggle${collapsed ? ' collapsed' : ''}" onclick="toggleSection('${encoded}')"
            aria-expanded="${!collapsed}" aria-label="Toggle ${esc(label)} section">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9 18l6-6-6-6"/></svg>
    </button>
    <button class="sec-name${isTI ? ' ti' : ''}" onclick="toggleSection('${encoded}')">${esc(label)}</button>
    <span class="sec-meter" aria-hidden="true"><i style="width:${pct}%;background:${pctColor(pct)}"></i></span>
    <span class="sec-ct">${done}/${total}</span>
    <button class="sec-bulk" onclick="toggleSectionItems('${esc(label)}', ${isTI})"
            title="Toggle all items in this section">${done === total && total ? 'Reset' : 'Fill'}</button>
  </div>`;
}

// ── RULEBOOK VIEW ────────────────────────────────────────────────────────────
function renderRulebook() {
  const input = $('rb-search');
  const q = (input ? input.value : '').toLowerCase().trim();
  const sec = $('rb-filter').value;
  const status = getStatusValue('rb-status');
  $('rb-clear').style.display = q ? 'inline' : 'none';

  const filtered = rules.filter(r => matches(r, false, q, sec, status));
  const rb = progress(rules);

  updateChecklistBars();
  $('rb-count').textContent = filtered.length === rules.length
    ? '' : `${filtered.length} of ${rules.length} shown`;

  const list = $('rb-list');
  if (!filtered.length) {
    list.innerHTML = `<div class="empty-state"><strong>No matching rules</strong>
      Try a different search term, section or status filter.</div>`;
    return;
  }

  // Group section → subsection, preserving rulebook order
  const bySection = groupBy(filtered, r => r.section);
  let html = '';
  let first = true;
  for (const [section, items] of bySection) {
    const sp = progress(items);
    html += `<section class="sec-block"${first ? '' : ' style="margin-top:20px"'}>
      ${sectionHeader(section, 'rb', sp.done, sp.total, false)}`;
    first = false;
    if (!collapsedSections.has('rb::' + section)) {
      const bySub = groupBy(items, r => r.subsection);
      for (const [sub, subItems] of bySub) {
        if (sub) html += `<div class="subsec-name">${esc(sub)}</div>`;
        html += subItems.map(r => renderItem(r, false)).join('');
      }
    }
    html += '</section>';
  }
  const keepFocus = focusedItemId();
  list.innerHTML = html;
  restoreFocusedItem(keepFocus);
}

// ── INSPECTION VIEW ──────────────────────────────────────────────────────────
function renderInspection() {
  const input = $('ti-search');
  const q = (input ? input.value : '').toLowerCase().trim();
  const sec = $('ti-filter').value;
  const status = getStatusValue('ti-status');
  $('ti-clear').style.display = q ? 'inline' : 'none';

  const filtered = inspection.filter(i => matches(i, true, q, sec, status));
  const ti = progress(inspection);

  updateChecklistBars();
  $('ti-count').textContent = filtered.length === inspection.length
    ? '' : `${filtered.length} of ${inspection.length} shown`;

  const list = $('ti-list');
  if (!filtered.length) {
    list.innerHTML = `<div class="empty-state"><strong>No matching inspection items</strong>
      Try a different search term, section or status filter.</div>`;
    return;
  }

  const bySection = groupBy(filtered, i => i.section);
  let html = '';
  let first = true;
  for (const [section, items] of bySection) {
    const sp = progress(items);
    html += `<section class="sec-block"${first ? '' : ' style="margin-top:20px"'}>
      ${sectionHeader(section, 'ti', sp.done, sp.total, true)}`;
    first = false;
    if (!collapsedSections.has('ti::' + section)) {
      html += items.map(i => renderItem(i, true)).join('');
    }
    html += '</section>';
  }
  const keepFocus = focusedItemId();
  list.innerHTML = html;
  restoreFocusedItem(keepFocus);
}

// ── ITEM ACTIONS ─────────────────────────────────────────────────────────────
function refresh(prefix) {
  prefix === 'rb' ? renderRulebook() : renderInspection();
  updateDashboard();
}

function toggleItem(id, isTI) {
  const arr = isTI ? inspection : rules;
  const item = arr.find(x => x.id === id);
  if (!item) return;
  item.completed = !item.completed;
  touchLocal(item);
  save();
  refresh(isTI ? 'ti' : 'rb');
  showToast(item.completed ? `✓ ${item.rule_code || item.item_number} complete` : `↺ ${item.rule_code || item.item_number} back to pending`);
}

function toggleSectionItems(section, isTI) {
  const arr = isTI ? inspection : rules;
  const items = arr.filter(x => x.section === section);
  if (!items.length) return;
  const allDone = items.every(x => x.completed);
  items.forEach(x => { x.completed = !allDone; touchLocal(x); });
  save();
  refresh(isTI ? 'ti' : 'rb');
  showToast(allDone ? `${section} reset` : `${items.length} item(s) marked complete in ${section}`);
}

function toggleExpand(id, isTI) {
  if (noteEditing.has(id)) return;
  if (expandedItems.has(id)) expandedItems.delete(id); else expandedItems.add(id);
  refresh(isTI ? 'ti' : 'rb');
  if (expandedItems.has(id)) {
    requestAnimationFrame(() => scrollTo($('detail-' + id)));
  }
}

function editNote(id) {
  // The note editor renders inside the expanded row, so expand first --
  // otherwise calling this on a collapsed item silently does nothing.
  expandedItems.add(id);
  noteEditing.add(id);
  inspection.some(x => x.id === id) ? renderInspection() : renderRulebook();
  setTimeout(() => { const el = $('note-' + id); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }, 40);
}

function cancelNote(id) {
  noteEditing.delete(id);
  inspection.some(x => x.id === id) ? renderInspection() : renderRulebook();
}

function saveNote(id, isTI) {
  const el = $('note-' + id);
  if (!el) return;
  const arr = isTI ? inspection : rules;
  const item = arr.find(x => x.id === id);
  if (!item) return;
  item.note = el.value.trim();
  item.updated_at = new Date().toISOString();
  noteEditing.delete(id);
  save();
  refresh(isTI ? 'ti' : 'rb');
  showToast('Note saved');
}

// ── DASHBOARD ────────────────────────────────────────────────────────────────
// Keeps the Rulebook / TI page readouts in step with the data, whoever changed it.
function updateChecklistBars() {
  const rb = progress(rules);
  const bar = $('rb-progress-bar');
  if (bar) { bar.style.width = rb.pct + '%'; bar.style.background = pctColor(rb.pct); }
  $('rb-pct-txt').textContent = rb.pct + '%';
  $('rb-ct-txt').textContent = `${rb.done} / ${rb.total}`;
  const ti = progress(inspection);
  const tbar = $('ti-progress-bar');
  if (tbar) { tbar.style.width = ti.pct + '%'; tbar.style.background = pctColor(ti.pct); }
  $('ti-pct-txt').textContent = ti.pct + '%';
  $('ti-ct-txt').textContent = `${ti.done} / ${ti.total} cleared`;
}

function setRing(id, pctId, pct) {
  const el = $(id);
  if (el) el.style.strokeDasharray = `${pct / 100 * CIRC} ${CIRC}`;
  const p = $(pctId);
  if (p) p.textContent = pct + '%';
}

function updateDashboard() {
  const rb = progress(rules);
  const ti = progress(inspection);
  const total = rb.total + ti.total;
  const done = rb.done + ti.done;
  const pct = total ? Math.round(done / total * 100) : 0;
  const notes = [...rules, ...inspection].filter(x => x.note && x.note.trim()).length;

  // Hero
  $('overall-pct').textContent = pct + '%';
  $('overall-sub').textContent = `${done} of ${total} tracked items completed`;
  $('overall-bar').style.width = pct + '%';
  $('overall-phase').textContent = pctLabel(pct);
  $('overall-bar').style.background = `linear-gradient(90deg, var(--orange), ${pctColor(pct)})`;

  // Mini stats
  $('stat-pending').textContent = total - done;
  $('stat-done').textContent = done;
  $('stat-notes').textContent = notes;
  $('stat-team').textContent = team.length;

  // Rings
  $('dash-rb-pct').textContent = rb.pct + '%';
  $('dash-rb-done').textContent = rb.done;
  $('dash-rb-tot').textContent = rb.total;
  setRing('ring-rb', 'ring-rb-pct', rb.pct);
  $('ring-rb').setAttribute('stroke', pctColor(rb.pct));

  $('dash-ti-pct').textContent = ti.pct + '%';
  $('dash-ti-done').textContent = ti.done;
  $('dash-ti-tot').textContent = ti.total;
  setRing('ring-ti', 'ring-ti-pct', ti.pct);
  $('ring-ti').setAttribute('stroke', pctColor(ti.pct));

  // Section progress — rulebook and TI side by side
  $('dash-sections').innerHTML =
    sectionBars(rules, false) + sectionBars(inspection, true);

  // Recently completed across both checklists
  const recent = [...rules.map(x => ({ ...x, kind: 'Rulebook', code: x.rule_code })),
                  ...inspection.map(x => ({ ...x, kind: 'TI Checklist', code: x.item_number }))]
    .filter(x => x.completed_at)
    .sort((a, b) => new Date(b.completed_at) - new Date(a.completed_at))
    .slice(0, 6);
  const rec = $('dash-recent');
  rec.innerHTML = recent.length
    ? recent.map(x => `<div class="recent-row">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2.5" class="recent-check"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        <span class="recent-title">${esc(x.title)}</span>
        <span class="recent-code">${esc(x.code)}</span>
        <span class="recent-kind">${esc(x.kind)}</span>
        <span class="recent-when">${relativeTime(x.completed_at)}</span>
      </div>`).join('')
    : '<p class="muted-copy">Nothing completed yet. Start with the Rulebook or the TI checklist.</p>';

  updateInsightCards();
  updateSideProgress();
  updateChecklistBars();
  updateLastSaved();
  pulseComplete();
}

function sectionBars(arr, isTI) {
  const groups = groupBy(arr, x => x.section);
  const rows = [...groups].map(([name, items]) => {
    const p = progress(items);
    return `<div class="secbar">
      <div class="secbar-top">
        <span class="secbar-name">${esc(name)}</span>
        <span class="secbar-ct"><b style="color:${pctColor(p.pct)}">${p.pct}%</b> ${p.done}/${p.total}</span>
      </div>
      <div class="pbar-track"><div class="pbar-fill" style="width:${p.pct}%;background:${pctColor(p.pct)}"></div></div>
    </div>`;
  }).join('');
  return `<div class="secbar-group">
    <div class="secbar-group-hd">${isTI ? 'Technical Inspection' : 'Rulebook'}</div>
    <div class="secbar-grid">${rows}</div>
  </div>`;
}

function relativeTime(iso) {
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return Math.floor(s / 60) + 'm ago';
  if (s < 86400) return Math.floor(s / 3600) + 'h ago';
  return Math.floor(s / 86400) + 'd ago';
}

function updateInsightCards() {
  const next = [...rules.map(x => ({ ...x, code: x.rule_code })),
                ...inspection.map(x => ({ ...x, code: x.item_number }))]
    .find(x => !x.completed);
  const tiPending = inspection.filter(x => !x.completed).length;
  $('next-priority').textContent = next
    ? `${next.code} · ${next.title}` : 'Everything is complete';
  $('inspection-priority').textContent = tiPending
    ? `${tiPending} inspection check${tiPending === 1 ? '' : 's'} remain` : 'Inspection complete';
  $('team-priority').textContent = team.length
    ? `${team.length} member${team.length === 1 ? '' : 's'} in the project` : 'Add your core team members';
}

function updateSideProgress() {
  const rb = progress(rules), ti = progress(inspection);
  const total = rb.total + ti.total, done = rb.done + ti.done;
  const pct = total ? Math.round(done / total * 100) : 0;
  $('side-progress-fill').style.width = pct + '%';
  $('side-progress-text').textContent = pct + '% ready';
  $('side-progress-count').textContent = `${done}/${total}`;
}

function goToNextPending() {
  const nextRule = rules.find(x => !x.completed);
  if (nextRule) {
    nav('rulebook'); setStatusFilter('rb-status', 'pending');
    syncQuickChips('rb', 'pending'); renderRulebook(); focusItem(nextRule.id);
    return;
  }
  const nextTI = inspection.find(x => !x.completed);
  if (nextTI) {
    nav('inspection'); setStatusFilter('ti-status', 'pending');
    syncQuickChips('ti', 'pending'); renderInspection(); focusItem(nextTI.id);
    return;
  }
  showToast('Everything is completed');
}

function focusItem(id) {
  const el = $('item-' + id);
  if (el) {
    expandedItems.add(id);
    renderRulebookIfNeeded(id);
    scrollTo($('item-' + id), 'center');
  }
}
function renderRulebookIfNeeded(id) {
  if ($('page-rulebook').classList.contains('active')) renderRulebook();
  else if ($('page-inspection').classList.contains('active')) renderInspection();
}

function pulseComplete() {
  const all = progress(rules).pct === 100 && progress(inspection).pct === 100;
  if (all && !document.body.dataset.celebrated) {
    document.body.dataset.celebrated = '1';
    showToast('All checklist items completed');
  }
  if (!all) delete document.body.dataset.celebrated;
}

// ── TEAM ─────────────────────────────────────────────────────────────────────
function renderTeam() {
  $('team-ct').textContent = team.length + ' member' + (team.length !== 1 ? 's' : '');
  const el = $('team-list');
  if (!team.length) {
    el.innerHTML = `<div class="team-empty">
      <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="var(--border)" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      <p>No team members yet.</p>
      <p class="muted-copy">Click Add Member to get started.</p>
    </div>`;
    return;
  }
  el.innerHTML = `<div class="team-list">${team.map(m => `
    <div class="team-row">
      <div class="team-av">${esc(m.name.charAt(0).toUpperCase())}</div>
      <div class="team-id">
        <div class="team-name">${esc(m.name)}</div>
        ${m.role ? `<div class="team-role">${esc(m.role)}</div>` : ''}
      </div>
      <button class="team-del" onclick="deleteMember('${m.id}')" title="Remove ${esc(m.name)}" aria-label="Remove ${esc(m.name)}">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
      </button>
    </div>`).join('')}</div>`;
}

function toggleAddForm() {
  const wrap = $('add-form-wrap');
  const open = wrap.style.display === 'none';
  wrap.style.display = open ? 'block' : 'none';
  $('tm-err').style.display = 'none';
  if (open) $('tm-name').focus();
}

function addMember() {
  const name = $('tm-name').value.trim();
  const role = $('tm-role').value.trim();
  const err = $('tm-err');
  if (!name) { err.textContent = 'Name is required.'; err.style.display = 'block'; return; }
  err.style.display = 'none';
  team.push({ id: uid(), name, role, created_at: new Date().toISOString() });
  if (typeof syncOnTeamChange === 'function') syncOnTeamChange();
  $('tm-name').value = '';
  $('tm-role').value = '';
  save();
  renderTeam();
  updateDashboard();
  $('add-form-wrap').style.display = 'none';
  // release focus so single-key shortcuts keep working
  if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  showToast('Team member added');
}

function deleteMember(id) {
  const m = team.find(x => x.id === id);
  if (!confirm(`Remove ${m ? m.name : 'this member'} from the team?`)) return;
  team = team.filter(x => x.id !== id);
  if (typeof syncOnTeamRemove === 'function') syncOnTeamRemove(id);
  save();
  renderTeam();
  updateDashboard();
  showToast('Team member removed');
}

// ── BACKUP / RESET ───────────────────────────────────────────────────────────
function exportData() {
  const payload = {
    app: 'Chitrak Rulebook Checklist',
    version: '2.0',
    exported_at: new Date().toISOString(),
    source: { rulebook: 'Rulebook-V-1.0.pdf', inspection: 'TI SHEET.pdf' },
    rules, inspection, team
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'chitrak-checklist-backup.json';
  a.click();
  URL.revokeObjectURL(a.href);
  showToast('Backup exported');
}

function importData(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (!Array.isArray(data.rules) || !Array.isArray(data.inspection) || !Array.isArray(data.team))
        throw new Error('invalid');
      if (!confirm('Import this backup? Your current local progress will be replaced.')) return;
      rules = hydrate(RULES_SEED, data.rules);
      inspection = hydrate(INSPECTION_SEED, data.inspection);
      team = data.team;
      save();
      initFilters();
      updateDashboard();
      renderRulebook();
      renderInspection();
      renderTeam();
      showToast('Backup imported');
    } catch (e) {
      showToast('Invalid backup file');
    }
  };
  reader.readAsText(file);
}

function resetAll() {
  if (!confirm('Reset ALL checklist progress, notes and team data stored in this browser? This cannot be undone unless you have a backup.')) return;
  Object.values(LS).forEach(k => { try { localStorage.removeItem(k); } catch (e) {} });
  load();
  initFilters();
  updateDashboard();
  renderRulebook();
  renderInspection();
  renderTeam();
  showToast('Project reset');
}

function printChecklist() {
  window.print();
}

// ── COMMAND PALETTE ──────────────────────────────────────────────────────────
const COMMANDS = [
  { title: 'Open Dashboard', hint: 'Project overview', key: 'D', run: () => nav('dashboard') },
  { title: 'Open Rulebook', hint: 'Requirements checklist', key: 'R', run: () => nav('rulebook') },
  { title: 'Open Technical Inspection', hint: 'TI sheet checklist', key: 'T', run: () => nav('inspection') },
  { title: 'Open Team', hint: 'Manage team members', key: 'M', run: () => nav('team') },
  { title: 'Show pending Rulebook items', hint: 'Unfinished requirements', key: 'P',
    run: () => { nav('rulebook'); setStatusFilter('rb-status', 'pending'); syncQuickChips('rb', 'pending'); renderRulebook(); } },
  { title: 'Show pending TI items', hint: 'Unfinished inspection checks', key: 'I',
    run: () => { nav('inspection'); setStatusFilter('ti-status', 'pending'); syncQuickChips('ti', 'pending'); renderInspection(); } },
  { title: 'Show completed items', hint: 'Filter to done only', key: 'C',
    run: () => currentPage === 'inspection'
      ? (setStatusFilter('ti-status', 'done'), syncQuickChips('ti', 'done'), renderInspection())
      : (setStatusFilter('rb-status', 'done'), syncQuickChips('rb', 'done'), renderRulebook()) },
  { title: 'Continue checklist', hint: 'Jump to the next incomplete item', key: 'N', run: () => goToNextPending() },
  { title: 'Expand all sections', hint: 'Open every group', key: 'E',
    run: () => (currentPage === 'inspection' ? setAllSections('ti', true) : setAllSections('rb', true)) },
  { title: 'Collapse all sections', hint: 'Close every group', key: 'X',
    run: () => (currentPage === 'inspection' ? setAllSections('ti', false) : setAllSections('rb', false)) },
  { title: 'Export backup', hint: 'Download local JSON backup', key: 'B', run: () => exportData() },
  { title: 'Import backup', hint: 'Restore a previous JSON backup', key: 'U', run: () => $('import-file').click() },
  { title: 'Print checklist', hint: 'Print or save as PDF', key: 'Y', run: () => printChecklist() },
  { title: 'Keyboard shortcuts', hint: 'Show the shortcut reference', key: '?', run: () => openShortcuts() },
  { title: 'Toggle sidebar', hint: 'Compact navigation', key: 'S', run: () => toggleSidebar() }
];

function openCommandPalette() {
  const m = $('command-palette');
  if (!m) return;
  m.classList.add('open');
  commandIndex = 0;
  commandMatches = COMMANDS.slice();
  renderCommandList();
  setTimeout(() => $('command-search')?.focus(), 30);
}
function closeCommandPalette() { $('command-palette')?.classList.remove('open'); }

function renderCommandList() {
  const list = $('command-list');
  if (!list) return;
  const q = ($('command-search')?.value || '').trim().toLowerCase();
  commandMatches = COMMANDS.filter(c => !q || c.title.toLowerCase().includes(q) || c.hint.toLowerCase().includes(q));
  if (!commandMatches.length) { list.innerHTML = '<div class="empty-state" style="margin:8px 0">No matching action</div>'; return; }
  if (commandIndex >= commandMatches.length) commandIndex = 0;
  list.innerHTML = commandMatches.map((c, i) =>
    `<button class="command-item ${i === commandIndex ? 'selected' : ''}" onclick="runCommand(${i})">
      <div class="ci-main"><strong>${esc(c.title)}</strong><span>${esc(c.hint)}</span></div>
      <span class="command-key">${esc(c.key)}</span>
    </button>`).join('');
}

function runCommand(i) {
  const c = commandMatches[i];
  if (!c) return;
  closeCommandPalette();
  setTimeout(c.run, 40);
}

function openShortcuts() { $('shortcut-modal')?.classList.add('open'); }
function closeShortcuts() { $('shortcut-modal')?.classList.remove('open'); }

// ── KEYBOARD NAVIGATION ──────────────────────────────────────────────────────
// Keyboard focus is tracked by item id so it survives the re-render that
// follows every tick or note save. If the item is filtered away, focus resets.
function focusedItemId() {
  const el = visibleItems()[focusIndex];
  return el ? el.dataset.item : null;
}

function restoreFocusedItem(id) {
  const items = visibleItems();
  if (!id) { focusIndex = -1; return; }
  const i = items.findIndex(el => el.dataset.item === id);
  focusIndex = i;
  items.forEach((el, k) => el.classList.toggle('keyboard-focus', k === i));
}

function visibleItems() {
  const page = currentPage === 'inspection' ? 'inspection' : 'rulebook';
  return [...document.querySelectorAll('#page-' + (page === 'inspection' ? 'inspection' : 'rulebook') + ' .cl-item')];
}

function moveFocus(delta) {
  const items = visibleItems();
  if (!items.length) return;
  focusIndex = Math.max(0, Math.min(items.length - 1, focusIndex + delta));
  items.forEach((el, i) => el.classList.toggle('keyboard-focus', i === focusIndex));
  scrollTo(items[focusIndex]);
}

function actOnFocused(tick) {
  const id = focusedItemId();
  if (!id) return;
  const isTI = inspection.some(x => x.id === id);
  tick ? toggleItem(id, isTI) : toggleExpand(id, isTI);
}

document.addEventListener('keydown', e => {
  const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName);
  const modalOpen = $('command-palette')?.classList.contains('open');

  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openCommandPalette(); return; }
  if (modalOpen) {
    if (e.key === 'Escape') { e.preventDefault(); closeCommandPalette(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); commandIndex = Math.min(commandIndex + 1, Math.max(0, commandMatches.length - 1)); renderCommandList(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); commandIndex = Math.max(commandIndex - 1, 0); renderCommandList(); }
    else if (e.key === 'Enter') { e.preventDefault(); runCommand(commandIndex); }
    return;
  }
  if ($('shortcut-modal')?.classList.contains('open')) {
    if (e.key === 'Escape' || e.key === '?') { e.preventDefault(); closeShortcuts(); }
    return;
  }
  if (e.key === 'Escape' && typing) { document.activeElement.blur(); return; }
  if (typing) return;

  const listPage = currentPage === 'rulebook' || currentPage === 'inspection';

  if (e.key === '/') {
    e.preventDefault();
    if (!listPage) nav('rulebook');
    const el = $(currentPage === 'inspection' ? 'ti-search' : 'rb-search');
    if (el) { el.focus(); el.select(); }
    return;
  }
  if (e.key === '?') { e.preventDefault(); openShortcuts(); return; }
  if (listPage) {
    if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); moveFocus(1); return; }
    if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); moveFocus(-1); return; }
    if (e.key === 'x') { e.preventDefault(); actOnFocused(true); return; }
    if (e.key === 'Enter') { e.preventDefault(); actOnFocused(false); return; }
  }
  if (e.key === 'd' || e.key === 'D') nav('dashboard');
  else if (e.key === 'r' || e.key === 'R') nav('rulebook');
  else if (e.key === 't' || e.key === 'T') nav('inspection');
  else if (e.key === 'm' || e.key === 'M') nav('team');
  else if (e.key === 'n' || e.key === 'N') goToNextPending();
});

// ── SEARCH INPUT BINDING ─────────────────────────────────────────────────────
['rb', 'ti'].forEach(prefix => {
  const el = $(prefix + '-search');
  if (el) el.addEventListener('input', () => prefix === 'rb' ? renderRulebook() : renderInspection());
  const f = $(prefix + '-filter');
  if (f) f.addEventListener('change', () => prefix === 'rb' ? renderRulebook() : renderInspection());
});

// ── CROSS-TAB SYNC ───────────────────────────────────────────────────────────
window.addEventListener('storage', e => {
  if (e.key !== LS.rules && e.key !== LS.insp && e.key !== LS.team) return;
  load();
  initFilters();
  updateDashboard();
  if (currentPage === 'rulebook') renderRulebook();
  if (currentPage === 'inspection') renderInspection();
  if (currentPage === 'team') renderTeam();
  showToast('Synced changes from another tab');
});

window.addEventListener('beforeunload', () => {
  try { localStorage.setItem(LS.meta, JSON.stringify({ lastSavedAt })); } catch (e) {}
  if (typeof flushOutbox === 'function') flushOutbox();
});

// ── INIT ─────────────────────────────────────────────────────────────────────
function init() {
  load();
  initFilters();
  if (localStorage.getItem(LS.sidebar) === '1') document.body.classList.add('sidebar-collapsed');

  $('import-file').addEventListener('change', e => {
    if (e.target.files[0]) importData(e.target.files[0]);
    e.target.value = '';
  });
  $('command-search')?.addEventListener('input', () => { commandIndex = 0; renderCommandList(); });

  updateDashboard();
  renderRulebook();
  renderInspection();
  renderTeam();

  if (typeof syncInit === 'function') syncInit();

  window.addEventListener('online', () => { if (typeof syncRetry === 'function') syncRetry(); });
  window.addEventListener('offline', () => {
    if (typeof setSyncStatus === 'function' && syncConfig()) setSyncStatus('offline');
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && typeof flushOutbox === 'function') flushOutbox();
  });
  setInterval(() => { if (typeof flushOutbox === 'function') flushOutbox(); }, 20000);

  setInterval(() => { updateLastSaved(); if (currentPage === 'dashboard') updateDashboard(); }, 60000);
}

init();
</script>'''

SUPABASE_JS = io.open('_supabase_client.js', encoding='utf-8').read()


def load_supabase_config():
    """Resolve sync credentials, in order of precedence:

    1. SYNC_URL / SYNC_ANON_KEY environment variables -- used by Vercel builds,
       where the key is stored in the project's environment settings.
    2. supabase-config.json -- local development. Git-ignored, so the key never
       enters repository history.
    3. Nothing -- produces a local-only build with sync disabled.
    """
    url = os.environ.get('SYNC_URL', '').strip()
    key = os.environ.get('SYNC_ANON_KEY', '').strip()
    if url and key:
        print('sync credentials from environment (SYNC_URL / SYNC_ANON_KEY)')
        return url, key
    if url or key:
        print('warning: SYNC_URL and SYNC_ANON_KEY must both be set to enable sync')

    try:
        cfg = json.load(io.open('supabase-config.json', encoding='utf-8'))
    except Exception:
        print('warning: no sync credentials found '
              '(set SYNC_URL + SYNC_ANON_KEY, or create supabase-config.json) '
              '-- building in local-only mode')
        return '', ''
    url, key = cfg.get('url', ''), cfg.get('anonKey', '')
    print('sync credentials from supabase-config.json' if url and key
          else 'warning: supabase-config.json incomplete -- building in local-only mode')
    return url, key


SYNC_URL, SYNC_KEY = load_supabase_config()
SUPABASE_JS = SUPABASE_JS.replace('__SYNC_URL__', SYNC_URL).replace('__SYNC_KEY__', SYNC_KEY)

js = (JS_TEMPLATE
      .replace('__SUPABASE__', SUPABASE_JS)
      .replace('__RULES__', RULES_JS)
      .replace('__TI__', TI_JS))

open('_new_script.html', 'w', encoding='utf-8').write(js)
print('generated _new_script.html', len(js), 'bytes; sync=%s'
      % ('configured' if SYNC_URL else 'local-only'))
