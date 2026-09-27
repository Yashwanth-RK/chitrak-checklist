// Minimal stand-in for the Supabase PostgREST API, enough to exercise the
// client's pull / upsert / delete paths offline. State lives in a JSON file so
// it survives restarts within a test run.
const http = require('http');
const fs = require('fs');
const url = require('url');

const FILE = process.env.MOCK_DB || '/tmp/mock-supabase.json';
const PORT = Number(process.env.MOCK_PORT || 54321);

function load() {
  try { return JSON.parse(fs.readFileSync(FILE, 'utf8')); }
  catch (e) { return { rule_state: [], inspection_state: [], team_members: [], app_meta: [] }; }
}
function save(db) { fs.writeFileSync(FILE, JSON.stringify(db, null, 2)); }

const server = http.createServer((req, res) => {
  const parsed = url.parse(req.url, true);
  const table = parsed.pathname.replace(/^\/rest\/v1\//, '').split('?')[0];
  const q = parsed.query;

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'apikey, Authorization, Content-Type, Prefer');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS');
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }

  const db = load();
  if (!db[table]) { res.writeHead(404, {'Content-Type':'application/json'}); return res.end(JSON.stringify({message:'relation not found: '+table})); }

  let body = '';
  req.on('data', c => body += c);
  req.on('end', () => {
    try {
      if (req.method === 'GET') {
        let rows = db[table];
        // support ?id=eq.<value> and ?select=*
        const filters = [];
        for (const [k, v] of Object.entries(q)) {
          if (k === 'select' || k === 'order') continue;
          const m = /^(eq|neq|gt|gte|lt|lte)\.(.*)$/.exec(String(v));
          if (m) filters.push([k, m[1], m[2]]);
        }
        for (const [col, op, val] of filters) {
          rows = rows.filter(r => {
            const a = r[col], b = val;
            switch (op) {
              case 'eq': return String(a) === String(b);
              case 'neq': return String(a) !== String(b);
              case 'gt': return a > b;
              case 'gte': return a >= b;
              case 'lt': return a < b;
              case 'lte': return a <= b;
            }
            return true;
          });
        }
        if (q.order) {
          const [col, dir] = String(q.order).split('.');
          rows = rows.slice().sort((a,b) => (a[col] > b[col] ? 1 : a[col] < b[col] ? -1 : 0) * (dir === 'desc' ? -1 : 1));
        }
        res.writeHead(200, {'Content-Type':'application/json'});
        return res.end(JSON.stringify(rows));
      }

      if (req.method === 'POST' || req.method === 'PATCH') {
        const incoming = JSON.parse(body || '[]');
        const arr = Array.isArray(incoming) ? incoming : [incoming];
        const keyOf = r => r.rule_id || r.item_id || r.key || r.id;
        for (const row of arr) {
          const k = keyOf(row);
          const existing = db[table].find(r => String(keyOf(r)) === String(k));
          if (existing) {
            if (req.method === 'PATCH') Object.assign(existing, row);
            else Object.assign(existing, row, { updated_at: row.updated_at || new Date().toISOString() });
          } else {
            db[table].push(row);
          }
        }
        save(db);
        const prefer = String(req.headers.prefer || '');
        if (prefer.includes('return=representation')) {
          res.writeHead(201, {'Content-Type':'application/json'});
          return res.end(JSON.stringify(arr));
        }
        res.writeHead(201, {'Content-Type':'application/json'});
        return res.end(JSON.stringify(arr));
      }

      if (req.method === 'DELETE') {
        const filters = Object.entries(q).map(([k,v]) => [k, /^(eq)\.(.*)$/.exec(String(v))]).filter(f => f[1]);
        let rows = db[table];
        for (const [col, m] of filters) rows = rows.filter(r => String(r[col]) !== String(m[2]));
        db[table] = rows; save(db);
        res.writeHead(204); return res.end();
      }

      res.writeHead(405); res.end();
    } catch (e) {
      res.writeHead(400, {'Content-Type':'application/json'});
      res.end(JSON.stringify({ message: e.message }));
    }
  });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log('mock supabase on http://127.0.0.1:' + PORT);
});
