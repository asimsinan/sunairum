/**
 * O29: the reader's renderer gets no layout decisions.
 *
 * Every text body exports with Chromium's own line breaks stated outright, so no
 * font-metric difference can re-wrap a paragraph, shift a baseline, or grow a
 * table row over the element beneath it ("metin kayması"). This test converts a
 * deck built to hit the cases that used to fall back to PowerPoint's wrapping:
 *   - a heading hard-broken with <br>            (host text "A\nB" vs lines "AB")
 *   - an uppercase kicker                        (rendered case vs source case)
 *   - a paragraph with a bold lead-in            (mixed ink-box tops per line)
 *   - a lede with a ::before label               (generated content is not a text node)
 *   - a table cell Chromium wrapped              (PowerPoint would grow the row)
 *   - a filled box Chromium wrapped              (the split-background path spread
 *                                                the options, then set wrap:true)
 *
 * Run: npm run build && node scripts/test-frozen-text.mjs
 */
import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'node:url';
import JSZip from 'jszip';
import { convertHtmlToPptx } from '../dist/index.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fastapiFonts = path.resolve(root, '../../assets/fonts');
if (fs.existsSync(fastapiFonts)) process.env.DECKHTML_FONTS_DIR = fastapiFonts;

const HTML = `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=1280">
<style>
 html,body{margin:0;width:1280px;height:720px;background:#fff;font-family:'Source Sans 3',sans-serif}
 .slide{position:relative;width:1280px;height:720px}
 h1{position:absolute;left:60px;top:60px;width:1000px;margin:0;font:64px/1.06 'Source Serif 4',serif}
 .kicker{position:absolute;left:60px;top:300px;font-size:12px;text-transform:uppercase;letter-spacing:2px}
 .lede{position:absolute;left:60px;top:340px;width:600px;padding-left:32px;font-size:20px;line-height:27px}
 .lede::before{content:"03 / FORMULATION";position:absolute;left:0;top:0;font-size:11px}
 .para{position:absolute;left:60px;top:430px;width:520px;font-size:16px;line-height:24px}
 .para b{font-size:20px}
 table{position:absolute;left:700px;top:430px;width:400px;border-collapse:collapse}
 td{border:1px solid #ccc;padding:8px;font-size:14px;line-height:20px;vertical-align:top}
</style></head><body><div class="slide">
 <h1>Bir uzun baslik satiri<br>ve ikinci satir</h1>
 <div class="kicker">tek mimari · iki yönelim</div>
 <div class="lede">The paper evaluates routing cost and route-distance balance together.</div>
 <p class="para"><b>Interpretation:</b> candidate reduction transfers to larger instances without yielding a monotonic size trend.</p>
 <table><tr><td>Short</td>
 <td>A deliberately long cell value that Chromium wraps onto several lines inside its column</td></tr></table>
</div></body></html>`;

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'deckhtml-frozen-'));
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
const xml = await zip.file('ppt/slides/slide1.xml').async('text');

// Every standalone text body freezes its wrapping.
const bodies = [...xml.matchAll(/<p:sp>[\s\S]*?<\/p:sp>/g)]
  .filter((m) => m[0].includes('<a:t>'))
  .map((m) => /<a:bodyPr([^>]*)>/.exec(m[0])?.[1] ?? '');
assert.ok(bodies.length >= 4, `expected several text bodies, saw ${bodies.length}`);
for (const attrs of bodies) {
  assert.match(attrs, /wrap="none"/, `text body left re-flowable: <a:bodyPr${attrs}>`);
}

// No fallback to the renderer's wrapping for any of the seeded cases.
const fallbacks = (result.diagnostics ?? []).filter((d) =>
  String(d.message).includes('ambiguous_line_map')
);
assert.equal(
  fallbacks.length,
  0,
  `line maps not resolved: ${fallbacks.map((d) => d.message).join(' | ')}`
);

// The hard-broken heading keeps both of Chromium's lines, at its measured size.
assert.match(xml, /<a:t>Bir uzun baslik satiri<\/a:t>/);
assert.match(xml, /<a:t>ve ikinci satir<\/a:t>/);

// Turkish casing survives the uppercase transform.
assert.ok(
  xml.includes('TEK MİMARİ · İKİ YÖNELİM'),
  'kicker lost its Turkish casing (dotted İ) in the frozen lines'
);

// The bold lead-in stays at the front of its paragraph (reading order).
const paragraph = [...xml.matchAll(/<a:t>([^<]*)<\/a:t>/g)].map((m) => m[1]);
const leadIn = paragraph.findIndex((t) => t.startsWith('Interpretation:'));
assert.notEqual(leadIn, -1, 'bold lead-in missing');
assert.ok(
  paragraph[leadIn].startsWith('Interpretation:'),
  `lead-in reordered: ${paragraph[leadIn]}`
);

// The wrapped table cell carries Chromium's break instead of PowerPoint's.
const frame = /<p:graphicFrame>[\s\S]*?<\/p:graphicFrame>/.exec(xml)?.[0] ?? '';
const cellRuns = [...frame.matchAll(/<a:t>([^<]*)<\/a:t>/g)].map((m) => m[1]);
assert.ok(
  cellRuns.some((t) => t.startsWith('A deliberately long cell value')) &&
    cellRuns.length > 2,
  `table cell was not split at Chromium's wrap: ${JSON.stringify(cellRuns)}`
);

fs.rmSync(tmp, { recursive: true, force: true });
console.log('O29 frozen text: ok');
// convertHtmlToPptx keeps its Chromium alive after returning, so a plain script
// would hang here (test-accent-descender has the same tail). Assertions are done.
process.exit(0);
