import { JSDOM } from 'jsdom';
import fs from 'fs';

const html = fs.readFileSync('Chitrak — Rulebook Checklist.html', 'utf8');
const errors = [];
const logs = [];

const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost/',
  beforeParse(w) {
    w.addEventListener('error', e => errors.push('window error: ' + (e.error?.stack || e.message)));
    const origErr = w.console.error;
    w.console.error = (...a) => { errors.push('console.error: ' + a.join(' ')); origErr(...a); };
    // localStorage stub
    const store = new Map();
    Object.defineProperty(w, 'localStorage', {
      value: {
        getItem: k => (store.has(k) ? store.get(k) : null),
        setItem: (k, v) => store.set(k, String(v)),
        removeItem: k => store.delete(k),
        clear: () => store.clear()
      },
      configurable: true
    });
    w.confirm = () => true;
    w.print = () => logs.push('print() called');
    w.scrollTo = () => {};
  }
});

const w = dom.window, d = w.document;
const $ = id => d.getElementById(id);
// top-level `let` bindings are script-scoped, not window properties
const state = expr => w.eval(expr);
const rules = () => state('rules');
const insp  = () => state('inspection');
const team  = () => state('team');

function check(name, cond, extra = '') {
  console.log((cond ? '  PASS  ' : '  FAIL  ') + name + (extra ? '  ' + extra : ''));
  if (!cond) errors.push('assert: ' + name);
}

console.log('\n=== INITIAL RENDER ===');
check('no script errors on load', errors.length === 0, errors.join(' | '));
check('rules loaded (173)', rules().length === 173, 'got ' + rules().length);
check('inspection loaded (66)', insp().length === 66, 'got ' + insp().length);
check('rulebook list rendered', d.querySelectorAll('#rb-list .cl-item').length === 173, d.querySelectorAll('#rb-list .cl-item').length + ' items');
check('rulebook grouped in 6 sections', $('rb-list').children.length === 6, $('rb-list').children.length + ' sections');
check('ti list rendered', d.querySelectorAll('#ti-list .cl-item').length === 66, d.querySelectorAll('#ti-list .cl-item').length + ' items');
check('ti grouped in 6 sections', $('ti-list').children.length === 6, $('ti-list').children.length + ' sections');
check('overall pct = 0%', $('overall-pct').textContent === '0%', $('overall-pct').textContent);
check('overall sub counts all', $('overall-sub').textContent.includes('239'), $('overall-sub').textContent);
check('phase label set', $('overall-phase').textContent === 'Not started', $('overall-phase').textContent);
check('rb total = 173', $('rb-ct-txt').textContent === '0 / 173', $('rb-ct-txt').textContent);
check('ti total = 66', $('ti-ct-txt').textContent === '0 / 66 cleared', $('ti-ct-txt').textContent);
check('section bars: 2 groups', d.querySelectorAll('#dash-sections .secbar-group').length === 2);
check('section bars rendered', d.querySelectorAll('#dash-sections .secbar').length === 6 + 6,
  d.querySelectorAll('#dash-sections .secbar').length + ' bars');
check('recent empty msg', $('dash-recent').textContent.includes('Nothing completed'));
check('next priority set', $('next-priority').textContent.includes('A.1'), $('next-priority').textContent);
check('ti priority set', $('inspection-priority').textContent.includes('66'), $('inspection-priority').textContent);
check('side progress 0/239', $('side-progress-count').textContent === '0/239', $('side-progress-count').textContent);
check('no placeholder warnings', !$('rb-list').textContent.includes('not yet populated'));

console.log('\n=== TOGGLE AN ITEM ===');
const firstId = rules()[0].id;
w.toggleItem(firstId, false);
check('item marked done', rules()[0].completed === true);
check('done class applied', !!d.querySelector(`#item-${firstId}`).classList.contains('done'));
check('overall pct still 0% (1/239)', $('overall-pct').textContent === '0%', $('overall-pct').textContent);
check('sub updated to 1 of 239', $('overall-sub').textContent.includes('1 of 239'), $('overall-sub').textContent);
check('completed stat = 1', $('stat-done').textContent === '1', $('stat-done').textContent);
check('pending stat = 238', $('stat-pending').textContent === '238', $('stat-pending').textContent);
check('recent shows item', $('dash-recent').textContent.includes(rules()[0].title));
check('rb done = 1/173', $('rb-ct-txt').textContent === '1 / 173', $('rb-ct-txt').textContent);
check('persisted to localStorage', JSON.parse(w.localStorage.getItem('ck_rules'))[0].completed === true);
check('next priority advanced', !$('next-priority').textContent.includes('A.1 '), $('next-priority').textContent);

console.log('\n=== EXPAND + NOTES ===');
w.toggleExpand(firstId, false);
check('detail rendered', !!$(`detail-${firstId}`));
check('official text shown', $(`detail-${firstId}`).textContent.includes('Imperial Society'));
check('meta row present', !!$(`detail-${firstId}`).querySelector('.cl-meta'));
w.editNote(firstId);
const ta = $(`note-${firstId}`);
check('textarea focused/present', !!ta);
ta.value = 'BMS tested — Rahul';
w.saveNote(firstId, false);
check('note stored', rules()[0].note === 'BMS tested — Rahul', rules()[0].note);
check('note indicator dot', !!d.querySelector(`#item-${firstId} .note-dot`));
check('notes stat = 1', $('stat-notes').textContent === '1', $('stat-notes').textContent);

console.log('\n=== SEARCH ===');
const rbSearch = $('rb-search');
rbSearch.value = 'kill switch';
rbSearch.dispatchEvent(new w.Event('input', { bubbles: true }));
let items = [...d.querySelectorAll('#rb-list .cl-item')];
check('search narrows results', items.length > 0 && items.length < 20, items.length + ' hits');
check('hits match on official rule text',
  items.every(el => rules().find(r => r.id === el.dataset.item).description.toLowerCase().includes('kill switch')));
check('result count badge', $('rb-count').textContent.includes('of 173'), $('rb-count').textContent);
check('clear button visible', $('rb-clear').style.display === 'inline');

rbSearch.value = 'Rahul';
rbSearch.dispatchEvent(new w.Event('input', { bubbles: true }));
items = [...d.querySelectorAll('#rb-list .cl-item')];
check('search matches team notes', items.length >= 1, items.length + ' hits (note search works)');

w.clearSearch('rb');
check('search cleared', rbSearch.value === '');
check('full list restored', d.querySelectorAll('#rb-list .cl-item').length > 100);

console.log('\n=== FILTERS ===');
$('rb-filter').value = 'Technical';
$('rb-filter').dispatchEvent(new w.Event('change', { bubbles: true }));
check('section filter works', d.querySelectorAll('#rb-list .cl-item').length === 69,
  d.querySelectorAll('#rb-list .cl-item').length + ' technical rules');
check('only Technical sections shown',
  [...d.querySelectorAll('#rb-list .sec-name')].every(s => s.textContent === 'Technical'));

$('rb-status').value = 'done';
w.renderRulebook();
check('Technical+done -> 0 items', d.querySelectorAll('#rb-list .cl-item').length === 0,
  d.querySelectorAll('#rb-list .cl-item').length + ' done');
$('rb-filter').value = 'All'; w.renderRulebook();
check('All+done -> 1 item', d.querySelectorAll('#rb-list .cl-item').length === 1,
  d.querySelectorAll('#rb-list .cl-item').length + ' done');
$('rb-filter').value = 'Technical'; w.renderRulebook();

$('rb-status').value = 'all'; $('rb-filter').value = 'All';
w.renderRulebook();
w.syncQuickChips('rb', 'pending');
check('quick chip sync', d.querySelector('#page-rulebook .filter-chip[data-status="pending"]').classList.contains('active'));

console.log('\n=== SECTION COLLAPSE / FILL ===');
const firstSec = d.querySelector('#rb-list .sec-hd .sec-name');
const secName = firstSec.textContent;
const before = d.querySelectorAll('#rb-list .cl-item').length;
w.toggleSection(encodeURIComponent('rb::' + secName));
check('section collapsed', d.querySelectorAll('#rb-list .cl-item').length < before,
  before + ' -> ' + d.querySelectorAll('#rb-list .cl-item').length);
check('sec meter present', !!d.querySelector('#rb-list .sec-meter i'));
w.setAllSections('rb', false);
check('collapse all', d.querySelectorAll('#rb-list .cl-item').length === 0);
w.setAllSections('rb', true);
check('expand all', d.querySelectorAll('#rb-list .cl-item').length === before);

const techItems = rules().filter(r => r.section === 'Technical');
w.toggleSectionItems('Technical', false);
check('bulk fill marks all done', techItems.every(r => r.completed),
  techItems.filter(r => r.completed).length + '/' + techItems.length);
check('rb pct jumped to 40%', $('rb-pct-txt').textContent === '40%', $('rb-pct-txt').textContent);
w.toggleSectionItems('Technical', false);
check('bulk reset clears', techItems.every(r => !r.completed));
check('rb pct back to 1%', $('rb-pct-txt').textContent === '1%', $('rb-pct-txt').textContent);

console.log('\n=== TI CHECKLIST ===');
w.nav('inspection');
check('ti page active', $('page-inspection').classList.contains('active'));
check('ti list rendered', d.querySelectorAll('#ti-list .cl-item').length === 66,
  d.querySelectorAll('#ti-list .cl-item').length);
w.toggleItem('ti-bt-001', true);
check('ti toggle works', insp().find(i => i.id === 'ti-bt-001').completed === true);
check('ti ring updated', $('dash-ti-pct').textContent === '2%', $('dash-ti-pct').textContent);
const tiSearch = $('ti-search');
tiSearch.value = 'UL-94';
tiSearch.dispatchEvent(new w.Event('input', { bubbles: true }));
check('ti search finds insulation rule', d.querySelectorAll('#ti-list .cl-item').length === 1,
  d.querySelectorAll('#ti-list .cl-item').length + ' hits');
w.clearSearch('ti');

console.log('\n=== TEAM ===');
w.nav('team');
$('tm-name').value = 'Yashwanth'; $('tm-role').value = 'Team Captain';
w.addMember();
check('member added', team().length === 1 && team()[0].name === 'Yashwanth');
check('team rendered', $('team-list').textContent.includes('Yashwanth'));
check('team count text', $('team-ct').textContent === '1 member', $('team-ct').textContent);
check('team stat = 1', $('stat-team').textContent === '1', $('stat-team').textContent);
check('form closed after add', $('add-form-wrap').style.display === 'none');
$('tm-name').value = ''; w.addMember();
check('empty name rejected', team().length === 1);
check('error shown', $('tm-err').style.display === 'block');
w.deleteMember(team()[0].id);
check('member removed', team().length === 0);
check('empty state shown', $('team-list').textContent.includes('No team members yet'));

console.log('\n=== NAVIGATION ===');
['dashboard', 'rulebook', 'inspection', 'team', 'dashboard'].forEach(p => w.nav(p));
check('nav works', $('page-dashboard').classList.contains('active'));
w.toggleSidebar();
check('sidebar collapses', d.body.classList.contains('sidebar-collapsed'));
check('sidebar pref persisted', w.localStorage.getItem('ck_sidebar_collapsed') === '1');
w.toggleSidebar();

console.log('\n=== GO TO NEXT PENDING ===');
w.goToNextPending();
check('jumped to rulebook', $('page-rulebook').classList.contains('active'));
check('pending filter applied', $('rb-status').value === 'pending');
check('next item expanded', d.querySelectorAll('#rb-list .cl-item').length === 172,
  d.querySelectorAll('#rb-list .cl-item').length + ' pending shown');

console.log('\n=== COMMAND PALETTE ===');
w.openCommandPalette();
check('palette open', $('command-palette').classList.contains('open'));
check('all 15 commands listed', d.querySelectorAll('#command-list .command-item').length === 15,
  d.querySelectorAll('#command-list .command-item').length);
$('command-search').value = 'print';
$('command-search').dispatchEvent(new w.Event('input', { bubbles: true }));
check('palette filters', d.querySelectorAll('#command-list .command-item').length === 1,
  d.querySelectorAll('#command-list .command-item').length);
$('command-search').value = 'zzzz';
$('command-search').dispatchEvent(new w.Event('input', { bubbles: true }));
check('no-match state', $('command-list').textContent.includes('No matching action'));
w.closeCommandPalette();
check('palette closed', !$('command-palette').classList.contains('open'));

console.log('\n=== SHORTCUTS MODAL ===');
w.openShortcuts();
check('shortcuts open', $('shortcut-modal').classList.contains('open'));
check('12 shortcut rows', d.querySelectorAll('#shortcut-modal .shortcut-row').length === 12,
  d.querySelectorAll('#shortcut-modal .shortcut-row').length);
w.closeShortcuts();
check('shortcuts closed', !$('shortcut-modal').classList.contains('open'));

console.log('\n=== KEYBOARD ===');
d.activeElement?.blur?.();
w.nav('rulebook');
$('rb-status').value = 'all'; w.renderRulebook();
check('focus released after add member', d.activeElement.tagName === 'BODY', d.activeElement.tagName);
const kd = (key, opts = {}) => d.dispatchEvent(new w.KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...opts }));
kd('j'); kd('j'); kd('j');
check('j moves focus', d.querySelectorAll('#rb-list .cl-item.keyboard-focus').length === 1);
const focused = d.querySelector('#rb-list .cl-item.keyboard-focus').dataset.item;
kd('x');
check('x ticks focused item', rules().find(r => r.id === focused).completed === true, 'item ' + focused);
kd('x');
check('x unticks focused item', rules().find(r => r.id === focused).completed === false);
kd('Enter');
check('Enter expands focused item', !!d.querySelector(`#detail-${focused}`));
kd('k');
check('k moves focus back', !!d.querySelectorAll('#rb-list .cl-item.keyboard-focus')[0]);
kd('d');
check('d -> dashboard', $('page-dashboard').classList.contains('active'));
kd('t');
check('t -> inspection', $('page-inspection').classList.contains('active'));
kd('m');
check('m -> team', $('page-team').classList.contains('active'));
kd('?');
check('? opens shortcuts', $('shortcut-modal').classList.contains('open'));
kd('Escape');
check('Esc closes shortcuts', !$('shortcut-modal').classList.contains('open'));
kd('/', { ctrlKey: false });
check('/ from Team page lands on rulebook search',
  $('page-rulebook').classList.contains('active') && d.activeElement === $('rb-search'),
  d.activeElement?.id);
w.nav('inspection'); kd('/');
check('/ on inspection focuses ti search', d.activeElement === $('ti-search'), d.activeElement?.id);

console.log('\n=== EXPORT / IMPORT ROUND TRIP ===');
rules()[0].completed = true; rules()[0].note = 'note here'; w.save();
team().push({ id: 'x1', name: 'Backup User', role: 'Tester' }); w.save();
const stored = { rules: w.localStorage.getItem('ck_rules'), insp: w.localStorage.getItem('ck_insp'), team: w.localStorage.getItem('ck_team') };
w.resetAll();
check('reset clears rules', rules().every(r => !r.completed));
check('reset clears team', team().length === 0);
check('reset clears localStorage', w.localStorage.getItem('ck_rules') === null);
Object.keys(stored).forEach((k, i) => w.localStorage.setItem(['ck_rules', 'ck_insp', 'ck_team'][i], stored[k]));
w.load(); w.initFilters(); w.updateDashboard(); w.renderRulebook();
check('reload restores state', rules()[0].note === 'note here' && rules()[0].completed === true);
check('reload restores team', team().length === 1 && team()[0].name === 'Backup User');

console.log('\n=== XSS SAFETY ===');
rules()[5].note = '<img src=x onerror="window.__pwned=1">';
rules()[5].completed = true;
w.toggleExpand(rules()[5].id, false);
check('note is escaped, not executed', !w.__pwned && d.querySelectorAll('#rb-list img').length === 0);
check('note text preserved literally', $('rb-list').textContent.includes('<img src=x'));

console.log('\n=== FULL COMPLETION ===');
rules().forEach(r => { r.completed = true; r.completed_at = new Date().toISOString(); });
insp().forEach(r => { r.completed = true; r.completed_at = new Date().toISOString(); });
w.updateDashboard();
check('overall 100%', $('overall-pct').textContent === '100%', $('overall-pct').textContent);
check('phase = Complete', $('overall-phase').textContent === 'Complete', $('overall-phase').textContent);
check('rb 100%', $('rb-pct-txt').textContent === '100%');
check('ti 100%', $('ti-pct-txt').textContent === '100%');
check('all bars green', [...d.querySelectorAll('#dash-sections .pbar-fill')].every(b => b.style.background.includes('green')));

console.log('\n' + '='.repeat(52));
if (errors.length) {
  console.log('FAILURES (' + errors.length + '):');
  errors.forEach(e => console.log('  • ' + e));
  process.exit(1);
} else {
  console.log('ALL CHECKS PASSED');
}
dom.window.close();
process.exit(errors.length ? 1 : 0);
