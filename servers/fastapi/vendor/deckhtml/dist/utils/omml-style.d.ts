/**
 * Apply presentation hints (color, size) to OMML produced by mathml2omml.
 *
 * PowerPoint is strict: use only valid children inside m:rPr (w:color, m:sz).
 * Do NOT insert DrawingML a:solidFill or a sibling w:rPr block — both can trigger repair.
 */
import { ElementInfo } from '../types';
export interface MathPresentationMeta {
    colorHex?: string;
    szHalfPt?: number;
    mathJc: 'left' | 'center' | 'right';
}
/**
 * Legacy dampening factor (no longer applied when host-box scaling is used).
 * Kept for callers/tests that import the constant.
 */
export declare const PPT_MATH_A_RPR_SZ_FACTOR = 1;
/** Nested `<mfrac>` depth in MathML (0 = no fraction). */
export declare function mathFractionDepth(mathml: string | undefined): number;
/**
 * Font size so Office Math (esp. fractions) fits inside the formula plate with air.
 *
 * Prior `0.38 * hostH` assumed single-line glyphs; a fraction paints ~2.5–3.4× that
 * tall and clipped the blue host. Scale from usable height after padding + breathing room.
 */
export declare function fitMathFontSizePx(opts: {
    hostH: number;
    hostW?: number;
    computedFs?: number;
    mathml?: string;
    paddingTopPx?: number;
    paddingBottomPx?: number;
}): number;
/** True when CSS text color is light (e.g. #f8fafc on dark slides). */
export declare function isLightTextColor(styles: {
    color?: string;
}): boolean;
/**
 * Derive OMML color/size/alignment from the inspected <math> element.
 */
export declare function getMathPresentationMeta(element: ElementInfo): MathPresentationMeta;
/**
 * Safety net: hat/dot overscripts that still arrived as limUpp (limit) → m:acc.
 * PowerPoint draws limUpp marks far above the base; accents sit tight.
 */
export declare function rewriteLimUppAccentsToOmmlAcc(omml: string): string;
export declare function sanitizeOmmlForPptx(omml: string): string;
/** Remove WordprocessingML tags when slide root has no xmlns:w (post-equation safety net). */
export declare function stripUndeclaredWordMlFromSlide(slideXml: string): string;
