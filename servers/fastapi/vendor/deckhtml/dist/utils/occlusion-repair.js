"use strict";
/**
 * Clear text that would sit under later opaque panels/tables in PPTX.
 *
 * HTML absolute layouts sometimes place a claim/table host through a title or
 * subtitle. In the browser the later paint wins; deckhtml would otherwise emit
 * both shapes and leave “ghost” text under the panel. Push the occluder down
 * (and shrink height to stay on-slide) so body content clears the text stack.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.repairTextOcclusions = repairTextOcclusions;
const coordinate_1 = require("./coordinate");
const style_1 = require("./style");
const CLEAR_GAP_PX = 12;
const MIN_OVERLAP_X_PX = 28;
const MIN_OVERLAP_Y_PX = 10;
const MIN_TEXT_CHARS = 8;
const MIN_COVER_AREA = 8000;
const MAX_PASSES = 4;
function rectsOverlap(a, b, padX = 0, padY = 0) {
    return !(a.x + a.width <= b.x + padX ||
        b.x + b.width <= a.x + padX ||
        a.y + a.height <= b.y + padY ||
        b.y + b.height <= a.y + padY);
}
function overlapExtents(a, b) {
    const ox = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x));
    const oy = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
    return { ox, oy };
}
function textPayload(el) {
    if (el.content && el.content.trim())
        return el.content.trim();
    if (el.richText?.length) {
        return el.richText
            .map((r) => (r.text || '').trim())
            .filter(Boolean)
            .join(' ');
    }
    return '';
}
function isTextVictim(el) {
    if (el.type !== 'text' && el.type !== 'icon')
        return false;
    const t = textPayload(el);
    if (t.length < MIN_TEXT_CHARS)
        return false;
    if (el.width < 40 || el.height < 10)
        return false;
    return true;
}
function bgAlpha(el) {
    const parsed = (0, style_1.parseColor)(el.styles?.backgroundColor);
    if (!parsed)
        return 0;
    if (typeof parsed.alpha === 'number')
        return parsed.alpha;
    // parseColor omits alpha when fully opaque
    return 1;
}
function isOpaqueCover(el) {
    if (el.width * el.height < MIN_COVER_AREA)
        return false;
    // Full-bleed slide backgrounds must not be nudged.
    const slideArea = (0, coordinate_1.getSlideWidthPx)() * (0, coordinate_1.getSlideHeightPx)();
    if (el.width * el.height >= slideArea * 0.55)
        return false;
    if (el.type === 'table' || el.type === 'image' || el.type === 'canvas')
        return true;
    if (el.dataUrl || el.needsScreenshot)
        return true;
    if (el.type === 'shape' || el.type === 'container') {
        return bgAlpha(el) >= 0.35;
    }
    // Text boxes with solid fills act as panels too (rare).
    if (el.type === 'text' && bgAlpha(el) >= 0.5 && el.width * el.height >= MIN_COVER_AREA) {
        return true;
    }
    return false;
}
function paintRank(el, index) {
    return typeof el.paintOrder === 'number' ? el.paintOrder : index;
}
/**
 * Mutates element geometry so opaque hosts clear earlier text they would cover.
 */
function repairTextOcclusions(elements) {
    if (!elements.length)
        return { changed: false, nudged: 0 };
    const slideH = (0, coordinate_1.getSlideHeightPx)();
    let nudged = 0;
    for (let pass = 0; pass < MAX_PASSES; pass++) {
        let passNudged = 0;
        const texts = elements
            .map((el, index) => ({ el, index }))
            .filter(({ el }) => isTextVictim(el));
        for (let i = 0; i < elements.length; i++) {
            const cover = elements[i];
            if (!isOpaqueCover(cover))
                continue;
            const coverRank = paintRank(cover, i);
            let clearBottom = -Infinity;
            for (const { el: text, index: ti } of texts) {
                if (text === cover)
                    continue;
                if (paintRank(text, ti) >= coverRank)
                    continue; // text paints on/after cover
                const { ox, oy } = overlapExtents(text, cover);
                if (ox < MIN_OVERLAP_X_PX || oy < MIN_OVERLAP_Y_PX)
                    continue;
                if (!rectsOverlap(text, cover))
                    continue;
                clearBottom = Math.max(clearBottom, text.y + text.height);
            }
            if (!Number.isFinite(clearBottom) || clearBottom <= cover.y - CLEAR_GAP_PX)
                continue;
            const targetTop = clearBottom + CLEAR_GAP_PX;
            const dy = targetTop - cover.y;
            if (dy < 1)
                continue;
            const oldBottom = cover.y + cover.height;
            cover.y = targetTop;
            // Prefer keeping the original bottom when it still fits; else clamp to slide.
            const maxH = Math.max(40, slideH - 28 - cover.y);
            const keepBottomH = oldBottom - cover.y;
            cover.height = Math.max(40, Math.min(maxH, keepBottomH > 40 ? keepBottomH : cover.height));
            passNudged += 1;
        }
        nudged += passNudged;
        if (passNudged === 0)
            break;
    }
    return { changed: nudged > 0, nudged };
}
