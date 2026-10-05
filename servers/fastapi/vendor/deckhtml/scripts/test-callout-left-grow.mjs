/**
 * O23: left-accent callouts must not grow left (text drifting past the bar).
 * Run: npm run build && node scripts/test-callout-left-grow.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { fitTextBoxToIntentionalLines } = require(path.join(root, 'dist/utils/style.js'));
const { setViewportPixels } = require(path.join(root, 'dist/utils/coordinate.js'));

setViewportPixels(1280, 720);

const base = {
  lines: [
    'Repair must optimize what is cheap to generate and useful to',
    'operate.',
  ],
  fontSizePt: 18,
  lineSpacingPt: 24,
  xInch: 1.5,
  yInch: 3.5,
  wInch: 4.0,
  hInch: 0.8,
  marginLeftPt: 14,
  marginRightPt: 12,
  marginTopPt: 10,
  marginBottomPt: 10,
  bold: false,
};

const drifted = fitTextBoxToIntentionalLines({ ...base });
// Without preferGrowRight, center-right boxes may expand left.
assert.ok(drifted.x <= base.xInch + 1e-6, 'baseline can shift left or stay');

const fixed = fitTextBoxToIntentionalLines({ ...base, preferGrowRight: true });
assert.equal(fixed.x, base.xInch, 'preferGrowRight must keep x (no left drift)');
assert.ok(fixed.w >= base.wInch - 1e-6, 'may grow right or shrink font');

console.log('O23 callout left-grow: ok');
