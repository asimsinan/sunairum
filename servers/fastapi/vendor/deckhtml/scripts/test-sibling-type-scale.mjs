/**
 * O31: a row of identical chips exports at one type size.
 *
 * `preserveIdentityBox` was meant to mark objects whose box is a contract --
 * something the deck names and that semantic geometry QA measures. It was read
 * as `Boolean(element.elementId)`, and the inspector synthesises a structural
 * path (`dh-auto__body-1__...__span-2`) for *every* element, so the flag was
 * true of everything: the branch that widens a box to fit PowerPoint's slightly
 * wider metrics became dead code, and shrinking the font was the only response
 * left. Each element negotiated that alone, so four chips authored at one size
 * exported at 8.4pt, 6.5pt, 8.4pt and 8.4pt -- a reader sees random type sizes
 * in a row that is identical in the HTML.
 *
 * Run: npm run build && node scripts/test-sibling-type-scale.mjs
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

// Unclassed <li> siblings: their only identity is the synthesised path, which
// is exactly the case the old flag mishandled.
const HTML = `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=1280">
<style>
 html,body{margin:0;width:1280px;height:720px;background:#fff;
   font-family:'Source Sans 3',sans-serif;color:#1A202C}
 .slide{position:relative;width:1280px;height:720px}
 .rail{position:absolute;left:80px;top:200px;width:700px;
   display:flex;gap:12px;list-style:none;margin:0;padding:0}
 .rail li{border:1px solid #90CDF4;border-radius:8px;padding:8px 14px;
   font-size:16px;line-height:22px;font-weight:600;white-space:nowrap}
</style></head><body><div class="slide">
 <ul class="rail">
  <li>Ogrenilmis gosterimler</li>
  <li>Pareto aramasi</li>
  <li>Dinamik rotalama</li>
 </ul>
</div></body></html>`;

const tmp = fs.mkdtempSync(
  path.join(fs.realpathSync(process.env.TMPDIR || '/tmp'), 'deckhtml-peer-')
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
const xml = await zip.file('ppt/slides/slide1.xml').async('text');

const chips = [...xml.matchAll(/<p:sp>[\s\S]*?<\/p:sp>/g)]
  .map((m) => m[0])
  .filter((sp) => /Ogrenilmis|Pareto|Dinamik/.test(sp))
  .map((sp) => ({
    text: [...sp.matchAll(/<a:t>([^<]*)<\/a:t>/g)].map((t) => t[1]).join(''),
    sizes: [...sp.matchAll(/sz="(\d+)"/g)].map((m) => Number(m[1]) / 100),
  }));

assert.equal(chips.length, 3, `expected three chips, got ${JSON.stringify(chips)}`);

const sizes = chips.flatMap((c) => c.sizes);
assert.ok(sizes.length >= 3, `no run sizes found: ${JSON.stringify(chips)}`);
const spread = Math.max(...sizes) - Math.min(...sizes);

// The row agrees one size before any member is laid out. Without that each chip
// negotiated alone against PowerPoint's wider metrics, and since a chip may only
// grow into the gap that happens to sit beside it, the last chip in a row kept
// its authored size while its neighbours were squeezed: 8.3pt, 6.5pt, 9pt for
// three chips written identically.
assert.equal(
  spread,
  0,
  `chips authored at one size exported at ${JSON.stringify(chips)} (spread ${spread}pt)`
);

// Uniformity must not be bought by shrinking everything: the shared size is the
// strictest member's fit, and that is still bounded by the layout-faithful cap.
// 16px * 0.5625 = 9pt authored; 45% off that is the floor the converter allows.
assert.ok(
  Math.min(...sizes) >= 9 * 0.55,
  `the row shrank past the layout-faithful bound: ${JSON.stringify(chips)}`
);

console.log('O31 sibling type scale: ok');
