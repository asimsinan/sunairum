"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.normalizeUniqueShapeIds = normalizeUniqueShapeIds;
const jszip_1 = __importDefault(require("jszip"));
/**
 * Make non-visual drawing-property ids unique within every slide.
 *
 * PptxGenJS allocates ids independently for some late-added native objects
 * (notably tables).  When DeckHTML mixes those objects with shapes already on
 * the slide, two cNvPr nodes can receive the same id.  PowerPoint treats that
 * as corrupt OOXML even though the package is well-formed and LibreOffice is
 * able to open it.  Preserve the first occurrence (and therefore any timing
 * reference to it) and deterministically renumber later occurrences.
 */
async function normalizeUniqueShapeIds(data) {
    const zip = await jszip_1.default.loadAsync(data);
    const entries = Object.keys(zip.files).filter((name) => /^ppt\/slides\/slide\d+\.xml$/.test(name));
    for (const entry of entries) {
        let xml = await zip.files[entry].async('string');
        const matches = [...xml.matchAll(/<p:cNvPr\b[^>]*\bid="(\d+)"/g)];
        if (matches.length < 2)
            continue;
        const used = new Set();
        let nextId = Math.max(...matches.map((match) => Number(match[1]))) + 1;
        let cursor = 0;
        let normalized = '';
        for (const match of matches) {
            const start = match.index;
            const original = match[0];
            const id = Number(match[1]);
            normalized += xml.slice(cursor, start);
            if (used.has(id)) {
                while (used.has(nextId))
                    nextId += 1;
                normalized += original.replace(/\bid="\d+"/, `id="${nextId}"`);
                used.add(nextId);
                nextId += 1;
            }
            else {
                normalized += original;
                used.add(id);
            }
            cursor = start + original.length;
        }
        normalized += xml.slice(cursor);
        if (normalized !== xml)
            zip.file(entry, normalized);
    }
    return zip.generateAsync({ type: 'nodebuffer' });
}
