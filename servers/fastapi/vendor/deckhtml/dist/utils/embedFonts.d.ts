import { EMBED_FONT_INDEX_META } from './embedFonts.index';
export { EMBED_FONT_INDEX_META };
export interface FontEmbedMatch {
    /** Font family name used in the presentation */
    used: string;
    /** Matched family name in the cloud embed font library */
    matchedFamily: string;
}
export interface FontEmbedProbeResult {
    matched: FontEmbedMatch[];
    unmatched: string[];
    indexMeta: typeof EMBED_FONT_INDEX_META;
}
/** Match a single font-family token or stack against the embed font library. */
export declare function matchEmbeddableFont(fontNameOrStack: string): string | null;
/** Probe which presentation font families can be embedded from the cloud library. */
export declare function probeEmbeddableFonts(usedFamilies: string[]): FontEmbedProbeResult;
