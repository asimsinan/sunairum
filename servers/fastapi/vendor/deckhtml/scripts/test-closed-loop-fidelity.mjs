/**
 * Closed-loop fidelity smoke:
 * 1) embedDeckFonts on a synthetic slide XML (no Playwright)
 * 2) convert wrapping-matrix → assert wrap:none, no normAutofit, shapeMap, embeds
 */
import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'node:url';
import JSZip from 'jszip';
import {
  convertHtmlToPptx,
  embedDeckFonts,
  resolveDeckFontDirs,
  resolveFontBytesForTypeface,
} from '../dist/index.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fastapiFonts = path.resolve(root, '../../assets/fonts');

async function testSyntheticEmbed() {
  console.log('synthetic embedDeckFonts');
  const dirs = resolveDeckFontDirs();
  assert.ok(dirs.length >= 1, 'expected at least one deck font dir');
  if (fs.existsSync(fastapiFonts)) {
    process.env.DECKHTML_FONTS_DIR = fastapiFonts;
  }
  const resolved = resolveFontBytesForTypeface(
    'Arial',
    resolveDeckFontDirs(),
    path.join(root, 'assets')
  );
  assert.ok(resolved, 'Arial should resolve to Source Sans 3 pack');

  const zip = new JSZip();
  zip.file(
    '[Content_Types].xml',
    `<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>`
  );
  zip.file(
    'ppt/_rels/presentation.xml.rels',
    `<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>`
  );
  zip.file(
    'ppt/presentation.xml',
    `<?xml version="1.0"?><p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst/><p:notesSz cx="0" cy="0"/></p:presentation>`
  );
  zip.file(
    'ppt/slides/slide1.xml',
    `<?xml version="1.0"?><p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:rPr><a:latin typeface="Arial"/></a:rPr><a:t>Hi</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>`
  );
  const buf = await zip.generateAsync({ type: 'nodebuffer' });
  const out = await embedDeckFonts(buf);
  const outZip = await JSZip.loadAsync(out);
  const fonts = Object.keys(outZip.files).filter(
    (p) => p.startsWith('ppt/fonts/') && p.endsWith('.fntdata')
  );
  assert.ok(fonts.length >= 1, 'fntdata embedded');
  const pres = await outZip.file('ppt/presentation.xml')?.async('string');
  assert.ok(pres?.includes('<p:embeddedFontLst>'));
  console.log('  ok  synthetic embed');
}

async function testConvertFidelity() {
  console.log('convert wrapping-matrix fidelity');
  const matrix = path.join(root, 'test/fixtures/wrapping-matrix/matrix.html');
  assert.ok(fs.existsSync(matrix));
  process.env.DECKHTML_LAYOUT_FAITHFUL = '1';
  if (fs.existsSync(fastapiFonts)) {
    process.env.DECKHTML_FONTS_DIR = fastapiFonts;
  }
  // Isolate Playwright profile so prior hung runs cannot block launch.
  process.env.DECKHTML_BROWSER_DATA_DIR = fs.mkdtempSync(
    path.join(os.tmpdir(), 'deckhtml-fid-')
  );

  const result = await convertHtmlToPptx({
    inputs: [matrix],
    allowLocalResources: true,
    quiet: true,
    layoutFaithful: true,
    slideTransitions: false,
    animations: false,
  });
  assert.ok(result.data?.length > 1000);
  assert.ok(Array.isArray(result.shapeMap) && result.shapeMap.length > 0);

  const zip = await JSZip.loadAsync(result.data);
  const slideXml = await zip.file('ppt/slides/slide1.xml')?.async('string');
  assert.ok(slideXml);
  assert.doesNotMatch(slideXml, /<a:normAutofit\/>/);
  assert.match(slideXml, /wrap="none"/);

  const presentation = await zip.file('ppt/presentation.xml')?.async('string');
  const fontFiles = Object.keys(zip.files).filter(
    (p) => p.startsWith('ppt/fonts/') && p.endsWith('.fntdata')
  );
  if (fs.existsSync(fastapiFonts)) {
    assert.ok(
      presentation?.includes('<p:embeddedFontLst>'),
      'expected embeddedFontLst when DECKHTML_FONTS_DIR resolves'
    );
    assert.ok(fontFiles.length >= 1, `expected fntdata embeds, got ${fontFiles.length}`);
  }
  console.log('  ok  convert fidelity');
}

await testSyntheticEmbed();
await testConvertFidelity();
console.log('All closed-loop fidelity tests passed.');
process.exit(0);
