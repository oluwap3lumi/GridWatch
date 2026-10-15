// Node 24 built-ins; a running scored stack and local Chromium CDP are required.
// --retrain appends one real model run while the same page and containers stay open.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { execFile, spawn } = require('node:child_process');
const { promisify } = require('node:util');
const execute = promisify(execFile);
const debugUrl = process.env.GRIDWATCH_BROWSER_DEBUG_URL || 'http://localhost:9223';
const webUrl = process.env.GRIDWATCH_WEB_URL || 'http://localhost:5173';
const docker = process.platform === 'win32' ? 'docker.exe' : 'docker';
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function containers() {
  const result = await execute(docker, ['compose', 'ps', '--quiet', 'api', 'web'], { windowsHide: true });
  const ids = result.stdout.trim().split(/\s+/).sort();
  assert.equal(ids.length, 2, 'Both application containers must be running');
  return ids;
}
async function train() {
  await new Promise((resolve, reject) => {
    const child = spawn(process.platform === 'win32' ? 'make.exe' : 'make', ['train'], { stdio: 'inherit', windowsHide: true });
    child.on('error', reject);
    child.on('exit', (code) => code === 0 ? resolve() : reject(new Error(`make train exited ${code}`)));
  });
}

async function main() {
  const beforeContainers = await containers();
  const created = await fetch(`${debugUrl}/json/new?about:blank`, { method: 'PUT' });
  assert(created.ok, 'Local Chromium DevTools endpoint required');
  const page = await created.json();
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  let id = 0;
  const pending = new Map();
  const exceptions = [];
  ws.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const item = pending.get(message.id);
      if (!item) return;
      clearTimeout(item.timer);
      pending.delete(message.id);
      message.error ? item.reject(new Error(JSON.stringify(message.error))) : item.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails);
  });
  function call(method, params = {}) {
    return new Promise((resolve, reject) => {
      const next = ++id;
      const timer = setTimeout(() => { pending.delete(next); reject(new Error(`CDP timeout: ${method}`)); }, 20000);
      pending.set(next, { resolve, reject, timer });
      ws.send(JSON.stringify({ id: next, method, params }));
    });
  }
  async function evaluate(expression) {
    const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function waitFor(expression, label, timeout = 45000) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) { if (await evaluate(`Boolean(${expression})`)) return; await pause(150); }
    throw new Error(`Timed out: ${label}`);
  }
  const api = (path) => evaluate(`(async()=>{const r=await fetch(${JSON.stringify('/api/v1' + path)});if(!r.ok)throw new Error('API failed '+r.status);return r.json()})()`);
  const click = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  try {
    await call('Runtime.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1200, deviceScaleFactor: 1, mobile: false });
    await call('Page.navigate', { url: `${webUrl}/#model` });
    await waitFor("document.querySelector('#model-version') && document.querySelector('.history-card tbody tr')", 'model and history');
    const origin = await evaluate('performance.timeOrigin');
    const before = await api('/model');
    const beforeSummary = await api('/risk/summary');
    assert(beforeSummary.scoring, 'Existing scored demo corpus required');
    let expected = before.model_version;
    if (process.argv.includes('--retrain')) {
      console.log(`Training while browser stays open; previous available model ${expected}`);
      await train();
      const available = await api('/model');
      assert.notEqual(available.model_version, before.model_version, 'Training must register a new version');
      assert.equal(available.scored_model_version, beforeSummary.scoring.model_version, 'Training alone must preserve saved scores');
      expected = available.model_version;
      await click('.intro .secondary');
      await waitFor(`document.querySelector('#model-version')?.textContent === ${JSON.stringify(expected)}`, 'new model after refresh');
      assert((await evaluate("document.querySelector('.model-status').textContent")).includes('A newer passing model is available'));
      await waitFor(`document.querySelector('.history-card tbody tr')?.textContent.includes(${JSON.stringify(expected)})`, 'new history record');
      console.log(`PASS running model page sees newly trained version ${expected}; saved scores remain unchanged.`);
    }
    assert.equal(await evaluate("document.querySelectorAll('.importance-list li').length"), before.features.length);
    await click('.page-nav a[href="#map"]');
    await waitFor("document.querySelector('.map-status')?.textContent.startsWith('Map ready')", 'risk map');
    await click('.filters .primary');
    await pause(200);
    const assetId = await evaluate("Number(document.querySelector('.asset-row strong').textContent.split('#')[1])");
    await click('.asset-row');
    await waitFor("document.querySelector('.asset-panel .model-stamp code')", 'selected asset');
    assert.equal(await evaluate("document.querySelector('.asset-panel .model-stamp code').textContent"), beforeSummary.scoring.model_version);
    await click('.rescore-button');
    await waitFor("document.querySelector('.rescore-button').disabled", 'pending rescore');
    await waitFor("document.querySelector('.rescore-message')?.textContent.includes('Views refreshed.')", 'saved scores and refreshed views', 180000);
    await waitFor(`document.querySelector('.asset-panel .model-stamp code')?.textContent === ${JSON.stringify(expected)}`, 'selected explanation version');
    const afterSummary = await api('/risk/summary');
    assert.equal(afterSummary.scoring.model_version, expected);
    assert.notEqual(afterSummary.scoring.scored_at, beforeSummary.scoring.scored_at, 'Actual rescoring must update the saved batch');
    assert((await evaluate("document.querySelector('.asset-panel h2').textContent")).includes(`#${assetId}`));
    const detail = await api(`/assets/${assetId}`);
    assert.equal(detail.asset.properties.risk.scored_at, afterSummary.scoring.scored_at);
    assert(detail.asset.properties.risk.top_factors.length > 0);
    console.log(`PASS real rescore updates ${afterSummary.scored_assets} assets and selected #${assetId} without leaving the map.`);
    await click('.page-nav a[href="#model"]');
    await waitFor(`document.querySelector('#scored-model-version')?.textContent === ${JSON.stringify(expected)}`, 'updated model status');
    assert.equal(await evaluate('performance.timeOrigin'), origin, 'Page must not reload');
    assert.deepEqual(await containers(), beforeContainers, 'API and web containers must not restart');
    await evaluate('window.scrollTo(0,0)');
    await pause(200);
    fs.mkdirSync('.tooling', { recursive: true });
    const desktop = await call('Page.captureScreenshot');
    fs.writeFileSync('.tooling/m5-model.png', Buffer.from(desktop.data, 'base64'));
    await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await pause(200);
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false, 'Mobile model overflow');
    const mobile = await call('Page.captureScreenshot');
    fs.writeFileSync('.tooling/m5-mobile.png', Buffer.from(mobile.data, 'base64'));
    assert.deepEqual(exceptions, [], 'Browser runtime exceptions');
    console.log(`PASS model status, history, mobile layout; page origin ${origin} and API/web container IDs unchanged.`);
  } finally { ws.close(); await fetch(`${debugUrl}/json/close/${page.id}`); }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
