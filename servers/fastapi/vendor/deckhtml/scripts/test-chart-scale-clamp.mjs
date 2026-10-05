/**
 * O27: mixed Cost/CV scales → dual-axis; chart hosts clamp below text bands.
 * Run: npm run build && node scripts/test-chart-scale-clamp.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { prepareChartPayload, isMixedScale } = require(
  path.join(root, 'dist/utils/chart-scale.js')
);
const { ElementConverter } = require(path.join(root, 'dist/converter.js'));
const { StyleEnhancementRegistry } = require(path.join(root, 'dist/enhancer/registry.js'));
const { setViewportPixels, pxToInchX, pxToInchY } = require(
  path.join(root, 'dist/utils/coordinate.js')
);

setViewportPixels(1280, 720);

assert.equal(isMixedScale([213199, 1.2517]), true);
assert.equal(isMixedScale([10, 20, 30]), false);

const prepared = prepareChartPayload({
  type: 'column',
  categories: ['Cost', 'CV'],
  series: [{ name: 'Value', values: [213199, 1.2517] }],
});
assert.equal(prepared.mixedScale, true);
assert.equal(prepared.dualAxis, true);
assert.equal(prepared.series.length, 2);
assert.equal(prepared.series[0].name, 'Cost');
assert.equal(prepared.series[1].name, 'CV');
assert.equal(prepared.series[0].secondary, false);
assert.equal(prepared.series[1].secondary, true);
assert.deepEqual(prepared.categories, ['']);

const multiSeries = prepareChartPayload({
  type: 'column',
  categories: ['A', 'B'],
  series: [
    { name: 'Cost', values: [200000, 210000] },
    { name: 'CV', values: [1.2, 0.55] },
  ],
});
assert.equal(multiSeries.dualAxis, true);
assert.equal(multiSeries.series.find((s) => s.name === 'CV')?.secondary, true);

const converter = new ElementConverter(new StyleEnhancementRegistry());
const bodyText = {
  type: 'text',
  id: 'body',
  x: 40,
  y: 120,
  width: 360,
  height: 220,
  styles: {},
};
converter.beginSlide(0, [bodyText], 0);

const box = {
  x: pxToInchX(40),
  y: pxToInchY(280),
  w: pxToInchX(360),
  h: pxToInchY(160),
};
const beforeY = box.y;
converter.clampChartAwayFromTextBands(box);
assert.ok(box.y > beforeY, 'chart top must move below overlapping text');
const textBottom = pxToInchY(120 + 220);
assert.ok(box.y + 0.01 >= textBottom, 'chart clears text band');

const chartEl = {
  type: 'chart',
  tag: 'div',
  x: 40,
  y: 280,
  width: 360,
  height: 160,
  styles: {},
  chartPayload: {
    type: 'column',
    categories: ['Cost', 'CV'],
    series: [{ name: 'Value', values: [213199, 1.2517] }],
  },
};
const converted = converter.convertElement(chartEl, 0, 0, 0);
const chart = converted.find((c) => c.type === 'chart');
assert.ok(chart, 'emits chart');
assert.equal(chart.options.dualAxis, true);
assert.ok(chart.options.y > beforeY - 0.01, 'converted chart clamped');

console.log('O27 chart scale + clamp: ok');
