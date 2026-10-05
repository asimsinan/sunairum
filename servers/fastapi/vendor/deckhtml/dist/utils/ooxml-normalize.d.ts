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
export declare function normalizeUniqueShapeIds(data: Buffer): Promise<Buffer>;
