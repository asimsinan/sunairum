/**
 * O24: OMML fractions must fit inside the formula plate (not 0.38×hostH).
 * Run: npm run build && node scripts/test-formula-host-fit.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const {
  fitMathFontSizePx,
  mathFractionDepth,
  getMathPresentationMeta,
} = require(path.join(root, 'dist/utils/omml-style.js'));

assert.equal(mathFractionDepth('<math><mi>x</mi></math>'), 0);
assert.equal(
  mathFractionDepth('<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>'),
  1
);

const hostH = 96;
const pad = 14;
const plain = fitMathFontSizePx({ hostH, hostW: 800, paddingTopPx: pad, paddingBottomPx: pad });
const withFrac = fitMathFontSizePx({
  hostH,
  hostW: 800,
  paddingTopPx: pad,
  paddingBottomPx: pad,
  mathml: '<math><mfrac><mrow><mi>C</mi></mrow><mrow><mi>C</mi><mn>0</mn></mrow></mfrac></math>',
});
assert.ok(withFrac < plain, `fraction font (${withFrac}) < plain (${plain})`);
// Old bug: 0.38 * 96 ≈ 36 → fraction paint ~97px > usable ~54px.
assert.ok(withFrac * 2.7 <= hostH - 2 * pad, `fraction must fit usable height (fs=${withFrac})`);
assert.ok(withFrac < hostH * 0.32, 'must be below legacy 0.38×host blow-up');

const meta = getMathPresentationMeta({
  type: 'math',
  x: 0,
  y: 0,
  width: 900,
  height: 96,
  styles: {
    fontSize: '16px',
    paddingTop: '14px',
    paddingBottom: '14px',
    color: '#1A365D',
    textAlign: 'center',
  },
  mathml:
    '<math><mfrac><mi>C</mi><msub><mi>C</mi><mn>0</mn></msub></mfrac></math>',
});
const fsFromHalf = (meta.szHalfPt / 2) * (96 / 72);
assert.ok(fsFromHalf * 2.7 <= 96 - 28 + 2, `meta size fits plate (≈${fsFromHalf}px)`);

console.log('O24 formula host fit: ok');
