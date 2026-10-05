/**
 * O28: a background gradient fills only the area its stops describe.
 *
 * `linear-gradient(90deg, rgba(...,.48) 0 1px, transparent 1px 80px)` is a hairline grid, not a
 * tint: flooding the shape with the stop color used to paint whole slides pale blue in PPTX
 * while Chromium showed white. Coverage is measured from stop positions, the background tile
 * (background-size) and the element box — never inferred from stop alpha.
 *
 * Run: npm run build && node scripts/test-gradient-coverage.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { parseGradientCoverage, getFillOptions } = require(path.join(root, 'dist/utils/style.js'));

const slide = { width: 1280, height: 720 };
const near = (actual, expected, tolerance, label) =>
  assert.ok(
    Math.abs(actual - expected) <= tolerance,
    `${label}: expected ~${expected}, got ${actual}`
  );

// Hairline grid drawn by stop positions (no background-size): one 1px line per box.
const authoredGrid =
  'linear-gradient(90deg, rgba(235,244,251,.48) 0 1px, transparent 1px 80px), ' +
  'linear-gradient(rgba(235,244,251,.42) 0 1px, transparent 1px 80px)';
near(parseGradientCoverage(authoredGrid, 'auto', slide).alpha, 0.0007, 0.0005, 'authored grid');

// Same pattern tiled by background-size: 1px of ink per 40px tile, twice.
const tiledGrid =
  'linear-gradient(90deg, rgba(49, 130, 206, 0.035) 1px, rgba(0, 0, 0, 0) 1px), ' +
  'linear-gradient(rgba(49, 130, 206, 0.035) 1px, rgba(0, 0, 0, 0) 1px)';
near(
  parseGradientCoverage(tiledGrid, '40px 40px, 40px 40px', slide).alpha,
  0.00175,
  0.0005,
  'tiled grid'
);

// A radial glow covers its disc, not the slide: area grows with r², so 120px of 1280 is ~0.2%.
const glow =
  'radial-gradient(circle at 86% 42%, rgba(99, 178, 237, 0.18) 0px, ' +
  'rgba(99, 178, 237, 0.18) 120px, rgba(0, 0, 0, 0) 121px)';
near(parseGradientCoverage(glow, 'auto', slide).alpha, 0.0016, 0.001, 'radial glow');

// A real two-stop gradient still covers the whole box and averages its stops.
const hero = 'linear-gradient(110deg, rgb(16, 42, 74) 0%, rgb(26, 54, 93) 56%, rgb(36, 89, 138) 100%)';
const heroCoverage = parseGradientCoverage(hero, 'auto', slide);
assert.equal(heroCoverage.alpha, 1, 'hero gradient covers the box');
assert.equal(heroCoverage.color, '193A62', 'hero gradient averages its stops');

// A stop we cannot resolve must not silently redistribute the others' area.
assert.equal(
  parseGradientCoverage('linear-gradient(90deg, #3182CE 0%, var(--unknown) 100%)', 'auto', slide),
  undefined,
  'unresolvable stop refuses measurement'
);

// The fill honours background-color under a hairline grid instead of flooding the tint.
const gridFill = getFillOptions(
  { backgroundImage: authoredGrid, backgroundSize: 'auto', backgroundColor: '#FFFFFF' },
  slide
);
assert.equal(gridFill.fill.color, 'FFFFFF', 'hairline grid keeps the white page');

// With no color layer beneath, decoration that thin is not a fill at all.
const bareGrid = getFillOptions({ backgroundImage: authoredGrid, backgroundSize: 'auto' }, slide);
assert.deepEqual(bareGrid, {}, 'hairline grid alone emits no fill');

// An opaque gradient remains the element's fill.
const heroFill = getFillOptions(
  { backgroundImage: hero, backgroundSize: 'auto', backgroundColor: '#1A365D' },
  slide
);
assert.equal(heroFill.fill.color, '193A62', 'opaque gradient fills the shape');

// A half-transparent overlay composites onto the color layer rather than replacing it.
const veil = getFillOptions(
  {
    backgroundImage: 'linear-gradient(0deg, rgba(0,0,0,.5) 0%, rgba(0,0,0,.5) 100%)',
    backgroundSize: 'auto',
    backgroundColor: '#FFFFFF',
  },
  slide
);
assert.equal(veil.fill.color, '808080', 'overlay composites onto background-color');

console.log('O28 gradient coverage: ok');
