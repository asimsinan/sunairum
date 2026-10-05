/**
 * L1 corpus gate: convert frozen slides 02–13 and assert geometry / wrap / overlap.
 * Run: node scripts/test-layout-faithful-corpus.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import JSZip from 'jszip';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const require = createRequire(import.meta.url);
const { convertHtmlToPptx } = require(path.join(root, 'dist/index.js'));

const fixtureDir = path.join(root, 'test/fixtures/sunairum-slides-02-13');
const slides = Array.from({ length: 12 }, (_, i) =>
  path.join(fixtureDir, `slide_${String(i + 2).padStart(2, '0')}.html`)
);
for (const s of slides) assert.ok(fs.existsSync(s), s);

const SLIDE_W = 10;
const SLIDE_H = 5.625;
const EMU = 914400;

function parseXfrm(shapeXml) {
  const m = shapeXml.match(
    /<a:off[^>]*x="(-?\d+)"[^>]*y="(-?\d+)"[^/]*\/>[\s\S]*?<a:ext[^>]*cx="(-?\d+)"[^>]*cy="(-?\d+)"/
  );
  if (!m) return null;
  return {
    x: Number(m[1]) / EMU,
    y: Number(m[2]) / EMU,
    w: Number(m[3]) / EMU,
    h: Number(m[4]) / EMU,
  };
}

function decodeXmlText(s) {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
}

console.log('Converting slides 02–13 with layoutFaithful=on …');
const t0 = Date.now();
const result = await convertHtmlToPptx({
  inputs: slides,
  allowLocalResources: true,
  quiet: true,
  layoutFaithful: true,
  slideTransitions: false,
  animations: false,
});
const ms = Date.now() - t0;
console.log(`  convert_ms=${ms} bytes=${result.data.length}`);
assert.ok(ms < 180_000, `conversion too slow: ${ms}ms`);

const zip = await JSZip.loadAsync(result.data);
let overflow = 0;
let wrapSquareEligibleSuspect = 0;
const origins = new Map();

for (let i = 1; i <= 12; i++) {
  const xml = await zip.file(`ppt/slides/slide${i}.xml`)?.async('string');
  assert.ok(xml, `missing slide${i}.xml`);
  const shapes = xml.split(/<p:sp[\s>]/).slice(1);
  for (const sh of shapes) {
    const box = parseXfrm(sh);
    if (!box) continue;
    if (box.x + box.w > SLIDE_W + 0.02 || box.y + box.h > SLIDE_H + 0.02) {
      overflow++;
    }
    if (box.x < -0.02 || box.y < -0.02) overflow++;
    const texts = [...sh.matchAll(/<a:t[^>]*>([^<]*)<\/a:t>/g)].map((m) =>
      decodeXmlText(m[1]).trim()
    );
    const joined = texts.join('').slice(0, 48);
    if (joined.length >= 8) {
      const key = `${i}:${box.x.toFixed(3)},${box.y.toFixed(3)}:${joined}`;
      origins.set(key, (origins.get(key) || 0) + 1);
    }
    if (/wrap="square"/.test(sh) && /<a:br\b/.test(sh)) {
      wrapSquareEligibleSuspect++;
    }
  }
}

assert.equal(overflow, 0, `slide overflow boxes: ${overflow}`);
// Duplicate identical text at identical origin is the classic split-span bug
const dups = [...origins.entries()].filter(([, n]) => n > 1);
assert.equal(dups.length, 0, `shared-origin duplicates: ${JSON.stringify(dups.slice(0, 5))}`);

// L1 closed-loop: no PowerPoint autofit on the package; fonts should embed when available.
const allSlideXml = await Promise.all(
  Array.from({ length: 12 }, (_, i) =>
    zip.file(`ppt/slides/slide${i + 1}.xml`)?.async('string')
  )
);
for (const xml of allSlideXml) {
  if (!xml) continue;
  assert.doesNotMatch(xml, /<a:normAutofit\/>/, 'L1 must not emit normAutofit');
}
const presentationXml = await zip.file('ppt/presentation.xml')?.async('string');
const fontFiles = Object.keys(zip.files).filter(
  (p) => p.startsWith('ppt/fonts/') && p.endsWith('.fntdata')
);
if (presentationXml?.includes('<p:embeddedFontLst>')) {
  assert.ok(fontFiles.length >= 1, 'embeddedFontLst without fntdata');
}

// Named regressions
const s05 = await zip.file('ppt/slides/slide4.xml')?.async('string'); // slide_05 = index 4 in 02..13
const s07 = await zip.file('ppt/slides/slide6.xml')?.async('string'); // slide_07
assert.ok(s05 && /SELECT/.test(s05), 'slide 05 SELECT missing');
assert.ok(s07 && /Candidate pool/.test(s07), 'slide 07 Candidate pool missing');
assert.ok(s07 && /HERO/.test(s07), 'slide 07 HERO missing');
// Label+body must be one shape (not two shared-origin boxes)
let poolShapes = 0;
for (const m of s07.matchAll(/<p:sp\b[\s\S]*?<\/p:sp>/g)) {
  if (!m[0].includes('Candidate pool')) continue;
  poolShapes += 1;
  assert.match(m[0], /Combine HNSW/, 'Candidate pool body missing from same shape');
}
assert.equal(poolShapes, 1, `Candidate pool shape count ${poolShapes}`);

console.log('Corpus gates passed.');
console.log(
  JSON.stringify({
    convert_ms: ms,
    overflow,
    wrapSquareWithBr: wrapSquareEligibleSuspect,
    slideCount: 12,
  })
);
process.exit(0);
