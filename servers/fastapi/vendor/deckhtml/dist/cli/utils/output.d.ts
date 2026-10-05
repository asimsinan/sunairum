import type { DeckTask } from '../types/sdk';
import type { ConversionSimplifiedStats, ConversionStats, ConversionFontStats } from '../../conversion-report';
export type TaskOutputWriteResult = {
    kind: 'file';
    path: string;
} | {
    kind: 'directory';
    path: string;
    files: string[];
} | {
    kind: 'json';
    path: string;
};
export declare function writeTaskOutput(task: DeckTask, outPath: string, downloadResult: unknown): Promise<TaskOutputWriteResult>;
export interface ConversionResultEnvelope {
    ok: true;
    input: string[];
    output: string;
    /** All generated artifact paths (e.g. multi-page local PNG). */
    outputs?: string[];
    format: string;
    mode: string;
    slideCount?: number;
    stats?: ConversionStats;
    simplified?: ConversionSimplifiedStats;
    /** Path to the written report file (when --report is set). */
    report?: string;
    /** Structured per-element conversion report (DH-P0-002). */
    conversionReport?: import('../../conversion-report').DeckHtmlConversionReport;
    /** HTML → PPTX shape attribution for visual verify. */
    shapeMap?: import('../../types').ShapeMapEntry[];
}
export declare function attachSimplifiedToEnvelope(envelope: ConversionResultEnvelope): ConversionResultEnvelope;
/** PPTX-only: which elements were rasterized during simplified conversion. */
export declare function printSimplifiedNotice(simplified: ConversionSimplifiedStats | undefined, mode: string, quiet: boolean, jsonOutput: boolean): void;
/** PPTX-only: cloud embed library match tip. Not shown for PNG. */
export declare function printFontEmbedNotice(fonts: ConversionFontStats | undefined, mode: string, embedFonts: boolean, quiet: boolean, jsonOutput: boolean): void;
export declare function printSuccess(envelope: ConversionResultEnvelope, jsonOutput: boolean): void;
export declare function logVerbose(verbose: boolean, quiet: boolean, message: string): void;
export declare function logProgress(quiet: boolean, message: string): void;
