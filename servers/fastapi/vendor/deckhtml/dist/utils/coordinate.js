"use strict";
/**
 * Coordinate and unit conversion utilities
 *
 * The HTML viewport is mapped to a fixed PPTX slide of 10in × 5.625in
 * (standard 16:9). The reference (1×) viewport is 1280px × 720px:
 *   1px → 10/1280 inch horizontally, 1px → 5.625/720 inch vertically.
 *
 * Larger viewports (e.g. 1920 × 1080) are projected onto the same slide,
 * so positions/sizes are scaled down automatically by `pxToInchX/Y`.
 *
 * Font-related lengths (px → pt for fontSize, padding, border, shadow,
 * letter-spacing, line-height, …) live in a different unit space (points)
 * that does not vary with `slideWidthPx`. To keep their visual size in
 * sync with positions/sizes, we apply a `fontScaleFactor = 1280 / slideWidthPx`
 * inside `pxToPoints`. So when the source HTML is 1920×1080, every px → pt
 * conversion is automatically scaled down by 1.5×, matching the geometry.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.EMU_PER_INCH = exports.PX_TO_POINTS = exports.SLIDE_HEIGHT_INCH = exports.SLIDE_WIDTH_INCH = void 0;
exports.setViewportPixels = setViewportPixels;
exports.getSlideWidthPx = getSlideWidthPx;
exports.getSlideHeightPx = getSlideHeightPx;
exports.pxToInchX = pxToInchX;
exports.pxToInchY = pxToInchY;
exports.pxToInch = pxToInch;
exports.pxToPoints = pxToPoints;
exports.pxToEmuX = pxToEmuX;
exports.pxToEmuY = pxToEmuY;
exports.emuRoundTripErrorPxX = emuRoundTripErrorPxX;
exports.inchToPoints = inchToPoints;
exports.pxToSlidePointsY = pxToSlidePointsY;
exports.clampPptxTablePositionInch = clampPptxTablePositionInch;
exports.SLIDE_WIDTH_INCH = 10;
exports.SLIDE_HEIGHT_INCH = 5.625;
/** Reference viewport the px→pt ratio is expressed at. */
const STANDARD_WIDTH_PX = 1280;
const STANDARD_HEIGHT_PX = 720;
let slideWidthPx = STANDARD_WIDTH_PX;
let slideHeightPx = STANDARD_HEIGHT_PX;
let fontScaleFactor = 1;
/**
 * Set HTML viewport size used for this conversion (Playwright + px→inch mapping).
 * Call before loading the page / inspecting. Height defaults to 720.
 *
 * Also derives the default font scale factor from the new viewport width so
 * px → pt conversions (font size, padding, border, shadow, …) stay consistent
 * with px → inch positions when the viewport is not 1280×720.
 */
function setViewportPixels(widthPx, heightPx = STANDARD_HEIGHT_PX) {
    const w = Number(widthPx);
    const h = Number(heightPx);
    if (!Number.isFinite(w) || w <= 0) {
        slideWidthPx = STANDARD_WIDTH_PX;
        slideHeightPx = STANDARD_HEIGHT_PX;
    }
    else {
        slideWidthPx = Math.round(w);
        if (!Number.isFinite(h) || h <= 0) {
            slideHeightPx = STANDARD_HEIGHT_PX;
        }
        else {
            slideHeightPx = Math.round(h);
        }
    }
    fontScaleFactor = STANDARD_WIDTH_PX / slideWidthPx;
}
function getSlideWidthPx() {
    return slideWidthPx;
}
function getSlideHeightPx() {
    return slideHeightPx;
}
/**
 * Horizontal px → inches (maps viewport width to slide width in inches)
 */
function pxToInchX(px) {
    return (px * exports.SLIDE_WIDTH_INCH) / slideWidthPx;
}
/**
 * Vertical px → inches (maps viewport height to slide height in inches)
 */
function pxToInchY(px) {
    return (px * exports.SLIDE_HEIGHT_INCH) / slideHeightPx;
}
/**
 * Neutral lengths (blur radius, uniform border-radius when scales match): average of axis scales.
 */
function pxToInch(px) {
    return (pxToInchX(px) + pxToInchY(px)) / 2;
}
/**
 * CSS px → points, the same projection the slide geometry uses.
 *
 * 5.625in over 720px is 0.5625pt per px, so a 64px heading is 36pt — the size
 * at which its glyphs occupy exactly the frame the inspector measured, and the
 * size its own line pitch (`pxToSlidePointsY`) is already computed at.
 *
 * This ratio was 0.58 for a long time, chosen so that a string's *width* in
 * LibreOffice matched Chromium; LibreOffice sets Georgia and Arial slightly
 * narrower than Chromium at equal point size. Inflating the size by 3.1% to
 * recover the width is a bad trade: it makes every glyph 3.1% taller than its
 * own line box, so text creeps out of its frame, re-wraps, and collides with
 * the element below — measured on a cover title, ink height 65px against the
 * 62px Chromium measured, and the first line 4px high. At 0.5625 the same
 * title measures 62px, exactly Chromium's, and every slide of the reference
 * deck scored the same or better. A residual width difference belongs to the
 * font, and is corrected by embedding faces and by per-run width fitting —
 * not by lying about the point size.
 *
 * The active `fontScaleFactor` (defaults to `1280 / slideWidthPx`) keeps the
 * conversion consistent across non-standard viewports — e.g. a 48px font in
 * a 1920px-wide HTML becomes the same PPT point size as a 32px font in a
 * 1280px-wide HTML.
 */
exports.PX_TO_POINTS = (exports.SLIDE_HEIGHT_INCH * 72) / STANDARD_HEIGHT_PX;
function pxToPoints(px) {
    return px * exports.PX_TO_POINTS * fontScaleFactor;
}
/** OOXML English Metric Unit — 914400 EMU per inch. */
exports.EMU_PER_INCH = 914400;
/** Convert CSS px (current viewport) to EMU on the X axis (deterministic). */
function pxToEmuX(px) {
    return Math.round(pxToInchX(px) * exports.EMU_PER_INCH);
}
/** Convert CSS px (current viewport) to EMU on the Y axis (deterministic). */
function pxToEmuY(px) {
    return Math.round(pxToInchY(px) * exports.EMU_PER_INCH);
}
/**
 * Max absolute error in CSS source pixels after inch→EMU→inch round-trip.
 * Used by L1 geometry gates (≤1 source px).
 */
function emuRoundTripErrorPxX(px) {
    const emu = pxToEmuX(px);
    const backInch = emu / exports.EMU_PER_INCH;
    const backPx = (backInch * slideWidthPx) / exports.SLIDE_WIDTH_INCH;
    return Math.abs(backPx - px);
}
/**
 * Convert inches to points
 */
function inchToPoints(inch) {
    return inch * 72;
}
/**
 * Vertical CSS lengths that must match element box height (line-height → a:spcPts).
 * Uses slide Y mapping — NOT font-calibrated pxToPoints — so N×line-height fits
 * the inspector-measured text box (otherwise the last line clips the card border).
 */
function pxToSlidePointsY(px) {
    return inchToPoints(pxToInchY(px));
}
/**
 * Sanitize a table position (inches) before passing it to pptxgenjs `addTable`.
 *
 * pptxgenjs treats any number `< 100` as inches, converts to EMU, then in
 * `addTable` re-runs `inch2Emu` when the result is still `< 20` — which is
 * true for every negative EMU. A later XML write calls `getSmartParseNumber`
 * again, so even a ~1px-negative table x explodes past OOXML
 * `ST_Coordinate` MinInclusive and PowerPoint reports the file as corrupt.
 *
 * Non-finite values become 0. Tiny negative leftovers (subpixel / transform
 * AABB) snap to 0 — visually negligible. Large negatives should not occur
 * once inspect uses document-space coords with scroll reset to origin.
 */
function clampPptxTablePositionInch(inch) {
    if (!Number.isFinite(inch))
        return 0;
    return Math.max(0, inch);
}
