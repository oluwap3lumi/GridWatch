// Node 24 built-ins only. Connect to an already running Chromium/Edge CDP endpoint.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const debugUrl = process.env.GRIDWATCH_BROWSER_DEBUG_URL || 'http://localhost:9223';
const webUrl = process.env.GRIDWATCH_WEB_URL || 'http://localhost:5173';
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function main() {
  const started = Date.now();
  const response = await fetch(`${debugUrl}/json/new?${encodeURIComponent(webUrl)}`, { method: 'PUT' });
  assert(response.ok, 'Browser must expose a local DevTools endpoint');
  const page = await response.json();
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true });
    ws.addEventListener('error', reject, { once: true });
  });
  let id = 0;
  const pending = new Map();
  const exceptions = [];
  ws.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const entry = pending.get(message.id);
      if (!entry) return;
      clearTimeout(entry.timer);
      pending.delete(message.id);
      if (message.error) entry.reject(new Error(JSON.stringify(message.error)));
      else entry.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails);
  });
  function call(method, params = {}) {
    return new Promise((resolve, reject) => {
      const next = ++id;
      const timer = setTimeout(() => { pending.delete(next); reject(new Error(`CDP timeout: ${method}`)); }, 15000);
      pending.set(next, { resolve, reject, timer });
      ws.send(JSON.stringify({ id: next, method, params }));
    });
  }
  async function evaluate(expression) {
    const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function waitFor(expression, label) {
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      if (await evaluate(`Boolean(${expression})`)) return;
      await pause(100);
    }
    throw new Error(`Timed out: ${label}`);
  }
  try {
    await call('Runtime.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
    await waitFor("document.querySelector('.map-status')?.textContent.startsWith('Map ready')", 'MapLibre worker and WebGL load');
    assert.equal(await evaluate("document.querySelectorAll('.maplibregl-canvas').length"), 1);
    const expectedIds = await evaluate(`(async () => {
      let offset = 0; const assets = [];
      do {
        const response = await fetch('/api/v1/assets?type=transformer&limit=500&offset=' + offset);
        if (!response.ok) throw new Error('Transformer API failed');
        const page = await response.json(); assets.push(...page.features); offset = page.pagination.next_offset;
      } while (offset !== null);
      return assets.filter(a => a.properties.risk).sort((a,b) => b.properties.risk.score-a.properties.risk.score || a.id-b.id).slice(0,10).map(a=>a.id);
    })()`);
    assert.equal(expectedIds.length, 10, 'Smoke corpus must have ten scored transformers');
    await evaluate("document.querySelector('.filters .primary').click()");
    await waitFor("document.querySelector('.list-heading h2')?.textContent === 'Top 10 transformers'", 'top ten ranking');
    const ids = await evaluate("Array.from(document.querySelectorAll('.asset-row strong'),node=>Number(node.textContent.split('#')[1]))");
    assert.deepEqual(ids, expectedIds, 'UI ranking must match every transformer API page');
    await evaluate("document.querySelector('.asset-row').click()");
    await waitFor("document.querySelector('.asset-panel .factors li') && document.querySelector('.asset-panel .outages li')", 'explanations and real outage history');
    const detail = await evaluate("document.querySelector('.asset-panel').textContent");
    assert(detail.includes('uncalibrated model log-odds'));
    assert(detail.includes(`transformer #${expectedIds[0]}`));
    const visibleFactor = await evaluate("(() => {const r=document.querySelector('.asset-panel .factor').getBoundingClientRect();const p=document.querySelector('.asset-panel').getBoundingClientRect();return r.top>=p.top && r.bottom<=p.bottom && r.top>=0 && r.bottom<=innerHeight})()");
    assert(visibleFactor, 'First explanation must be visible without scrolling past attributes');
    await evaluate("document.querySelector('.asset-panel .outages li').scrollIntoView({block:'nearest'})");
    const elapsed = Date.now() - started;
    assert(elapsed < 60000, `Top-ten explanations took ${elapsed} ms`);
    console.log(`PASS top ten matches all API pages; SHAP and outage history visible in ${elapsed} ms (asset #${expectedIds[0]}).`);
    await evaluate("document.querySelector('.asset-panel').scrollTop=0");
    fs.mkdirSync('.tooling', { recursive: true });
    const insight = await call('Page.captureScreenshot');
    fs.writeFileSync('.tooling/m4-detail.png', Buffer.from(insight.data, 'base64'));
    await evaluate("document.querySelector('[aria-label=\"Close asset detail\"]').click()");
    await waitFor("!document.querySelector('.asset-panel')", 'detail closed');
    await pause(500);
    // Selection centred this asset. Exercise a real canvas click to reopen it.
    const point = await evaluate("(() => {const r=document.querySelector('.maplibregl-canvas').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()");
    await call('Input.dispatchMouseEvent', { type: 'mousePressed', ...point, button: 'left', clickCount: 1 });
    await call('Input.dispatchMouseEvent', { type: 'mouseReleased', ...point, button: 'left', clickCount: 1 });
    await waitFor("document.querySelector('.asset-panel')", 'canvas click-through');
    assert((await evaluate("document.querySelector('.asset-panel h2').textContent")).includes(`#${expectedIds[0]}`));
    await evaluate("document.querySelector('[aria-label=\"Close asset detail\"]').click()");
    await evaluate("document.querySelector('.filters .text-button').click()");
    await waitFor("document.querySelector('.list-heading h2')?.textContent === 'Assets by risk'", 'reset');
    await evaluate("document.querySelector('.fit-map').click()");
    await pause(300);
    fs.mkdirSync('.tooling', { recursive: true });
    const desktop = await call('Page.captureScreenshot');
    fs.writeFileSync('.tooling/m4-dashboard.png', Buffer.from(desktop.data, 'base64'));
    await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await evaluate('window.scrollTo(0,0)');
    await pause(300);
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false, 'Mobile horizontal overflow');
    await evaluate("document.querySelector('.filters .primary').click(); document.querySelector('.asset-row').click()");
    await waitFor("document.querySelector('.asset-panel .factors li')", 'mobile explanations');
    assert(await evaluate("(() => {const r=document.querySelector('.asset-panel .factor').getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight})()"), 'Mobile explanation must be in view');
    const mobile = await call('Page.captureScreenshot');
    fs.writeFileSync('.tooling/m4-mobile.png', Buffer.from(mobile.data, 'base64'));
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false, 'Detail panel horizontal overflow');
    assert.deepEqual(exceptions, [], 'Browser runtime exceptions');
    assert(await evaluate("document.querySelector('.map-status').textContent.startsWith('Map ready')"), 'Map must remain healthy after interactions');
    console.log('PASS canvas click-through, reset, mobile layout and explanations; no runtime exceptions.');
  } finally {
    ws.close();
    await fetch(`${debugUrl}/json/close/${page.id}`);
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
