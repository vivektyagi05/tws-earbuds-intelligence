'use strict';
// Smoke test: 5 endpoints return 200 + meta.simulated, unknown route -> 404,
// missing snapshot -> 503.
const http = require('http');
const app = require('./server');
const srv = app.listen(0, async () => {
  const port = srv.address().port;
  const get = (p) => new Promise((ok, no) => http.get({ port, path: p }, (r) => {
    let b = ''; r.on('data', (c) => (b += c));
    r.on('end', () => ok({ code: r.statusCode, body: JSON.parse(b) })); }).on('error', no));
  let bad = 0;
  const check = (cond, msg) => { if (!cond) { bad++; console.log('FAIL:', msg); } };
  for (const p of ['status', 'recovery', 'battery', 'exposure', 'context']) {
    const r = await get('/api/earbuds/' + p);
    console.log(r.code, p, JSON.stringify(r.body).slice(0, 100) + '...');
    check(r.code === 200, `${p} status ${r.code}`);
    check(r.body.meta && r.body.meta.simulated === true, `${p} meta.simulated`);
  }
  const nf = await get('/api/earbuds/does-not-exist');
  console.log(nf.code, 'unknown route'); check(nf.code === 404, 'unknown route should be 404');
  const saved = process.env.TWS_SNAPSHOT;
  process.env.TWS_SNAPSHOT = '/nonexistent/snapshot.json';
  const miss = await get('/api/earbuds/battery');
  console.log(miss.code, 'missing snapshot'); check(miss.code === 503, 'missing snapshot should be 503');
  if (saved === undefined) delete process.env.TWS_SNAPSHOT; else process.env.TWS_SNAPSHOT = saved;
  console.log(bad ? `SMOKE TEST FAILED (${bad})` : 'SMOKE TEST PASSED');
  srv.close(); process.exit(bad ? 1 : 0);
});
