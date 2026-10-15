// Run with: node --test tests/test_tree_model.cjs (no npm dependencies).
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {bestNode, chartSeries, ancestry, completionOrder} = require('../pi_rsi/templates/tree.js');
const start = '2026-01-01T00:00:00Z';
const node = (id, score, status = 'done', extra = {}) => ({id, score, status, parent: 'root', created_at: start, finished_at: '2026-01-01T00:00:10Z', ...extra});
const data = (nodes, higher = true) => ({nodes, higher_is_better: higher, experiment_started_at: start});

test('failed, pending, evaluating and nonfinite scores never become best', () => {
  const nodes = [node('root', 10), node('n001', 999, 'failed'), node('n002', Infinity), node('n003', NaN), node('n004', 777, 'evaluating'), node('n005', 500, 'planned'), node('n006', 9999, 'incomplete')];
  assert.equal(bestNode(nodes, true).id, 'root');
  const series = chartSeries(data(nodes));
  assert.equal(series.baseline, 10);
  assert.ok(series.points.every(p => p.score === null && p.best === 10));
});

test('baseline is the initial incumbent even if every experiment is worse', () => {
  const series = chartSeries(data([node('root', 10), node('n001', 3), node('n002', 8)]));
  assert.deepEqual(series.points.map(p => p.best), [10, 10]);
  assert.deepEqual(series.points.map(p => p.x), [1, 2]);
});

test('valid measurement survives pending documentation; quarantine excludes it', () => {
  const pending = node('n001',12,'incomplete',{measurement:{state:'validated',score:12}});
  assert.equal(bestNode([node('root',10),pending],true).id,'n001');
  pending.measurement.state='invalid';
  assert.equal(bestNode([node('root',10),pending],true).id,'root');
});

test('lower-is-better, zeros and ties are valid', () => {
  const nodes = [node('root', 1), node('n001', 0), node('n002', 0), node('n003', 0.5)];
  assert.equal(bestNode(nodes, false).id, 'n001');
  assert.deepEqual(chartSeries(data(nodes, false)).points.map(p => p.best), [0, 0, 0]);
});

test('explicit completion order breaks same-second ties', () => {
  const nodes = [node('root', 0), node('n001', 3, 'done', {finished_order: 2}), node('n002', 7, 'done', {finished_order: 1})];
  const series = chartSeries(data(nodes));
  assert.deepEqual(series.points.map(p => p.node.id), ['n002', 'n001']);
  assert.deepEqual(series.points.map(p => p.best), [7, 7]);
  assert.ok(completionOrder(node('old', 1), nodes[1]) < 0);
});

test('wall clock uses experiment origin, not resumed process start', () => {
  const d = data([node('root', 5), node('n001', 7), node('n002', 8, 'done', {finished_at: '2026-01-01T00:02:00Z'})]);
  d.state = {started_at: Date.parse('2026-01-01T00:01:00Z') / 1000};
  assert.deepEqual(chartSeries(d, 'time').points.map(p => p.x), [10, 120]);
});

test('missing timestamps disable time axis rather than invent elapsed times', () => {
  const series = chartSeries(data([node('root', 3), node('n001', 4, 'done', {finished_at: null})]), 'time');
  assert.equal(series.timeAvailable, false);
  assert.equal(series.axis, 'nodes');
});

test('empty and baseline-only experiments render valid series', () => {
  assert.equal(bestNode([], true), null);
  assert.deepEqual(chartSeries(data([])).points, []);
  assert.equal(chartSeries(data([node('root', 0)])).baseline, 0);
});

test('ancestry tolerates orphans and corrupt cycles', () => {
  const map = {a: {parent: 'b'}, b: {parent: 'a'}, c: {parent: 'missing'}};
  assert.deepEqual([...ancestry('a', map)], ['a', 'b']);
  assert.deepEqual([...ancestry('c', map)], ['c']);
});
