import type { ElementInfo, RasterMethod, RasterReason, UsedFontDescriptor } from './types';
import { type FontEmbedProbeResult } from './utils/embedFonts';
export type { FontEmbedMatch, FontEmbedProbeResult } from './utils/embedFonts';
export { probeEmbeddableFonts, matchEmbeddableFont } from './utils/embedFonts';
export type ElementTypeCounts = Record<string, number>;
export interface SlideElementStats {
    index: number;
    total: number;
    byType: ElementTypeCounts;
}
export interface ConversionElementStats {
    total: number;
    byType: ElementTypeCounts;
    slides: SlideElementStats[];
}
export interface ConversionFontStats {
    families: string[];
    variants: UsedFontDescriptor[];
    /** Probe result against the cloud embed font library (../../fonts/fonts-index.ts) */
    embed?: FontEmbedProbeResult;
}
export interface SimplifiedElementEntry {
    slide: number;
    type: string;
    tag: string;
    method: RasterMethod;
    reason: RasterReason;
    x: number;
    y: number;
    width: number;
    height: number;
}
export interface SlideSimplifiedStats {
    index: number;
    total: number;
    byReason: Record<string, number>;
}
export interface ConversionSimplifiedStats {
    total: number;
    byMethod: Record<string, number>;
    byReason: Record<string, number>;
    slides: SlideSimplifiedStats[];
    items: SimplifiedElementEntry[];
}
export interface ConversionStats {
    elements: ConversionElementStats;
    fonts: ConversionFontStats;
    simplified: ConversionSimplifiedStats;
}
export interface ConversionReport {
    version: 1;
    generatedAt: string;
    input: string[];
    output: string;
    format: string;
    mode: string;
    slideCount: number;
    elements: ConversionElementStats;
    fonts: ConversionFontStats;
    simplified: ConversionSimplifiedStats;
    viewport?: {
        width: number;
        height: number;
    };
    platform?: string;
    durationMs?: number;
}
export declare function buildElementStats(slidesMap: Map<number, ElementInfo[]>): ConversionElementStats;
export declare function buildSimplifiedStats(slidesMap: Map<number, ElementInfo[]>): ConversionSimplifiedStats;
export declare function buildFontStats(usedFontsMap: Map<string, UsedFontDescriptor>): ConversionFontStats;
export declare function buildConversionReport(params: {
    input: string[];
    output: string;
    format: string;
    mode: string;
    slideCount: number;
    stats: ConversionStats;
    viewport?: {
        width: number;
        height: number;
    };
    platform?: string;
    durationMs?: number;
}): ConversionReport;
export declare const EMPTY_CONVERSION_STATS: ConversionStats;
export type MappingMode = 'native' | 'vector' | 'raster' | 'ignored' | 'unsupported';
export interface ElementGeometry {
    x: number;
    y: number;
    w: number;
    h: number;
    unit: 'inch' | 'px';
}
export interface ElementReportRecord {
    element_id: string | null;
    kind: string;
    mapping_mode: MappingMode;
    object_ref: string | null;
    geometry: ElementGeometry;
    warnings: import('./utils/diagnostics').Diagnostic[];
}
export interface SlideReport {
    slide_id: string;
    index: number;
    elements: ElementReportRecord[];
}
export interface ConversionReportSummary {
    native: number;
    vector: number;
    raster: number;
    ignored: number;
    unsupported: number;
}
export interface DeckHtmlConversionReport {
    schema_version: 1;
    engine: {
        name: string;
        version: string;
    };
    status: 'succeeded' | 'failed';
    slides: SlideReport[];
    summary: ConversionReportSummary;
    diagnostics: import('./utils/diagnostics').Diagnostic[];
}
/**
 * Mutable collector used by the generator to build the per-element report.
 */
export declare class ReportCollector {
    readonly slides: SlideReport[];
    readonly diagnostics: import('./utils/diagnostics').Diagnostic[];
    /** Number of elements excluded before reaching the generator (ignored). */
    ignoredCount: number;
    startSlide(slideId: string, index: number): void;
    addElement(record: ElementReportRecord): void;
    build(engineName: string, engineVersion: string, status: 'succeeded' | 'failed'): DeckHtmlConversionReport;
}
/**
 * Recompute the summary counts from per-element records (DH-P0-003).
 *
 * The summary is always derivable from `slides[].elements[].mapping_mode` plus
 * the ignored count, so callers can verify the report was not tampered with
 * and strict-mode gates can re-check after any post-processing.
 */
export declare function recomputeSummary(report: DeckHtmlConversionReport, ignoredCount?: number): ConversionReportSummary;
