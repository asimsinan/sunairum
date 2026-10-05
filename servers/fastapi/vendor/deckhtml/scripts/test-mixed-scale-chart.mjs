/**
 * O32: a dual-axis chart's series can be told apart, and its axes say nothing
 * misleading.
 *
 * Cost (~1262) beside CV (~0.34) cannot share a linear axis, so the payload is
 * restructured into two series on two axes. Two problems followed. pptxgenjs
 * colours a multi-chart's sub-charts from the start of its default list each
 * time, so both series were drawn in the same red -- one bar hiding another,
 * and two identical legend swatches. And two value axes at four orders of
 * magnitude apart are two rulers printed over each other; on the deck that
 * prompted this they stacked "1400 / 1.2 / 0.4" down the left edge of a card.
 * The HTML preview draws no axis for a mixed-scale chart: it paints the bars
 * and prints the numbers on them, and the export now matches that.
 *
 * Run: npm run build && node scripts/test-mixed-scale-chart.mjs
 */
import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'node:url';
import JSZip from 'jszip';
import { convertHtmlToPptx } from '../dist/index.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fastapiFonts = path.resolve(root, '../../assets/fonts');
if (fs.existsSync(fastapiFonts)) process.env.DECKHTML_FONTS_DIR = fastapiFonts;

// The payload carries no colours: an export made before the deck palette was
// threaded through must still produce a legible chart.
const payload = JSON.stringify({
  type: 'column',
  categories: ['Cost', 'CV'],
  series: [{ name: 'Value', values: [1261.9, 0.3439] }],
}).replace(/"/g, '&quot;');

const HTML = `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=1280">
<style>
 html,body{margin:0;width:1280px;height:720px;background:#fff;
   font-family:'Source Sans 3',sans-serif}
 .slide{position:relative;width:1280px;height:720px}
</style></head><body><div class="slide">
 <div data-pptx="chart" data-chart-id="c1" data-chart-payload="${payload}"
   style="position:absolute;left:80px;top:120px;width:420px;height:300px;">
   <div data-sunairum-chart-preview="1" data-pptx-kind="ignore">x</div>
 </div>
</div></body></html>`;

const tmp = fs.mkdtempSync(
  path.join(fs.realpathSync(process.env.TMPDIR || '/tmp'), 'deckhtml-chart-')
);
const input = path.join(tmp, 'slide_01.html');
fs.writeFileSync(input, HTML, 'utf8');

const result = await convertHtmlToPptx({
  inputs: [input],
  allowLocalResources: true,
  quiet: true,
  layoutFaithful: true,
  slideTransitions: false,
  animations: false,
});

const zip = await JSZip.loadAsync(result.data);
const chartFile = Object.keys(zip.files).find((n) => /ppt\/charts\/chart\d+\.xml$/.test(n));
assert.ok(chartFile, `no chart part emitted: ${Object.keys(zip.files).join(', ')}`);
const xml = await zip.file(chartFile).async('text');

const seriesNames = [...xml.matchAll(/<c:tx>[\s\S]*?<c:v>([^<]*)<\/c:v>/g)].map((m) => m[1]);
assert.deepEqual(
  seriesNames.slice(0, 2).sort(),
  ['CV', 'Cost'],
  `mixed-scale categories were not promoted to series: ${seriesNames}`
);

const seriesColors = [...xml.matchAll(/<c:ser>[\s\S]*?<a:srgbClr val="(\w+)"/g)].map((m) => m[1]);
assert.ok(seriesColors.length >= 2, `no series colours found: ${xml.slice(0, 400)}`);
assert.notEqual(
  seriesColors[0],
  seriesColors[1],
  `both series drawn in ${seriesColors[0]} — one bar hides the other`
);

// Both value axes suppressed: with two incommensurable scales an axis ruler is
// not information, and the data labels carry the numbers instead.
const valAxDeletes = [...xml.matchAll(/<c:valAx>[\s\S]*?<c:delete val="([01])"/g)].map(
  (m) => m[1]
);
assert.ok(valAxDeletes.length >= 2, `expected two value axes, got ${valAxDeletes.length}`);
assert.ok(
  valAxDeletes.every((d) => d === '1'),
  `a mixed-scale chart still draws a value axis ruler: ${valAxDeletes}`
);
assert.ok(xml.includes('<c:dLbls>'), 'no data labels: the numbers are nowhere to be read');

// Each metric keeps its own category slot. Collapsing both onto one unnamed
// category drew the two bars at the same x, so the taller hid the shorter and
// the card showed one bar, a label reading "0", and a phantom "Series1".
const cats = [...xml.matchAll(/<c:cat>[\s\S]*?<\/c:cat>/g)]
  .flatMap((m) => [...m[0].matchAll(/<c:pt idx="\d+"><c:v>([^<]*)<\/c:v>/g)].map((p) => p[1]));
assert.ok(
  cats.includes('Cost') && cats.includes('CV'),
  `metrics did not keep their own category slots: ${JSON.stringify(cats)}`
);

// The slot a series does not occupy is blank, not zero: a zero draws a
// zero-height bar *and* its data label, printing a stray "0" beside the
// neighbour's real value.
const numericPts = [...xml.matchAll(/<c:val>[\s\S]*?<\/c:val>/g)].flatMap((m) =>
  [...m[0].matchAll(/<c:pt idx="\d+"><c:v>([^<]*)<\/c:v>/g)].map((p) => p[1])
);
assert.ok(
  !numericPts.includes('0'),
  `an unoccupied slot was written as 0 rather than left blank: ${JSON.stringify(numericPts)}`
);

// An axis that is hidden still decides the height of what sits on it. Left to
// auto-fit, renderers gave both axes the larger metric's range and the smaller
// series drew no bar at all -- its label was the only trace of it.
const axMaxima = [...xml.matchAll(/<c:valAx>[\s\S]*?<\/c:valAx>/g)].map((m) => {
  const hit = /<c:max val="([\d.]+)"\/>/.exec(m[0]);
  return hit ? Number(hit[1]) : null;
});
assert.ok(
  axMaxima.length >= 2 && axMaxima.every((v) => typeof v === 'number' && v > 0),
  `a value axis was left to auto-fit: ${JSON.stringify(axMaxima)}`
);
assert.ok(
  Math.max(...axMaxima) / Math.min(...axMaxima) > 100,
  `both axes were scaled to the same metric: ${JSON.stringify(axMaxima)}`
);

console.log('O32 mixed-scale chart: ok');
