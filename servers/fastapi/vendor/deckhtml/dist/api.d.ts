/**
 * API Module
 * Main conversion function for programmatic use
 */
import { ConversionOptions, ConversionResult } from './types';
/**
 * Inspect HTML inputs and collect slide/element/font statistics without generating PPTX.
 */
export declare function inspectHtmlFonts(options: ConversionOptions): Promise<{
    usedFonts: string[];
    slideCount: number;
    stats: NonNullable<ConversionResult['stats']>;
}>;
/**
 * Convert one or more HTML/SVG files to a single PPTX.
 * Each input file becomes one slide by default; use slideSelector or splitByHeight
 * within a file to produce multiple slides from that file.
 */
export declare function convertHtmlToPptx(options: ConversionOptions): Promise<ConversionResult>;
export default convertHtmlToPptx;
