/**
 * Unit checks for pill/chip badge classification + font fit (no Playwright).
 * Run: node scripts/test-pill-badge.mjs  (after npm run build)
 */
import assert from 'node:assert/strict'
import {
  fitPillFontSizeToBox,
  fitWrappedTextBox,
  hasVisibleBorder,
  isInlinePillBox,
  layoutPillBoxForText,
  parseLetterSpacing,
  parsePillFontSize,
} from '../dist/utils/style.js'
import { setViewportPixels } from '../dist/utils/coordinate.js'

setViewportPixels(1280, 720)

// Short flex-item chips (HNSW / LNS) — blockified, no nowrap, w/h < 2.2
const shortFlexChip = {
  display: 'block',
  borderRadius: '8px',
  borderTopWidth: '1px',
  borderRightWidth: '1px',
  borderBottomWidth: '1px',
  borderLeftWidth: '1px',
  borderTopColor: 'rgb(226, 232, 240)',
  borderRightColor: 'rgb(226, 232, 240)',
  borderBottomColor: 'rgb(226, 232, 240)',
  borderLeftColor: 'rgb(226, 232, 240)',
  backgroundColor: 'rgb(255, 255, 255)',
  paddingTop: '8px',
  paddingRight: '12px',
  paddingBottom: '8px',
  paddingLeft: '12px',
  fontSize: 13,
  fontWeight: '700',
}
assert.equal(
  isInlinePillBox(shortFlexChip, { width: 54, height: 34 }),
  true,
  'short HNSW-like flex chip must be a pill'
)
assert.equal(
  isInlinePillBox(shortFlexChip, { width: 42, height: 34 }),
  true,
  'short LNS-like flex chip must be a pill'
)
assert.equal(
  isInlinePillBox(shortFlexChip, { width: 54, height: 52 }),
  true,
  'compact flex chip at h=52 (≤56) must still be a pill'
)

// Negative CSS letter-spacing must not become positive PPT tracking
const negTrack = parseLetterSpacing('-1.2px', 55)
assert.ok(negTrack !== undefined && negTrack < 0, `expected negative charSpacing, got ${negTrack}`)
assert.equal(parseLetterSpacing('normal'), undefined)

// Collision-aware grow: do not expand into a right neighbor
const collided = layoutPillBoxForText({
  fontSizePt: 7.9,
  text: 'HNSW',
  xInch: 8.0,
  yInch: 4.0,
  wInch: 0.45,
  hInch: 0.28,
  marginLeftPt: 6.75,
  marginRightPt: 6.75,
  marginTopPt: 4.5,
  marginBottomPt: 4.5,
  bold: true,
  preferShrinkFont: true,
  maxGrowInch: 10 / 96,
  maxRightInch: 8.52,
})
assert.ok(collided.x + collided.w <= 8.52 + 1e-6, 'must not grow into right sibling')
assert.ok(collided.fontSizePt <= 7.9, 'may shrink font when gap is tight')

// Outline flex-item chip (slide_02 hero badge)
const outlineChip = {
  display: 'block',
  borderRadius: '20px',
  borderTopWidth: '1px',
  borderRightWidth: '1px',
  borderBottomWidth: '1px',
  borderLeftWidth: '1px',
  borderTopColor: 'rgb(99, 179, 237)',
  borderRightColor: 'rgb(99, 179, 237)',
  borderBottomColor: 'rgb(99, 179, 237)',
  borderLeftColor: 'rgb(99, 179, 237)',
  backgroundColor: 'rgba(0, 0, 0, 0)',
  paddingTop: '10px',
  paddingRight: '15px',
  paddingBottom: '10px',
  paddingLeft: '15px',
  fontSize: 15,
  fontWeight: '700',
}

assert.equal(hasVisibleBorder(outlineChip), true)
assert.equal(
  isInlinePillBox(outlineChip, { width: 190, height: 40 }),
  true,
  'compact outline chip must be a pill'
)
assert.equal(
  isInlinePillBox(outlineChip, { width: 544, height: 270 }),
  false,
  'tall rounded card must not be a pill'
)
assert.equal(
  isInlinePillBox(
    { ...outlineChip, whiteSpace: 'normal' },
    { width: 317, height: 76 },
    { multiLine: true }
  ),
  false,
  'multi-line <br> callout must not be a nowrap pill'
)

// Legacy filled inline-block pill
assert.equal(
  isInlinePillBox({
    display: 'inline-block',
    borderRadius: '9999px',
    backgroundColor: 'rgb(49, 130, 206)',
  }),
  true
)

// Pill font uses slide-space (not the larger font-calibrated size)
const pillPt = parsePillFontSize('15px')
assert.ok(pillPt <= 9, `expected spatial ~8.4pt, got ${pillPt}`)

const fitted = fitPillFontSizeToBox({
  fontSizePt: 12,
  text: 'REPAIR, NOT REPLACE',
  boxWidthInch: 1.35,
  marginLeftPt: 9,
  marginRightPt: 9,
  bold: true,
})
assert.ok(fitted <= 12, 'fit should not grow font')
assert.ok(fitted >= 6, 'fit should keep readable minimum')

// Prefer grow-over-shrink so padding air is preserved ("4 dimensions" chip).
const laid = layoutPillBoxForText({
  fontSizePt: 7.9,
  text: '4 dimensions',
  xInch: 8.3,
  yInch: 1.84,
  wInch: 0.89,
  hInch: 0.25,
  marginLeftPt: 6.75,
  marginRightPt: 6.75,
  marginTopPt: 4.5,
  marginBottomPt: 4.5,
  bold: true,
})
assert.ok(laid.w > 0.89, 'should widen chip before crushing font')
assert.ok(laid.fontSizePt >= 7.5, `should keep near-full font, got ${laid.fontSizePt}`)
assert.ok(laid.x < 8.3, 'right-side chip should expand leftward')

// Three adjacent chips: middle grow must not overlap left/right AABBs
const leftChip = { x: 7.5, w: 0.5 }
const mid = layoutPillBoxForText({
  fontSizePt: 7.9,
  text: 'Equity',
  xInch: 8.1,
  yInch: 4.0,
  wInch: 0.5,
  hInch: 0.28,
  marginLeftPt: 6.75,
  marginRightPt: 6.75,
  marginTopPt: 4.5,
  marginBottomPt: 4.5,
  bold: true,
  preferShrinkFont: true,
  maxGrowInch: 10 / 96,
  minLeftInch: leftChip.x + leftChip.w + 4 / 96,
  maxRightInch: 9.15,
})
assert.ok(mid.x >= leftChip.x + leftChip.w + 4 / 96 - 1e-6, 'no overlap left sibling')
assert.ok(mid.x + mid.w <= 9.15 + 1e-6, 'no overlap right sibling')

// Title wrap fit: must not spill past accent ceiling
const titleFit = fitWrappedTextBox({
  text: 'Solomon results show the intended separation of routing heuristics',
  fontSizePt: 22,
  lineSpacingPt: 24.6,
  xInch: 2.0,
  yInch: 0.4,
  wInch: 6.5,
  hInch: 0.55,
  bold: true,
  charSpacingPt: -0.3,
  maxBottomInch: 1.05,
})
assert.ok(titleFit.y + titleFit.h <= 1.05 + 1e-4, 'title must stay above accent band')
assert.ok(titleFit.fontSizePt <= 22, 'may shrink font to clear accent')

// Title must not grow into a right-column wall (slide 1 HNSW title vs SEARCH LANDSCAPE)
const titleVsPanel = fitWrappedTextBox({
  text: 'HNSW Guided Large Neighborhood Search for Equitable Vehicle Routing',
  fontSizePt: 30,
  lineSpacingPt: 32.4,
  xInch: 80 / 96,
  yInch: 2.0,
  wInch: 610 / 96,
  hInch: 2.2,
  bold: true,
  charSpacingPt: -0.7,
  maxRightInch: 690 / 96,
  preferShrinkFont: true,
})
assert.ok(
  titleVsPanel.x + titleVsPanel.w <= 690 / 96 + 1e-4,
  `title must not enter right panel, got right=${titleVsPanel.x + titleVsPanel.w}`
)

console.log('pill-badge checks ok')
