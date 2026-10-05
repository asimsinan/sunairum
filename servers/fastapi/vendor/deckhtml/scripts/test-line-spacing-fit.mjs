/**
 * Typography and geometry must share one px→pt scale.
 *
 * They did not: font sizes converted at 0.58 pt/px while line pitch and every frame converted
 * at the geometric 0.5625, so each glyph was 3.1% taller than the line box holding it. Three
 * lines of 25px line-height then needed more room than the 75px box the inspector measured —
 * text crept out of its frame, re-wrapped, and collided with the element below. The invariant
 * below is what makes N lines fit an N-line box exactly.
 *
 * Run: node scripts/test-line-spacing-fit.mjs  (after npm run build)
 */
import assert from 'node:assert/strict'
import { parseLineHeight } from '../dist/utils/style.js'
import {
  PX_TO_POINTS,
  pxToPoints,
  pxToSlidePointsY,
  setViewportPixels,
} from '../dist/utils/coordinate.js'

setViewportPixels(1280, 720)

const lhPx = 25
assert.equal(PX_TO_POINTS, (5.625 * 72) / 720, 'px→pt is the slide projection')
assert.ok(
  Math.abs(pxToPoints(lhPx) - pxToSlidePointsY(lhPx)) < 1e-9,
  `typography (${pxToPoints(lhPx)}) and geometry (${pxToSlidePointsY(lhPx)}) must agree`
)

// A 64px heading is 36pt — the size whose glyphs occupy the measured frame.
assert.equal(pxToPoints(64), 36, '64px → 36pt')

// 3 lines in a 75px content box fit exactly, with no accumulating drift.
const boxPx = 75
const lines = 3
const boxPt = pxToSlidePointsY(boxPx)
assert.ok(
  Math.abs(pxToPoints(lhPx) * lines - boxPt) < 0.05,
  'N lines of line-height fill an N-line box'
)

// A non-standard viewport keeps the two spaces in step.
setViewportPixels(1920, 1080)
assert.ok(
  Math.abs(pxToPoints(37.5) - pxToSlidePointsY(37.5)) < 1e-9,
  'scaled viewport keeps typography and geometry aligned'
)
setViewportPixels(1280, 720)

// parseLineHeight: 25px / 18px → multiple path; bare px without exact ratio uses slide Y
const fixed = parseLineHeight('24px', 18)
assert.ok(fixed?.lineSpacing != null || fixed?.lineSpacingMultiple != null)
if (fixed?.lineSpacing != null) {
  assert.ok(Math.abs(fixed.lineSpacing - pxToSlidePointsY(24)) < 0.05)
}

console.log('line-spacing-fit checks ok')
