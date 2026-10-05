/**
 * L1 layout-faithful text — contract constants + pure helpers.
 * Browser-side line capture lives inside inspector page.evaluate;
 * Node-side eligibility / freeze decisions live here.
 */
import type { ElementInfo, TextLineBox, TextRun, LayoutFaithfulMode } from '../types';
/** Max relative font shrink allowed inside a frozen box (reported). */
export declare const LAYOUT_FAITHFUL_MAX_FONT_SHRINK = 0.08;
/** Geometry tolerance in CSS source pixels after EMU round-trip. */
export declare const LAYOUT_FAITHFUL_GEOM_TOL_PX = 1;
/** Reference slide (matches coordinate.ts). */
export declare const LAYOUT_FAITHFUL_SLIDE_W_IN = 10;
export declare const LAYOUT_FAITHFUL_SLIDE_H_IN = 5.625;
export declare const LAYOUT_FAITHFUL_VIEW_W_PX = 1280;
export declare const LAYOUT_FAITHFUL_VIEW_H_PX = 720;
export type LayoutFaithfulIneligibility = 'disabled' | 'not_text' | 'vertical_writing' | 'rtl_or_bidi' | 'unsupported_transform' | 'non_rect_clip' | 'pill_path' | 'math_or_formula' | 'table_or_chart' | 'svg_foreign' | 'ambiguous_line_map' | 'no_lines' | 'empty_text';
export declare function resolveLayoutFaithfulMode(option?: LayoutFaithfulMode | true, env?: NodeJS.ProcessEnv): LayoutFaithfulMode;
export declare function isLayoutFaithfulStrict(mode: LayoutFaithfulMode): boolean;
/** Detect CSS writing-mode that is not ordinary horizontal. */
export declare function isVerticalWritingMode(writingMode?: string): boolean;
export declare function classifyLayoutFaithfulEligibility(el: ElementInfo, opts?: {
    isPillBox?: boolean;
}): {
    eligible: boolean;
    reason?: LayoutFaithfulIneligibility;
};
/**
 * Inject softBreakBefore on rich runs at Chromium wrap boundaries.
 *
 * Whitespace-tolerant: alignment happens in "condensed" space (all whitespace
 * removed) because line capture and rich-text extraction collapse spaces
 * differently. Boundaries land on the first non-space character of each line.
 */
export declare function applyChromiumSoftBreaks(richText: TextRun[] | undefined, lines: TextLineBox[] | undefined, content?: string): TextRun[] | undefined;
/**
 * Synthesize rich runs directly from captured line boxes when the host has a
 * single style (no richText). Every line becomes one run; lines 2+ carry
 * softBreakBefore so PPTX emits `<a:br/>` exactly at Chromium wrap points.
 */
export declare function buildRunsFromLines(styles: TextRun['styles'], lines: TextLineBox[] | undefined, content?: string): TextRun[] | undefined;
/**
 * Line pitch (px) of a captured block: the distance between consecutive line boxes.
 *
 * A captured line's `height` is its glyph box — ascent plus descent — which for most faces is
 * taller than the CSS line box holding it (a 64px Georgia measures ~73px against a 67.8px
 * line-height). Summing those heights therefore claims a three-line heading needs more room
 * than the three-line frame Chromium measured it in, which is impossible; the frozen path
 * answered that phantom overflow by shrinking the font and stretching the pitch, and the text
 * walked out of its box. Consecutive line tops give the pitch the renderer must reproduce.
 */
export declare function layoutLinePitchPx(lines: TextLineBox[] | undefined): number;
/** Bound font shrink: return new size (pt) and whether shrink was applied. */
export declare function boundFontShrink(fontSizePt: number, needScale: number): {
    fontSizePt: number;
    shrunk: boolean;
    scale: number;
};
/** Reconstruct normalized text from layout lines. */
export declare function reconstructFromLines(lines: TextLineBox[]): string;
