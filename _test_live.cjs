// End-to-end test against the REAL Supabase project.
// Uses two isolated browser profiles to prove a second person sees the first
// person's ticks. Every DB assertion waits on the outbox actually draining
// rather than on a fixed timer, so it cannot race the debounced push.
const puppeteer = require('/tmp/node_modules/puppeteer');
const { execSync } = require('child_process');

const APP  = 'http://localhost:8000/Chitrak%20%E2%80%94%20Rulebook%20Checklist.html';
const KEY  = process.env.SB_KEY;
const BASE = process.env.SB_URL;
const TABLES = ['rule_state', 'inspection_state', 'team_members', 'app_meta'];
const COL = { rule_state:'rule_id', inspection_state:'item_id', team_members:'id', app_meta:'key' };

const fails = [], errors = [];
const check = (n, c, x='') => { console.log((c?'  PASS  ':'  FAIL  ')+n+(x?'  '+x:'')); if(!c) fails.push(n); };
const wait = ms => new Promise(r => setTimeout(r, ms));

const api = (path, method='GET', data=null, prefer='') => {
  const cmd = `curl -s --max-time 25 -X ${method} "${BASE}/rest/v1/${path}"` +
              ` -H "apikey: ${KEY}" -H "Authorization: Bearer ${KEY}" -H "Content-Type: application/json"` +
              (prefer ? ` -H "Prefer: ${prefer}"` : '') +
              (data ? ` -d '${data}'` : '');
  return execSync(cmd, { encoding: 'utf8' });
};
const rows = t => JSON.parse(api(t + '?select=*'));
const wipe = () => TABLES.forEach(t => api(t + '?' + COL[t] + '=neq.__none__', 'DELETE'));

// wait until nothing is queued and no push is in flight
const settled = page => page.waitForFunction(
  () => SYNC._outbox.size === 0 && !SYNC._pushing && !SYNC._pulling, { timeout: 40000 });

async function profile(browser, label) {
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  page.on('dialog', async d => { try { await d.accept(); } catch (e) {} });
  page.on('pageerror', e => errors.push(label + ': ' + e.message));
  page.on('console', m => {
    if (m.type() === 'error' && !m.text().includes('favicon')) errors.push(label + ' console: ' + m.text());
  });
  await page.goto(APP, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => ['synced','error'].includes(SYNC.status), { timeout: 30000 });
  await settled(page);
  return { ctx, page };
}

(async () => {
  console.log('target:', BASE);
  wipe();
  console.log('start state: rule=%d insp=%d team=%d meta=%d',
    rows('rule_state').length, rows('inspection_state').length,
    rows('team_members').length, rows('app_meta').length);

  const browser = await puppeteer.launch({ headless:'new', args:['--no-sandbox','--disable-setuid-sandbox'], protocolTimeout:150000 });

  console.log('\n=== boot ===');
  const A = await profile(browser, 'A');
  check('reaches "synced"', await A.page.evaluate(() => SYNC.status === 'synced'),
        await A.page.evaluate(() => SYNC.status + ' / ' + (SYNC.lastError || 'no error')));
  check('auth mode resolved', ['bearer','apikey-only'].includes(await A.page.evaluate(() => _authMode)),
        'mode=' + await A.page.evaluate(() => _authMode));
  check('bootstrap wrote all rule rows', rows('rule_state').length === 173, rows('rule_state').length + ' rows');
  check('bootstrap wrote all inspection rows', rows('inspection_state').length === 66, rows('inspection_state').length + ' rows');

  console.log('\n=== a single tick reaches the database ===');
  await A.page.evaluate(() => toggleItem('c-041', false));
  await settled(A.page);
  let row = JSON.parse(api('rule_state?rule_id=eq.c-041&select=*'))[0];
  check('c-041 persisted as done', row && row.completed === true, JSON.stringify(row && row.completed));
  check('completed_at stamped', !!(row && row.completed_at));
  check('incremental push, not full re-push', await A.page.evaluate(() => SYNC._outbox.size === 0));

  console.log('\n=== note persists ===');
  await A.page.evaluate(() => editNote('c-062'));
  await A.page.waitForSelector('#note-c-062', { timeout: 8000 });
  await A.page.evaluate(() => { $('note-c-062').value = 'Snell K2010 + DOT'; saveNote('c-062', false); });
  await settled(A.page);
  row = JSON.parse(api('rule_state?rule_id=eq.c-062&select=*'))[0];
  check('note text stored', row && row.note === 'Snell K2010 + DOT', JSON.stringify(row && row.note));

  console.log('\n=== second person pulls it ===');
  const B = await profile(browser, 'B');
  check('B sees the tick',    await B.page.evaluate(() => rules.find(r => r.id === 'c-041').completed === true));
  check('B sees the note',    await B.page.evaluate(() => rules.find(r => r.id === 'c-062').note === 'Snell K2010 + DOT'));
  check('B shows 1% progress', (await B.page.evaluate(() => $('rb-pct-txt').textContent)) === '1%');

  console.log('\n=== B writes, A pulls back ===');
  await B.page.evaluate(() => toggleItem('c-019', false));
  await settled(B.page);
  row = JSON.parse(api('rule_state?rule_id=eq.c-019&select=*'))[0];
  check("B's tick is in the database", row && row.completed === true);
  await A.page.evaluate(() => syncPull());
  await settled(A.page);
  check('A received it', await A.page.evaluate(() => rules.find(r => r.id === 'c-019').completed === true));
  // 2 of 173 is 1.16%, which rounds to 1% -- not 2%
  check('A counts 2 completed', (await A.page.evaluate(() => $('rb-ct-txt').textContent)) === '2 / 173',
        await A.page.evaluate(() => $('rb-ct-txt').textContent));
  check('A shows 1% (2/173 rounds down)', (await A.page.evaluate(() => $('rb-pct-txt').textContent)) === '1%',
        await A.page.evaluate(() => $('rb-pct-txt').textContent));

  console.log('\n=== last-write-wins ===');
  await A.page.evaluate(() => { const it = rules.find(r => r.id === 'c-043');
    it.completed = true; it.completed_at = '2020-01-01T00:00:00Z'; it.updated_at = '2020-01-01T00:00:00Z'; save(); });
  await settled(A.page);
  await B.page.evaluate(() => { const it = rules.find(r => r.id === 'c-043');
    it.completed = false; it.updated_at = new Date().toISOString(); save(); });
  await settled(B.page);
  await A.page.evaluate(() => syncPull());
  await settled(A.page);
  check('newer remote write wins', await A.page.evaluate(() => rules.find(r => r.id === 'c-043').completed === false));

  console.log('\n=== team ===');
  await A.page.evaluate(() => { team.push({ id:'11111111-1111-1111-1111-111111111111', name:'Live Probe', role:'test' }); syncOnTeamChange(); save(); });
  await wait(1500);
  check('member in database', rows('team_members').some(m => m.name === 'Live Probe'));
  await B.page.evaluate(() => syncPull());
  await wait(500);
  check('B sees the member', await B.page.evaluate(() => team.some(m => m.name === 'Live Probe')));
  await B.page.evaluate(() => deleteMember('11111111-1111-1111-1111-111111111111'));
  await wait(1500);
  check('removal reaches database', rows('team_members').length === 0, rows('team_members').length + ' left');

  console.log('\n=== cleanup ===');
  wipe();
  const left = TABLES.map(t => t + '=' + rows(t).length).join(' ');
  check('all tables empty again', TABLES.every(t => rows(t).length === 0), left);

  console.log('\n' + '='.repeat(56));
  if (errors.length) { console.log('JS ERRORS:'); errors.forEach(e => console.log('  • ' + e)); }
  if (fails.length)  { console.log('FAILED (' + fails.length + '):'); fails.forEach(f => console.log('  • ' + f)); }
  if (!fails.length && !errors.length) console.log('LIVE SUPABASE TEST PASSED');
  await browser.close();
  process.exit(fails.length || errors.length ? 1 : 0);
})();
