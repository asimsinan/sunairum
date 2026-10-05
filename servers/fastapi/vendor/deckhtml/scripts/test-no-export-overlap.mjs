/**
 * O31: the conversion must not put text on top of other text.
 *
 * A right-aligned label needing 42px more width grew *leftward* through the box
 * beside it, because the growth bound saw pill peers only and `roomLeft`
 * defaults to the slide edge when no bound is given. Three overlaps the HTML
 * did not have appeared in a twelve-slide export. Growth is now bounded by text
 * neighbours in both directions.
 *
 * Run: npm run build && node scripts/test-no-export-overlap.mjs
 */
import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'node:url';
import { convertHtmlToPptx } from '../dist/index.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fastapiFonts = path.resolve(root, '../../assets/fonts');
if (fs.existsSync(fastapiFonts)) process.env.DECKHTML_FONTS_DIR = fastapiFonts;

// A right-aligned label whose copy needs more width than its box, with a text
// box immediately to its left: the only free space is leftward, and taking it
// would print one over the other.
const HTML = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=1280">
<style>
 html,body{margin:0;width:1280px;height:720px;background:#fff;
   font-family:'Source Sans 3',sans-serif}
 .slide{position:relative;width:1280px;height:720px}
 .left{position:absolute;left:820px;top:250px;width:180px;height:36px;
   font-size:17px;line-height:36px;background:#EBF4FB}
 .right{position:absolute;left:1014px;top:250px;width:158px;height:36px;
   font-size:17px;line-height:36px;text-align:right;font-weight:700}
</style></head><body><div class="slide">
 <div class="left">Neighbouring copy</div>
 <div class="right">A label that needs more width</div>
</div></body></html>`;

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'deckhtml-overlap-'));
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

const area = (a, b) =>
  Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x))
  * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));

const text = (result.shapeMap ?? []).filter((s) => s.type === 'text' && s.html && s.pptx);
assert.ok(text.length >= 2, `expected both text shapes, saw ${text.length}`);

const PX_PER_INCH = 128;
for (let i = 0; i < text.length; i += 1) {
  for (let j = i + 1; j < text.length; j += 1) {
    const authored = area(text[i].html, text[j].html);
    const exported = area(
      { x: text[i].pptx.x * PX_PER_INCH, y: text[i].pptx.y * PX_PER_INCH,
        w: text[i].pptx.w * PX_PER_INCH, h: text[i].pptx.h * PX_PER_INCH },
      { x: text[j].pptx.x * PX_PER_INCH, y: text[j].pptx.y * PX_PER_INCH,
        w: text[j].pptx.w * PX_PER_INCH, h: text[j].pptx.h * PX_PER_INCH },
    );
    assert.ok(
      exported <= authored + 20,
      `export added ${(exported - authored).toFixed(0)}px² of overlap between `
      + `${text[i].elementId} and ${text[j].elementId}`
    );
  }
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log('O31 no export overlap: ok');
process.exit(0);
