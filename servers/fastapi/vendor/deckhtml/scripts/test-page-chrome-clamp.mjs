/**
 * O25: callouts must not grow into bottom-right page chrome (n/N).
 * Run: npm run build && node scripts/test-page-chrome-clamp.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { ElementConverter } = require(path.join(root, 'dist/converter.js'));
const { StyleEnhancementRegistry } = require(path.join(root, 'dist/enhancer/registry.js'));
const { setViewportPixels, pxToInchX, pxToInchY } = require(
  path.join(root, 'dist/utils/coordinate.js')
);

setViewportPixels(1280, 720);

const converter = new ElementConverter(new StyleEnhancementRegistry());

const chromeEl = {
  type: 'text',
  id: 'page-chrome',
  x: 1180,
  y: 690,
  width: 60,
  height: 16,
  pageChrome: true,
  styles: {},
};

converter.beginSlide(0, [chromeEl], 0);
assert.ok(converter.chromeBands.length >= 1, 'chrome band seeded');

const box = {
  x: pxToInchX(200),
  y: pxToInchY(560),
  w: pxToInchX(1060),
  h: pxToInchY(140),
};
const beforeH = box.h;
const beforeW = box.w;
converter.clampBoxAwayFromChrome(box);
assert.ok(box.h < beforeH || box.w < beforeW, 'must trim into chrome');

const chromeTop = converter.chromeBands[0].y;
assert.ok(box.y + box.h <= chromeTop + 0.02, 'callout bottom stays above chrome');

console.log('O25 page-chrome clamp: ok');
