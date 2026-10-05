"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.embedFontAwesomeFonts = embedFontAwesomeFonts;
/**
 * Font Awesome font embedder for PPTX — thin wrapper around embedDeckFonts.
 *
 * Historical entry point kept for public API stability. Local conversion now
 * embeds all resolvable deck faces (FA + Source/Inter/Barlow/…) via
 * `embedDeckFonts`; calling this still embeds FA when present.
 */
const deck_font_embedder_1 = require("./deck-font-embedder");
/**
 * Embed Font Awesome (and any other resolvable deck) fonts referenced by the PPTX.
 * @deprecated Prefer `embedDeckFonts` — this remains as a stable alias.
 */
async function embedFontAwesomeFonts(pptxData) {
    return (0, deck_font_embedder_1.embedDeckFonts)(pptxData);
}
