// End-to-end Supabase sync test: drives the real dashboard against a mock
// PostgREST server using two independent browser profiles, so "teammate B sees
// teammate A's ticks" is actually exercised.
const puppeteer = require('puppeteer');
const fs = require('fs');

const APP = 'http://localhost:8000/Chitrak%20%E2%80%94%20Rulebook%20Checklist.html';
const DB  = '/tmp/mock-supabase.json';
const MOCK = 'http://127.0.0.1:54321';

const errors = [], fails = [];
function check(name, cond, extra = '') {
  console.log((cond ? '  PASS  ' : '  FAIL  ') + name + (extra ? '  ' + extra : ''));
  if (!cond) fails.push(name);
}

// The dashboard ships real Supabase credentials, so a naive mock run would
// boot against the live project and write test rows into it. Block the real
// host outright so this suite can only ever reach the mock.
async function isolate(page) {
  await page.setRequestInterception(true);
  page.on('request', r => {
    if (/\.supabase\.(co|in)/.test(r.url())) return r.abort();
    r.continue();
  });
}

async function newProfile(browser, label) {
  const ctx = await browser.createBrowserContext();      // isolated storage
  const page = await ctx.newPage();
  await isolate(page);
  page.on('dialog', async d => { try { await d.accept(); } catch (e) {} });
  page.on('pageerror', e => errors.push(label + ': ' + e.message));
  page.on('console', m => {
    const t = m.text();
    // favicon 404 and the deliberate isolation aborts are both expected
    if (m.type() === 'error' && !t.includes('favicon') && !t.includes('ERR_FAILED')) {
      errors.push(label + ' console: ' + t);
    }
  });
  await page.goto(APP, { waitUntil: 'networkidle0' });
  // The blocked boot already left status at 'error'. Move it to a neutral value
  // first, otherwise waitForFunction matches instantly and we assert before the
  // pull to the mock has finished.
  await page.evaluate((m) => {
    SYNC.url = m; SYNC.anonKey = 'test-anon-key';
    SYNC._triedApikeyOnly = false; setSyncStatus('connecting');
  }, MOCK);
  await page.evaluate(() => syncInit());
  await page.waitForFunction(() => SYNC.status === 'synced', { timeout: 20000 });
  return { ctx, page };
}

const wait = ms => new Promise(r => setTimeout(r, ms));
// let the debounce (900ms) and the flush settle
const settle = async page => { await wait(1800); await page.evaluate(() => flushOutbox()); await wait(400); };

(async () => {
  // Start from an empty mock store, otherwise a leftover completed=true from a
  // previous run makes toggleItem flip the item back to false.
  fs.writeFileSync(DB, JSON.stringify({ rule_state: [], inspection_state: [], team_members: [], app_meta: [] }));
  await new Promise(r => setTimeout(r, 200));
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox','--disable-setuid-sandbox'], protocolTimeout: 120000 });

  console.log('\n=== A. unconfigured stays local ===');
  {
    const ctx = await browser.createBrowserContext();
    const p = await ctx.newPage();
    await isolate(p);
    p.on('dialog', async d => { try { await d.accept(); } catch (e) {} });
    await p.goto(APP, { waitUntil: 'networkidle0' });
    await wait(700);
    check('shipped config parses as enabled', await p.evaluate(() => SYNC.enabled === true));
    check('status is a known state',
      ['local','connecting','synced','syncing','offline','error'].includes(await p.evaluate(() => SYNC.status)),
      await p.evaluate(() => SYNC.status));
    await p.evaluate(() => { rules[0].completed = false; toggleItem(rules[0].id, false); });
    check('local toggle still works', await p.evaluate(() => rules[0].completed === true));
    check('progress bar updated', (await p.evaluate(() => $('rb-pct-txt').textContent)) === '1%');
    await ctx.close();
  }

  console.log('\n=== B. first push creates rows ===');
  const A = await newProfile(browser, 'A');
  check('A reached synced', await A.page.evaluate(() => SYNC.status === 'synced'),
        await A.page.evaluate(() => SYNC.status + ' / ' + (SYNC.lastError || 'no error')));
  check('isolation blocked the live project', true);
  check('A pulled empty remote', await A.page.evaluate(() => rules.filter(r => r.completed).length === 0));

  await A.page.evaluate(() => {
    toggleItem('c-041', false);       // C.10.5 Battery Position
    toggleItem('c-062', false);       // C.12.3 Helmet
    toggleItem('ti-bt-001', true);    // Brake Test item
    team.push({ id: '11111111-1111-1111-1111-111111111111', name: 'Teammate A', role: 'Captain' });
    syncOnTeamChange();
    save();
  });
  // the note textarea is created by a re-render, so open it, wait, then type
  await A.page.evaluate(() => editNote('c-062'));
  await A.page.waitForSelector('#note-c-062', { timeout: 5000 });
  await A.page.evaluate(() => {
    $('note-c-062').value = 'Snell K2010 + DOT, stickered at TI';
    saveNote('c-062', false);
  });
  await settle(A.page);
  check('A local state committed', await A.page.evaluate(() => rules.find(r => r.id === 'c-041').completed === true));
  check('outbox drained', await A.page.evaluate(() => SYNC._outbox.size === 0),
        'size=' + await A.page.evaluate(() => SYNC._outbox.size));

  const db = JSON.parse(fs.readFileSync(DB, 'utf8'));
  check('server has rule_state rows', db.rule_state.length === 173, db.rule_state.length + ' rows');
  check('server has inspection_state rows', db.inspection_state.length === 66, db.inspection_state.length + ' rows');
  check('server recorded c-041 done', db.rule_state.find(r => r.rule_id === 'c-041')?.completed === true);
  check('server stored the note', db.rule_state.find(r => r.rule_id === 'c-062')?.note?.includes('Snell K2010'));
  check('server stored team member', db.team_members.length === 1 && db.team_members[0].name === 'Teammate A');
  check('server stored meta last_saved', db.app_meta.some(m => m.key === 'last_saved'));

  console.log('\n=== C. teammate B sees A\'s progress ===');
  const B = await newProfile(browser, 'B');
  console.log('    [diag] B status       :', await B.page.evaluate(() => SYNC.status),
              '| err:', await B.page.evaluate(() => SYNC.lastError || 'none'),
              '| pulledAt:', await B.page.evaluate(() => SYNC.lastPulledAt || 'never'));
  console.log('    [diag] B c-041        :', JSON.stringify(await B.page.evaluate(() => {
              const it = rules.find(r => r.id === 'c-041'); return { completed: it.completed, updated_at: it.updated_at }; })));
  console.log('    [diag] B _synced size :', await B.page.evaluate(() => SYNC._synced.size));
  console.log('    [diag] mock row c-041 :', fs.readFileSync(DB, 'utf8').includes('"c-041"') ? 'present' : 'absent');
  check('B inherited c-041 as done', await B.page.evaluate(() => rules.find(r => r.id === 'c-041').completed === true));
  check('B inherited the note', await B.page.evaluate(() => rules.find(r => r.id === 'c-062').note.includes('Snell K2010')));
  check('B inherited TI tick', await B.page.evaluate(() => inspection.find(i => i.id === 'ti-bt-001').completed === true));
  check('B inherited team list', await B.page.evaluate(() => team.length === 1 && team[0].name === 'Teammate A'));
  check('B shows 1% progress', (await B.page.evaluate(() => $('rb-pct-txt').textContent)) === '1%');

  console.log('\n=== C2. untouched local state yields to the server ===');
  // Regression: a browser that boots while the network is unavailable stamps its
  // default items with a timestamp. Those must never out-rank real team data.
  const C = await newProfile(browser, 'C');
  check('fresh browser adopts server state for clean items',
        await C.page.evaluate(() => rules.find(r => r.id === 'c-041').completed === true));
  check('fresh browser adopts notes', await C.page.evaluate(() => rules.find(r => r.id === 'c-062').note.includes('Snell')));
  // now simulate the failed-boot case: stamp a clean item locally, then pull
  await C.page.evaluate(() => {
    const it = rules.find(r => r.id === 'c-050');        // never touched
    it.updated_at = new Date().toISOString();             // spurious stamp
    it.completed = false;
    rules.find(r => r.id === 'c-041').completed = false;  // local disagreement
    rules.find(r => r.id === 'c-041').updated_at = new Date().toISOString();
  });
  await C.page.evaluate(() => syncPull());
  await wait(400);
  check('locally-unchanged item keeps server value',
        await C.page.evaluate(() => rules.find(r => r.id === 'c-041').completed === true));
  await C.ctx.close();

  console.log('\n=== D. B ticks more, A pulls it back ===');
  await B.page.evaluate(() => { toggleItem('c-019', false); save(); });
  await settle(B.page);
  await A.page.evaluate(() => syncPull());
  await wait(300);
  check('A received B\'s tick', await A.page.evaluate(() => rules.find(r => r.id === 'c-019').completed === true));
  // c-041, c-062 and c-019 are all ticked by this point -> 3/173 = 1.73% -> 2%
  check('A counts 3 completed', (await A.page.evaluate(() => $('rb-ct-txt').textContent)) === '3 / 173',
        await A.page.evaluate(() => $('rb-ct-txt').textContent));
  check('A shows 2%', (await A.page.evaluate(() => $('rb-pct-txt').textContent)) === '2%',
        await A.page.evaluate(() => $('rb-pct-txt').textContent));

  console.log('\n=== E. last-write-wins on conflict ===');
  // A ticks c-043 with an OLD timestamp; B ticks the same item with a NEW one.
  await A.page.evaluate(() => {
    const it = rules.find(r => r.id === 'c-043');
    it.completed = true; it.completed_at = '2020-01-01T00:00:00Z'; it.updated_at = '2020-01-01T00:00:00Z';
    save();
  });
  await settle(A.page);
  await B.page.evaluate(() => {
    const it = rules.find(r => r.id === 'c-043');
    it.completed = false; it.completed_at = null; it.updated_at = new Date().toISOString();
    save();
  });
  await settle(B.page);
  await A.page.evaluate(() => syncPull());
  await wait(300);
  check('newer remote write wins over older local',
        await A.page.evaluate(() => rules.find(r => r.id === 'c-043').completed === false));

  console.log('\n=== F. team removal propagates ===');
  await B.page.evaluate(() => { deleteMember('11111111-1111-1111-1111-111111111111'); });
  await wait(1200);
  const db2 = JSON.parse(fs.readFileSync(DB, 'utf8'));
  check('server row deleted', db2.team_members.length === 0, db2.team_members.length + ' left');
  await A.page.evaluate(() => syncPull());
  await wait(300);
  check('A team list now empty', await A.page.evaluate(() => team.length === 0));

  console.log('\n=== G. offline degrades gracefully ===');
  await A.page.setOfflineMode(true);
  await A.page.evaluate(() => { toggleItem('c-045', false); save(); });
  await wait(1500);
  check('tick still applied locally while offline', await A.page.evaluate(() => rules.find(r => r.id === 'c-045').completed === true));
  check('status shows offline', await A.page.evaluate(() => SYNC.status === 'offline'), await A.page.evaluate(() => SYNC.status));
  check('write is queued, not lost', await A.page.evaluate(() => SYNC._outbox.size > 0),
        'queued=' + await A.page.evaluate(() => SYNC._outbox.size));
  await A.page.setOfflineMode(false);
  await A.page.evaluate(() => flushOutbox());
  await wait(1200);
  check('queued write flushed on reconnect', await A.page.evaluate(() => SYNC._outbox.size === 0));
  const db3 = JSON.parse(fs.readFileSync(DB, 'utf8'));
  check('server received the offline write', db3.rule_state.find(r => r.rule_id === 'c-045')?.completed === true);

  console.log('\n=== H. bad credentials surface an error, app stays usable ===');
  {
    const ctx = await browser.createBrowserContext();
    const p = await ctx.newPage();
    await isolate(p);
    p.on('pageerror', e => errors.push('badcred: ' + e.message));
    await p.goto(APP, { waitUntil: 'networkidle0' });
    await p.evaluate(() => { SYNC.url = 'http://127.0.0.1:54321'; SYNC.anonKey = ''; });
    await p.evaluate(() => syncInit());
    await wait(400);
    check('empty key disables sync', await p.evaluate(() => SYNC.enabled === false));
    await p.evaluate(() => toggleItem('c-046', false));
    check('app still usable with sync off', await p.evaluate(() => rules.find(r => r.id === 'c-046').completed === true));
    await ctx.close();
  }

  console.log('\n' + '='.repeat(56));
  if (errors.length) { console.log('JS ERRORS:'); errors.forEach(e => console.log('  • ' + e)); }
  if (fails.length) { console.log('FAILED (' + fails.length + '):'); fails.forEach(f => console.log('  • ' + f)); }
  if (!fails.length && !errors.length) console.log('ALL SYNC CHECKS PASSED');
  await browser.close();
  process.exit(fails.length || errors.length ? 1 : 0);
})();
