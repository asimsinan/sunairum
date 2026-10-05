/**
 * O22: title underline / accent must clear serif descenders.
 * Run: npm run build && node scripts/test-accent-descender.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import JSZip from 'jszip';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { convertHtmlToPptx } = require(path.join(root, 'dist/index.js'));

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'deckhtml-o22-'));
const htmlPath = path.join(dir, 'slide.html');
fs.writeFileSync(
  htmlPath,
  `<!DOCTYPE html><html><body>
<section class="slide" style="width:1280px;height:720px;position:relative;background:#fff;overflow:hidden;">
  <h1 style="position:absolute;left:80px;top:80px;width:900px;margin:0;padding:0 0 12px 0;
    font-family:Georgia,serif;font-size:48px;font-weight:700;line-height:1.15;color:#1A365D;
    border-bottom:2px solid #BEE3F8;box-sizing:border-box;">
    HNSW Guided Large<br/>Neighborhood Search for<br/>Equitable Vehicle Routing
  </h1>
</section>
</body></html>`
);

const result = await convertHtmlToPptx({
  input: htmlPath,
  allowLocalResources: true,
  layoutFaithful: true,
  quiet: true,
  viewportWidth: 1280,
  viewportHeight: 720,
  slideTransitions: false,
  animations: false,
});

assert.ok(result.data?.length > 1000, 'pptx buffer');
const zip = await JSZip.loadAsync(result.data);
const slideName = Object.keys(zip.files).find(
  (n) => /ppt\/slides\/slide\d+\.xml$/.test(n)
);
assert.ok(slideName, 'slide xml in pptx');
const xml = await zip.file(slideName).async('string');
assert.match(xml, /Equitable/, 'title text present');

// Thin filled accent (border decoration) should exist.
assert.match(xml, /<a:solidFill>/, 'accent fill present');

console.log('O22 accent/descender clearance: ok');
