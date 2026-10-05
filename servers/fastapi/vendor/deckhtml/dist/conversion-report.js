"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ReportCollector = exports.EMPTY_CONVERSION_STATS = exports.matchEmbeddableFont = exports.probeEmbeddableFonts = void 0;
exports.buildElementStats = buildElementStats;
exports.buildSimplifiedStats = buildSimplifiedStats;
exports.buildFontStats = buildFontStats;
exports.buildConversionReport = buildConversionReport;
exports.recomputeSummary = recomputeSummary;
const embedFonts_1 = require("./utils/embedFonts");
var embedFonts_2 = require("./utils/embedFonts");
Object.defineProperty(exports, "probeEmbeddableFonts", { enumerable: true, get: function () { return embedFonts_2.probeEmbeddableFonts; } });
Object.defineProperty(exports, "matchEmbeddableFont", { enumerable: true, get: function () { return embedFonts_2.matchEmbeddableFont; } });
function countByType(elements) {
    const counts = {};
    for (const el of elements) {
        counts[el.type] = (counts[el.type] ?? 0) + 1;
    }
    return counts;
}
function mergeCounts(target, source) {
    for (const [type, count] of Object.entries(source)) {
        target[type] = (target[type] ?? 0) + count;
    }
}
function buildElementStats(slidesMap) {
    const slides = [];
    const byType = {};
    let total = 0;
    const indices = [...slidesMap.keys()].sort((a, b) => a - b);
    for (const index of indices) {
        const elements = slidesMap.get(index) ?? [];
        const slideByType = countByType(elements);
        const slideTotal = elements.length;
        total += slideTotal;
        mergeCounts(byType, slideByType);
        slides.push({ index, total: slideTotal, byType: slideByType });
    }
    return { total, byType, slides };
}
function buildSimplifiedStats(slidesMap) {
    const byMethod = {};
    const byReason = {};
    const slides = [];
    const items = [];
    let total = 0;
    const indices = [...slidesMap.keys()].sort((a, b) => a - b);
    for (const index of indices) {
        const elements = slidesMap.get(index) ?? [];
        const slideByReason = {};
        let slideTotal = 0;
        for (const el of elements) {
            if (!el.rasterMethod || !el.rasterReason)
                continue;
            slideTotal++;
            total++;
            byMethod[el.rasterMethod] = (byMethod[el.rasterMethod] ?? 0) + 1;
            byReason[el.rasterReason] = (byReason[el.rasterReason] ?? 0) + 1;
            slideByReason[el.rasterReason] = (slideByReason[el.rasterReason] ?? 0) + 1;
            items.push({
                slide: index,
                type: el.type,
                tag: el.tag,
                method: el.rasterMethod,
                reason: el.rasterReason,
                x: Math.round(el.x),
                y: Math.round(el.y),
                width: Math.round(el.width),
                height: Math.round(el.height),
            });
        }
        if (slideTotal > 0) {
            slides.push({ index, total: slideTotal, byReason: slideByReason });
        }
    }
    return { total, byMethod, byReason, slides, items };
}
function buildFontStats(usedFontsMap) {
    const variants = [...usedFontsMap.values()].sort((a, b) => {
        const fam = a.fontFamily.localeCompare(b.fontFamily);
        if (fam !== 0)
            return fam;
        const bold = Number(Boolean(b.bold)) - Number(Boolean(a.bold));
        if (bold !== 0)
            return bold;
        return Number(Boolean(b.italic)) - Number(Boolean(a.italic));
    });
    const families = [...new Set(variants.map((d) => d.fontFamily))].sort();
    const embed = (0, embedFonts_1.probeEmbeddableFonts)(families);
    return { families, variants, embed };
}
function buildConversionReport(params) {
    return {
        version: 1,
        generatedAt: new Date().toISOString(),
        input: params.input,
        output: params.output,
        format: params.format,
        mode: params.mode,
        slideCount: params.slideCount,
        elements: params.stats.elements,
        fonts: params.stats.fonts,
        simplified: params.stats.simplified,
        ...(params.viewport ? { viewport: params.viewport } : {}),
        ...(params.platform ? { platform: params.platform } : {}),
        ...(params.durationMs !== undefined ? { durationMs: params.durationMs } : {}),
    };
}
exports.EMPTY_CONVERSION_STATS = {
    elements: { total: 0, byType: {}, slides: [] },
    fonts: { families: [], variants: [] },
    simplified: { total: 0, byMethod: {}, byReason: {}, slides: [], items: [] },
};
/**
 * Mutable collector used by the generator to build the per-element report.
 */
class ReportCollector {
    constructor() {
        this.slides = [];
        this.diagnostics = [];
        /** Number of elements excluded before reaching the generator (ignored). */
        this.ignoredCount = 0;
    }
    startSlide(slideId, index) {
        this.slides.push({ slide_id: slideId, index, elements: [] });
    }
    addElement(record) {
        const slide = this.slides[this.slides.length - 1];
        if (slide)
            slide.elements.push(record);
    }
    build(engineName, engineVersion, status) {
        const summary = {
            native: 0,
            vector: 0,
            raster: 0,
            ignored: this.ignoredCount,
            unsupported: 0,
        };
        for (const slide of this.slides) {
            for (const rec of slide.elements) {
                summary[rec.mapping_mode]++;
            }
        }
        // Stable sort: slides by index, elements kept in insertion (DOM) order.
        this.slides.sort((a, b) => a.index - b.index);
        return {
            schema_version: 1,
            engine: { name: engineName, version: engineVersion },
            status,
            slides: this.slides,
            summary,
            diagnostics: this.diagnostics,
        };
    }
}
exports.ReportCollector = ReportCollector;
/**
 * Recompute the summary counts from per-element records (DH-P0-003).
 *
 * The summary is always derivable from `slides[].elements[].mapping_mode` plus
 * the ignored count, so callers can verify the report was not tampered with
 * and strict-mode gates can re-check after any post-processing.
 */
function recomputeSummary(report, ignoredCount = 0) {
    const summary = {
        native: 0,
        vector: 0,
        raster: 0,
        ignored: ignoredCount,
        unsupported: 0,
    };
    for (const slide of report.slides) {
        for (const rec of slide.elements) {
            summary[rec.mapping_mode]++;
        }
    }
    return summary;
}
