// Optional browser smoke tests. Requires Playwright (outside the runtime dependency set).
// PLAYWRIGHT_MODULE=/path/to/playwright CHROME_BIN=/usr/bin/google-chrome node tests/test_tree_browser.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const repo = path.resolve(__dirname, '..');
const out = fs.mkdtempSync(path.join(os.tmpdir(), 'rsi-tree-browser-'));
const start = '2026-01-01T00:00:00Z';
const injection = '</script><img src=x onerror="window.__injected=true">';
const fixture = {
  experiment: 'Explorer regression', task: 'kernel-optimization', score_key: 'latency_ms', higher_is_better: false,
  generated_at: start, experiment_started_at: start, official_seedset: 'validation', final_seedset: 'test',
  runner: 'script:test', utility: 'script:test', root_score: 10, best: 'n002',
  search: {max_nodes: 12, max_parallel: 2, depth: 4}, state: {status: 'running'}, reference_scores: {reference: 2},
  insights: 'Shared-memory reuse helped. [n002]', deadends: 'Invalid numerical output. [n003]',
  wiki: 'WIKI REVISION: earlier claim superseded; counterevidence retained.',
  monitor_notes: 'MONITOR: task completed, validated, model wake 1.',
  nodes: [
    {id: 'root', parent: null, x: 1, y: 0, depth: 0, status: 'done', verdict: 'baseline', score: 10, title: 'Baseline', summary: 'Original kernel'},
    {id: 'n001', parent: 'root', x: 0, y: 1, depth: 1, status: 'done', verdict: 'no_change', score: 12, delta_parent: -2, title: 'Change block layout', summary: 'No improvement', finished_order: 2},
    {id: 'n002', parent: 'root', x: 1, y: 1, depth: 1, status: 'done', verdict: 'improved', score: 7, delta_parent: 3, title: 'Use shared memory', summary: 'Reduced redundant loads', finished_order: 1,
      proposals: [{title: 'Tune tile size', hypothesis: 'Try a larger tile', risk: 'Register pressure'}],
      docs: {thinking: 'THINKING EVIDENCE: compared alternatives.', analysis: 'ANALYSIS EVIDENCE: within noise.', handoff: 'HANDOFF EVIDENCE', progress_tail: 'Checkpoint 1: pass', summary_md: '## Git log\n```\nabc123 Use shared memory\n```\n```\nkernel.cu | 12 ++--\n```'}},
    {id: 'n003', parent: 'n002', x: 0.5, y: 2, depth: 2, status: 'failed', verdict: 'failed', score: -999, title: 'Incorrect fast kernel', failure: 'Correctness failed', diagnosis: {cause: 'Out of bounds', advice: 'Fix indexing'}, finished_order: 3},
    {id: 'n004', parent: 'n002', x: 1.5, y: 2, depth: 2, status: 'evaluating', score: null, title: 'Tune tile size', retry_of: 'n003'},
    {id: 'n005', parent: 'root', x: 2.5, y: 1, depth: 1, status: 'running', score: null, title: 'Vectorized loads'},
    {id: 'n006', parent: 'n005', x: 2.5, y: 2, depth: 2, status: 'planned', score: null, title: injection, hypothesis: injection},
  ].map((n, i) => ({created_at: start, started_at: start, duration_s: 30 + i, commit: 'abcdef1234567890', hypothesis: 'Improve memory access', finished_at: ['done', 'failed'].includes(n.status) ? `2026-01-01T00:0${i}:00Z` : null, ...n})),
};
function render(data, name, external = false) {
  const html = execFileSync('python3', ['-c', 'import sys,json; from pi_rsi.render import render_html; print(render_html(json.load(sys.stdin), external=' + (external ? 'True' : 'False') + '))'], {cwd: repo, input: JSON.stringify(data), encoding: 'utf8', maxBuffer: 8 * 1024 * 1024});
  const file = path.join(out, name); fs.writeFileSync(file, html); return pathToFileURL(file).href;
}
(async () => {
  const browser = await chromium.launch({headless: true, ...(process.env.CHROME_BIN ? {executablePath: process.env.CHROME_BIN} : {}), args: ['--no-sandbox']});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, colorScheme: 'light'});
  const page = await context.newPage();
  const errors = [], network = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
  try {
    await page.goto(render(fixture, 'fixture.html'));
    await page.waitForSelector('#tree .node');
    assert.equal(await page.locator('#tree .node').count(), 7);
    assert.ok(await page.evaluate(() => {
      const canvas = document.getElementById('treewrap').getBoundingClientRect();
      const panel = document.querySelector('.tree-panel').getBoundingClientRect();
      const lower = document.querySelector('.lower').getBoundingClientRect();
      return canvas.bottom <= panel.bottom && panel.bottom <= lower.top;
    }), 'tree canvas must remain inside its panel without overlapping the chart');
    assert.equal(await page.locator('#tree .node.selected').getAttribute('data-id'), 'n002');
    assert.equal(await page.locator('#tree .node.best-path').count(), 2);
    assert.equal(await page.locator('#chart .score-dot').count(), 2); // excludes root and failed -999
    assert.equal(await page.evaluate(() => window.__injected), undefined);
    assert.match(await page.locator('#detail').innerText(), /Code changes/i);
    assert.match(await page.locator('#detail').innerText(), /kernel.cu/);
    await page.click('[data-tab="thinking"]');
    assert.match(await page.locator('#detail-body').innerText(), /THINKING EVIDENCE/);
    await page.click('[data-tab="analysis"]');
    assert.match(await page.locator('#detail-body').innerText(), /ANALYSIS EVIDENCE/);
    await page.click('[data-t="wiki"]');
    assert.match(await page.locator('#idtext').innerText(), /counterevidence retained/);
    await page.click('[data-t="monitor_notes"]');
    assert.match(await page.locator('#idtext').innerText(), /model wake 1/);
    await page.click('[data-t="insights"]');
    await page.click('[data-tab="overview"]');
    const view = () => page.locator('#tree').getAttribute('viewBox');
    const before = await view(); await page.click('#zoom-in'); assert.notEqual(await view(), before);
    await page.click('#fit-tree');
    const region = await page.locator('#treewrap').boundingBox();
    const beforeDrag = await view();
    await page.mouse.move(region.x + 20, region.y + 20); await page.mouse.down();
    await page.mouse.move(region.x + 80, region.y + 70, {steps: 5}); await page.mouse.up();
    assert.notEqual(await view(), beforeDrag);
    const beforeWheel = await view(); await page.mouse.wheel(0, -100);
    await page.waitForFunction(previous => document.getElementById('tree').getAttribute('viewBox') !== previous, beforeWheel);
    await page.click('#fit-tree');
    await page.locator('#tree .node[data-id="n001"]').click();
    assert.equal(await page.locator('#tree .node.selected').getAttribute('data-id'), 'n001');
    assert.equal(await page.locator('#tree .node.ancestor').count(), 2);
    await page.click('#focus-best');
    assert.equal(await page.locator('#tree .node.selected').getAttribute('data-id'), 'n002');
    await page.click('#detail [data-tab="handoff"]');
    assert.match(await page.locator('#detail-body').innerText(), /HANDOFF EVIDENCE/);
    await page.click('#detail [data-tab="overview"]');
    await page.click('[data-axis="time"]'); assert.match(await page.locator('#chart-note').innerText(), /wall time/);
    await page.click('[data-axis="nodes"]');
    await page.locator('#chart [data-node="n003"]').click();
    await page.click('#detail [data-tab="failure"]');
    assert.match(await page.locator('#detail-body').innerText(), /Out of bounds/);
    await page.selectOption('#status-filter', 'failed'); assert.equal(await page.locator('#table tbody tr[data-id]').count(), 1);
    await page.selectOption('#status-filter', 'all');
    await page.fill('#node-search', 'shared'); assert.equal(await page.locator('#table tbody tr[data-id]').count(), 1);
    await page.locator('#table [data-select="n002"]').click();
    assert.equal(await page.locator('#tree .node.selected').getAttribute('data-id'), 'n002');
    await page.fill('#node-search', 'nothing matches'); assert.match(await page.locator('#table').innerText(), /No experiments match/);
    await page.fill('#node-search', '');
    await page.click('[data-t="deadends"]'); assert.match(await page.locator('#idtext').innerText(), /Invalid numerical/);
    await page.click('#theme-toggle'); assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    await page.screenshot({path: path.join(out, 'desktop-dark.png'), fullPage: true});
    await page.click('#theme-toggle'); assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
    await page.click('#fit-tree');
    await page.locator('#tree [data-id="n001"]').focus(); await page.keyboard.press('Enter');
    assert.equal(await page.locator('#tree .node.selected').getAttribute('data-id'), 'n001');
    await page.screenshot({path: path.join(out, 'desktop-light.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await page.click('#fit-tree');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'mobile horizontal overflow');
    await page.screenshot({path: path.join(out, 'mobile.png'), fullPage: true});

    await page.goto(render({...fixture, nodes: [], best: null, root_score: null}, 'empty.html'));
    assert.match(await page.locator('#tree').textContent(), /No experiments/);
    assert.match(await page.locator('#chart').textContent(), /No valid/);
    await page.goto(render({...fixture, nodes: [fixture.nodes[0]], best: 'root'}, 'baseline.html'));
    assert.equal(await page.locator('#chart .best-curve').count(), 1);
    assert.equal(await page.locator('[data-axis="time"]').isDisabled(), true);

    // Static-hosting bundle: no inline JS; same interaction code.
    fs.writeFileSync(path.join(out, 'data.js'), 'window.__RSI_DATA__=' + JSON.stringify(fixture).replaceAll('<', '\\u003c') + ';');
    fs.copyFileSync(path.join(repo, 'pi_rsi/templates/tree.js'), path.join(out, 'tree.js'));
    await page.goto(render(fixture, 'external.html', true));
    assert.equal(await page.locator('script:not([src])').count(), 0);
    assert.equal(await page.locator('#tree .node').count(), 7);
    await page.click('#theme-toggle');
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    assert.deepEqual(errors, [], 'browser console errors'); assert.deepEqual(network, [], 'unexpected network dependency');
    console.log('BROWSER TESTS OK:', out);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
