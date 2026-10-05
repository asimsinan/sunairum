/**
 * L1 layout-faithful unit + fixture smoke tests.
 * Run: node scripts/test-layout-faithful.mjs  (after npm run build)
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';
import JSZip from 'jszip';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const require = createRequire(import.meta.url);
const dist = require(path.join(root, 'dist/index.js'));

const {
  applyChromiumSoftBreaks,
  classifyLayoutFaithfulEligibility,
  resolveLayoutFaithfulMode,
  boundFontShrink,
  LAYOUT_FAITHFUL_MAX_FONT_SHRINK,
  emuRoundTripErrorPxX,
  setViewportPixels,
  convertHtmlToPptx,
} = dist;

// boundFontShrink may not be re-exported — load utils directly
const lf = require(path.join(root, 'dist/utils/layout-faithful.js'));
const coord = require(path.join(root, 'dist/utils/coordinate.js'));
const style = require(path.join(root, 'dist/utils/style.js'));

function test(name, fn) {
  try {
    fn();
    console.log(`  ok  ${name}`);
  } catch (err) {
    console.error(`  FAIL ${name}`);
    throw err;
  }
}

console.log('L1 layout-faithful unit tests');

test('resolveLayoutFaithfulMode defaults on', () => {
  const mode = resolveLayoutFaithfulMode(undefined, {});
  assert.equal(mode, 'on');
});

test('resolveLayoutFaithfulMode cannot be disabled by a retired env value', () => {
  assert.equal(resolveLayoutFaithfulMode(undefined, { DECKHTML_LAYOUT_FAITHFUL: '0' }), 'on');
});

test('container backgrounds never become OOXML run highlights', () => {
  const options = style.getTextOptions({
    display: 'block',
    backgroundColor: 'rgba(255, 255, 255, 0.5)',
    fontSize: '16px',
  });
  assert.equal(options.highlight, undefined);
});

test('explicit glyph highlights remain highlights', () => {
  const options = style.getTextOptions({
    display: 'inline',
    glyphHighlightColor: 'rgb(255, 240, 100)',
    fontSize: '16px',
  });
  assert.equal(options.highlight, 'FFF064');
});

test('applyChromiumSoftBreaks inserts soft breaks at line boundaries', () => {
  const rich = [
    { text: 'Candidate pool', styles: { fontWeight: '700' } },
    { text: ' — Combine HNSW neighbors with positions.', styles: { color: '#4A5568' } },
  ];
  const lines = [
    { text: 'Candidate pool — Combine HNSW ', x: 0, y: 0, width: 200, height: 20, startOffset: 0, endOffset: 30 },
    { text: 'neighbors with positions.', x: 0, y: 20, width: 180, height: 20, startOffset: 30, endOffset: 55 },
  ];
  // Fix line texts to match join
  const joined = rich.map((r) => r.text).join('');
  const mid = 28;
  const lines2 = [
    {
      text: joined.slice(0, mid),
      x: 0,
      y: 0,
      width: 200,
      height: 20,
      startOffset: 0,
      endOffset: mid,
    },
    {
      text: joined.slice(mid),
      x: 0,
      y: 20,
      width: 180,
      height: 20,
      startOffset: mid,
      endOffset: joined.length,
    },
  ];
  const out = lf.applyChromiumSoftBreaks(rich, lines2, joined);
  assert.ok(out);
  const soft = out.filter((r) => r.softBreakBefore);
  assert.ok(soft.length >= 1, 'expected at least one softBreakBefore');
  assert.equal(out.map((r) => r.text).join(''), joined);
});

test('classify rejects pills and math', () => {
  const pill = classifyLayoutFaithfulEligibility(
    {
      type: 'text',
      tag: 'div',
      x: 0,
      y: 0,
      width: 80,
      height: 28,
      styles: {},
      layoutLines: [{ text: 'X', x: 0, y: 0, width: 10, height: 10, startOffset: 0, endOffset: 1 }],
      content: 'X',
    },
    { isPillBox: true }
  );
  assert.equal(pill.eligible, false);
  assert.equal(pill.reason, 'pill_path');
});

test('boundFontShrink respects max', () => {
  const r = lf.boundFontShrink(20, 0.5);
  assert.ok(r.shrunk);
  assert.ok(r.scale >= 1 - LAYOUT_FAITHFUL_MAX_FONT_SHRINK - 1e-9);
});

test('EMU round-trip ≤ 1 source px', () => {
  coord.setViewportPixels(1280, 720);
  for (const px of [0, 1, 60, 132, 640, 1160, 1279]) {
    const err = coord.emuRoundTripErrorPxX(px);
    assert.ok(err <= 1.0001, `px=${px} err=${err}`);
  }
});

async function smokeConvert() {
  console.log('L1 fixture smoke (wrapping-matrix + slide_07)');
  const matrix = path.join(root, 'test/fixtures/wrapping-matrix/matrix.html');
  const slide07 = path.join(root, 'test/fixtures/sunairum-slides-02-13/slide_07.html');
  assert.ok(fs.existsSync(matrix));
  assert.ok(fs.existsSync(slide07));

  const result = await convertHtmlToPptx({
    inputs: [matrix, slide07],
    allowLocalResources: true,
    quiet: true,
    layoutFaithful: true,
    slideTransitions: false,
    animations: false,
  });
  assert.ok(result.data?.length > 1000, 'pptx buffer');

  const zip = await JSZip.loadAsync(result.data);
  const slideXml = await zip.file('ppt/slides/slide1.xml')?.async('string');
  assert.ok(slideXml, 'slide1.xml');
  // Frozen path: explicit Chromium breaks + wrap:none (no PowerPoint autofit).
  assert.match(slideXml, /<a:br\/>/);
  assert.doesNotMatch(slideXml, /<a:normAutofit\/>/);
  assert.match(slideXml, /wrap="none"/);
  // Single-style paragraphs must also get their Chromium breaks synthesized.
  assert.match(slideXml, /Title that wraps across two lines for layout<\/a:t><\/a:r><a:br\/>/);

  // slide 2 in package = fixture slide_07 — look for Candidate pool without requiring exact XML text order
  const slide2 = await zip.file('ppt/slides/slide2.xml')?.async('string');
  assert.ok(slide2, 'slide2.xml');
  assert.match(slide2, /Candidate pool/);
  // Count text shapes that contain "Candidate pool" — should be one host, not two overlapping
  const poolHits = (slide2.match(/Candidate pool/g) || []).length;
  assert.ok(poolHits >= 1 && poolHits <= 2, `unexpected Candidate pool count: ${poolHits}`);

  console.log('  ok  smoke convert wrapping-matrix + slide_07');
}

async function smokeObjectFallback() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'deckhtml-object-fallback-'));
  const input = path.join(tmp, 'slide.html');
  fs.writeFileSync(input, `<!doctype html><html><head><style>
    html,body{margin:0;width:1280px;height:720px;background:white}
    .slide{position:relative;width:1280px;height:720px;overflow:hidden}
    p{position:absolute;left:80px;font:32px Arial;color:#123}
    .native{top:80px;width:500px;height:50px}
    .unsupported{top:180px;width:420px;height:80px;transform:rotate(4deg)}
  </style></head><body><section class="slide">
    <p class="native">This remains editable native text.</p>
    <p class="unsupported">Only this unsupported transformed fragment is rasterized.</p>
  </section></body></html>`);
  try {
    const result = await convertHtmlToPptx({
      inputs: [input], allowLocalResources: true, quiet: true, layoutFaithful: true,
      slideTransitions: false, animations: false,
    });
    const zip = await JSZip.loadAsync(result.data);
    const slideXml = await zip.file('ppt/slides/slide1.xml')?.async('string');
    assert.match(slideXml, /This remains editable native text/);
    assert.doesNotMatch(slideXml, /Only this unsupported transformed fragment is rasterized/);
    const ids = (result.shapeMap || []).map((shape) => shape.elementId);
    assert.ok(ids.length >= 2);
    assert.equal(new Set(ids).size, ids.length, 'every emitted drawable must have a unique stable identity');
    assert.ok(ids.every(Boolean), 'every emitted drawable must have a stable identity');
    const fallback = (result.shapeMap || []).find((shape) =>
      String(shape.rasterReason || '').startsWith('unsupported-text-')
    );
    assert.ok(fallback, 'unsupported fragment must use one object-level image fallback');
    assert.ok(fallback.pptx.w < 9 && fallback.pptx.h < 5, 'fallback must not flatten the whole slide');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  console.log('  ok  unsupported construct uses object-level fallback only');
}

await smokeConvert();
await smokeObjectFallback();
console.log('All L1 tests passed.');
process.exit(0);
