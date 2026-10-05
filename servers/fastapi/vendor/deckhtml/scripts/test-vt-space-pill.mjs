/**
 * O26: vertical tab must become a space (not glue words); short chips stay one line.
 * Run: npm run build && node scripts/test-vt-space-pill.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { sanitizeTextForXml, isInlinePillBox, layoutPillBoxForText } = require(
  path.join(root, 'dist/utils/style.js')
);
const { setViewportPixels, pxToInchX, pxToInchY } = require(
  path.join(root, 'dist/utils/coordinate.js')
);

setViewportPixels(1280, 720);

assert.equal(
  sanitizeTextForXml('Insert\u000bhere'),
  'Insert here',
  'VT must become a space'
);
assert.equal(
  sanitizeTextForXml('using\u000bspatial, temporal'),
  'using spatial, temporal'
);
assert.ok(!sanitizeTextForXml('Insert\u000bhere').includes('Inserthere'));

const styles = {
  borderRadius: '999px',
  backgroundColor: 'rgb(49, 130, 206)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  whiteSpace: 'normal',
};
// Chromium wrapped to 2 lines inside a tight circle — still a short chip.
assert.equal(
  isInlinePillBox(styles, { width: 72, height: 72 }, { multiLine: true }),
  false,
  'tall multi-line callouts stay excluded'
);
assert.equal(
  isInlinePillBox(
    styles,
    { width: 72, height: 72 },
    { multiLine: true, shortLabel: true }
  ),
  true,
  'short wrapped Insert-here node is still a pill'
);

const laid = layoutPillBoxForText({
  fontSizePt: 12,
  text: 'Insert here',
  xInch: pxToInchX(500),
  yInch: pxToInchY(300),
  wInch: pxToInchX(64),
  hInch: pxToInchY(36),
  marginLeftPt: 6,
  marginRightPt: 6,
  marginTopPt: 4,
  marginBottomPt: 4,
  bold: true,
  preferShrinkFont: false,
  maxGrowInch: pxToInchX(80),
});
assert.ok(laid.w > pxToInchX(64) - 1e-6, 'pill grows to fit Insert here on one line');

console.log('O26 vt-space-pill: ok');
