/**
 * HTML → PNG export via Playwright viewport screenshots.
 */
import { type ConversionStats } from './conversion-report';
import type { ConversionOptions } from './types';
export interface PngConversionResult {
    /** One PNG buffer per detected page/slide, in order. */
    images: Buffer[];
    slideCount: number;
    stats?: ConversionStats;
}
/**
 * Convert HTML input(s) to one or more PNG buffers using Playwright screenshots.
 * Multi-slide decks and multi-file inputs produce one image per page, in order.
 * Multiple HTML files are processed concurrently (CPU cores − 2), matching PPTX.
 */
export declare function convertHtmlToPng(options: ConversionOptions): Promise<PngConversionResult>;
