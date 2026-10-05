"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.EMBED_FONT_INDEX_META = void 0;
exports.matchEmbeddableFont = matchEmbeddableFont;
exports.probeEmbeddableFonts = probeEmbeddableFonts;
const chineseFonts_1 = require("./chineseFonts");
const embedFonts_index_1 = require("./embedFonts.index");
Object.defineProperty(exports, "EMBED_FONT_INDEX_META", { enumerable: true, get: function () { return embedFonts_index_1.EMBED_FONT_INDEX_META; } });
function toSearchKey(name) {
    return name
        .normalize('NFKC')
        .toLowerCase()
        .replace(/[^a-z0-9\u4e00-\u9fff]/g, '');
}
function lookupFamily(name) {
    const candidates = [
        toSearchKey(name),
        toSearchKey((0, chineseFonts_1.extractCoreFontName)(name)),
    ].filter((key) => key.length >= 2);
    for (const key of candidates) {
        const family = embedFonts_index_1.EMBED_FONT_SEARCH_INDEX[key];
        if (family)
            return family;
    }
    return null;
}
/** Match a single font-family token or stack against the embed font library. */
function matchEmbeddableFont(fontNameOrStack) {
    const tokens = fontNameOrStack.includes(',') ? (0, chineseFonts_1.splitFontStack)(fontNameOrStack) : [fontNameOrStack];
    for (const raw of tokens) {
        const family = lookupFamily(raw);
        if (family)
            return family;
    }
    return null;
}
/** Probe which presentation font families can be embedded from the cloud library. */
function probeEmbeddableFonts(usedFamilies) {
    const matched = [];
    const unmatched = [];
    const seenMatched = new Set();
    const seenUnmatched = new Set();
    for (const used of usedFamilies) {
        const family = matchEmbeddableFont(used);
        if (family) {
            const key = `${used}\0${family}`;
            if (!seenMatched.has(key)) {
                seenMatched.add(key);
                matched.push({ used, matchedFamily: family });
            }
        }
        else if (!seenUnmatched.has(used)) {
            seenUnmatched.add(used);
            unmatched.push(used);
        }
    }
    matched.sort((a, b) => a.used.localeCompare(b.used));
    unmatched.sort((a, b) => a.localeCompare(b));
    return {
        matched,
        unmatched,
        indexMeta: embedFonts_index_1.EMBED_FONT_INDEX_META,
    };
}
