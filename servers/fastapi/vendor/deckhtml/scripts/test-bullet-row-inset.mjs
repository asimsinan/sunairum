/**
 * O30: a bullet row keeps the gap between its marker and its words.
 *
 * A flex row that owns text is a block-level box: it starts its own line, and
 * the dot it lays out before that text sets a left inset for that line only.
 * Merged into the parent's text box the inset is unexpressible — one `marL`
 * cannot describe both the parent's copy at zero and this row's copy at 17px —
 * so the dot exported touching its own words, and the row's leading drifted to
 * the parent's. Kept as its own measured box, both survive.
 *
 * Run: npm run build && node scripts/test-bullet-row-inset.mjs
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

const HTML = `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=1280">
<style>
 html,body{margin:0;width:1280px;height:720px;background:#1A365D;
   font-family:'Source Sans 3',sans-serif;color:#fff}
 .slide{position:relative;width:1280px;height:720px}
 .band{position:absolute;left:92px;top:560px;width:328px;font-size:15px;line-height:20px}
 .row{display:flex;align-items:center;gap:9px;margin-top:8px;font-size:16px;font-weight:600}
 .dot{width:8px;height:8px;border-radius:50%;background:#63B3ED;flex:none}
</style></head><body><div class="slide">
 <div class="band">
  Her iterasyonda karar alani yeniden yoklanir.
  <div class="row">
   <span class="dot" aria-hidden="true" data-pptx-kind="decoration"></span>
   Cok sayida konum, dogrudan degerlendirme yerine
  </div>
 </div>
</div></body></html>`;

const tmp = fs.mkdtempSync(path.join(fs.realpathSync(process.env.TMPDIR || '/tmp'), 'deckhtml-bullet-'));
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
const EMU_PER_PX = 914400 / 128;

const shapes = [...xml.matchAll(/<p:sp>[\s\S]*?<\/p:sp>/g)]
  .map((m) => m[0])
  .filter((sp) => sp.includes('<a:t>'))
  .map((sp) => {
    const off = /<a:off x="(-?\d+)" y="(-?\d+)"\/><a:ext cx="(\d+)" cy="(\d+)"/.exec(sp);
    return {
      x: off ? +(Number(off[1]) / EMU_PER_PX).toFixed(1) : NaN,
      text: [...sp.matchAll(/<a:t>([^<]*)<\/a:t>/g)].map((t) => t[1]).join(''),
      wrap: /wrap="(\w+)"/.exec(/<a:bodyPr([^>]*)>/.exec(sp)[1])?.[1],
    };
  });

const parent = shapes.find((s) => s.text.includes('iterasyonda'));
const bullet = shapes.find((s) => s.text.includes('Cok sayida'));
assert.ok(parent, `parent copy missing: ${JSON.stringify(shapes)}`);
assert.ok(bullet, `bullet copy missing: ${JSON.stringify(shapes)}`);
assert.notEqual(parent, bullet, 'the bullet row must not be merged into the parent text box');

// The dot occupies 8px and the flex gap 9px, so the row's copy starts 17px in.
assert.ok(
  bullet.x - parent.x >= 15 && bullet.x - parent.x <= 19,
  `bullet copy should clear its marker by ~17px, got ${bullet.x - parent.x}px`
);

// Splitting must not cost the drift guarantee.
for (const shape of [parent, bullet]) {
  assert.equal(shape.wrap, 'none', `text left re-flowable: ${shape.text.slice(0, 30)}`);
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log('O30 bullet row inset: ok');
process.exit(0);
