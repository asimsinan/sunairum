/**
 * CSS to PPTX style mapping utilities
 */
import { ComputedStyles, GradientData } from '../types';
import { PlatformFontContext, PlatformFontLang } from './platformFontMap';
/**
 * Sanitize text for XML/PPTX compatibility - remove control characters that cause Office repair
 * XML 1.0 allows: #x9, #xA, #xD, #x20-#xD7FF, #xE000-#xFFFD
 *
 * LLMs often emit vertical tab (U+000B) as a soft line hint. Deleting it glues
 * words ("Insert\u000bhere" → "Inserthere"); map C0 controls to a space instead.
 */
export declare function sanitizeTextForXml(text: string): string;
/**
 * Parse CSS color to hex format (RRGGBB without #) and extract alpha
 * PowerPoint uses hex colors without the # prefix
 * Returns { color: string, alpha?: number } where alpha is 0-1
 */
export declare function parseColor(color: string | undefined): {
    color: string;
    alpha?: number;
} | undefined;
/**
 * Parse font size from CSS to points (1:1 with CSS px via pxToPoints).
 * Viewport scaling (e.g. 1920→1280) is applied transparently inside `pxToPoints`.
 */
export declare function parseFontSize(fontSize: string | undefined): number;
/**
 * Font size for pill/chip badges (roundRect + text).
 * Use slide-space pt so glyph size matches the HTML border-box (px→inch geometry).
 * Preferring the larger font-calibrated size overflows tight chips in PPT.
 */
export declare function parsePillFontSize(fontSize: string | undefined): number;
/** Estimated text width in inches for a nowrap pill label at `fontSizePt`. */
export declare function estimatePillTextWidthInch(opts: {
    fontSizePt: number;
    text: string;
    bold?: boolean;
    charSpacingPt?: number;
}): number;
/**
 * Shrink pill font so estimated text width fits the content box (last resort).
 * Prefer {@link layoutPillBoxForText} (grow chip) so padding/font weight stay HTML-like.
 */
export declare function fitPillFontSizeToBox(opts: {
    fontSizePt: number;
    text: string;
    boxWidthInch: number;
    marginLeftPt: number;
    marginRightPt: number;
    bold?: boolean;
    charSpacingPt?: number;
}): number;
/**
 * Settle a chip's box, padding and font in one place.
 *
 * The order matters and is the whole point: the box grows into whatever room
 * the neighbours leave, then the chip's own padding gives way, and only then
 * the type. Padding is air; type is content. Held the other way round, a chip
 * whose growth was capped by the sibling on its right had nothing left but its
 * font, so the middle chips of a row shrank while the last one -- with open
 * space beside it -- kept full size.
 *
 * Both the conversion path and the pre-pass that agrees one size for a row call
 * this. They must, or they answer differently: a pre-pass that skipped the
 * padding step computed a harsher factor and imposed it on the whole row, and
 * chips that had been exporting at their authored size lost 20% of it.
 */
export declare function fitPillBox(opts: {
    fontSizePt: number;
    text: string;
    xInch: number;
    yInch: number;
    wInch: number;
    hInch: number;
    marginLeftPt: number;
    marginRightPt: number;
    marginTopPt: number;
    marginBottomPt: number;
    bold?: boolean;
    charSpacingPt?: number;
    maxGrowInch?: number;
    minLeftInch?: number;
    maxRightInch?: number;
    preferShrinkFont?: boolean;
}): {
    x: number;
    y: number;
    w: number;
    h: number;
    fontSizePt: number;
    marginLeftPt: number;
    marginRightPt: number;
};
/**
 * Grow a nowrap pill box so full HTML font size + CSS padding still fit in PPT metrics.
 * Shrinking the font first makes chips look “too tight” (padding air collapses).
 *
 * Optional sibling bounds (`minLeftInch` / `maxRightInch`) keep flex-row chips from
 * growing into neighbors. Compact chips can prefer shrink over large grow.
 */
export declare function layoutPillBoxForText(opts: {
    fontSizePt: number;
    text: string;
    xInch: number;
    yInch: number;
    wInch: number;
    hInch: number;
    marginLeftPt: number;
    marginRightPt: number;
    marginTopPt: number;
    marginBottomPt: number;
    bold?: boolean;
    charSpacingPt?: number;
    /** Cap how far we expand past the HTML box (default ~48 CSS px). */
    maxGrowInch?: number;
    /** Do not expand left of this edge (prior sibling in a flex row). */
    minLeftInch?: number;
    /** Do not expand right of this edge (next sibling in a flex row). */
    maxRightInch?: number;
    /** Prefer font shrink over growing into a tight flex gap. */
    preferShrinkFont?: boolean;
    /**
     * Chromium's own measurement of the text at the authored size, in inches.
     *
     * The estimator below is a model of PowerPoint's metrics, needed when the
     * reader's machine substitutes a face. This deck embeds its fonts, so
     * PowerPoint lays the text out with the very face Chromium measured, and the
     * model's safety margin becomes pessimism that gets paid for by shrinking
     * type. A measurement, where one exists, beats a model of one.
     */
    measuredContentWidthInch?: number;
}): {
    x: number;
    y: number;
    w: number;
    h: number;
    fontSizePt: number;
};
export interface ParseScriptFontFacesOptions {
    platformFontContext?: PlatformFontContext;
    specifiedFontFamily?: string;
    textScript?: PlatformFontLang;
}
/**
 * Parse font family, return first available font
 */
export declare function parseFontFamily(fontFamily: string | undefined, ctx?: PlatformFontContext, lang?: PlatformFontLang): string;
export interface ScriptFontFaces {
    latin: string;
    ea: string;
    cs?: string;
}
/**
 * Parse CSS font-family stack into PPTX script-specific faces.
 * - latin: first font in stack
 * - ea: first Chinese font in stack
 * - cs: only for ar/he scripts (complex script)
 */
export declare function parseScriptFontFaces(fontFamily: string | undefined, options?: ParseScriptFontFacesOptions): ScriptFontFaces;
/**
 * Check if font weight is bold
 * For numeric values: > 400 is treated as bold (500-900 map to bold in PPTX)
 */
export declare function isBold(fontWeight: string | undefined): boolean;
/**
 * If the primary font is Font Awesome Free (not Brands), return a discrete family name
 * (Solid vs Regular) from font-weight so multiple TTFs can be embedded without clashing.
 * Brands and non–Free families are left to the caller (returns undefined).
 */
export declare function normalizeFontAwesomeFreeFamily(fontFamily: string | undefined, fontWeight: string | undefined): string | undefined;
/**
 * Normalize any Font Awesome family (Free Solid/Regular, Brands, v4 Compatibility) to the
 * discrete PPTX face name that matches a pre-built EOT in assets/fonts/font-awesome/.
 * Returns undefined for non–Font Awesome stacks so the caller can fall back to the
 * normal script-face resolution.
 *
 * Brands bypass normalizeFontAwesomeFreeFamily because they are a separate family (not Free),
 * and their computed fontFamilySpecified can be wrong (e.g. inherited "Arial, sans-serif"),
 * which would otherwise let platform font mapping replace the FA face with Arial.
 */
export declare function normalizeFontAwesomeFamily(fontFamily: string | undefined, fontWeight: string | undefined): string | undefined;
/**
 * Check if font style is italic
 */
export declare function isItalic(fontStyle: string | undefined): boolean;
/**
 * Check if text has underline
 */
export declare function hasUnderline(textDecoration: string | undefined): boolean;
export declare function hasStrikethrough(textDecoration: string | undefined): boolean;
/**
 * Parse text alignment
 */
export declare function parseTextAlign(textAlign: string | undefined): 'left' | 'center' | 'right' | undefined;
/**
 * Parse opacity (0-1) to transparency percentage (0-100)
 */
export declare function parseTransparency(opacity: number | undefined): number;
/**
 * Parse border width from CSS
 * Using 0.5 ratio (px to pt) for better visual match
 * Empirically determined: 8px (web) ≈ 4pt (PowerPoint)
 */
export declare function parseBorderWidth(borderWidth: string | undefined): number;
/**
 * Map CSS border-style to pptxgenjs dashType
 * PowerPoint supports: solid, dash, dashDot, lgDash, lgDashDot, lgDashDotDot, sysDash, sysDot
 */
export declare function parseBorderStyleToDashType(borderStyle: string | undefined): 'solid' | 'dash' | 'dashDot' | 'lgDash' | 'lgDashDot' | 'lgDashDotDot' | 'sysDash' | 'sysDot';
/**
 * Parse padding from CSS to points
 * Converts padding values to match PowerPoint margin units
 */
export declare function parsePadding(padding: string | undefined): number;
/** Slide-space padding/border px → pt for text-box insets (not font-calibrated pxToPoints). */
export declare function parseBoxInsetPt(paddingPx: number, borderPx?: number): number;
/**
 * Parse letter spacing from CSS to points
 * Converts letter-spacing to PowerPoint character spacing (charSpacing)
 * Supports: normal, px, em (em needs fontSizePx for conversion)
 */
export declare function parseLetterSpacing(letterSpacing: string | undefined, fontSizePx?: number, pxToPt?: (px: number) => number, boost?: number): number | undefined;
/**
 * Parse line height from CSS to pptxgenjs lineSpacing (points) or lineSpacingMultiple
 * CSS line-height: normal | number (1.5) | length (24px, 1.5em) | percentage (150%)
 * pptxgenjs: lineSpacing (points, fixed) | lineSpacingMultiple (e.g. 1.5 = 150%)
 */
export declare function parseLineHeight(lineHeight: string | undefined, fontSizePx?: number): {
    lineSpacing?: number;
    lineSpacingMultiple?: number;
} | undefined;
/**
 * Parsed box-shadow result with classification
 */
export interface BoxShadowParsed {
    offsetX: number;
    offsetY: number;
    blur: number;
    spread: number;
    color: string;
    alpha: number;
    /** 'glow' when shadow wraps 3-4 sides, 'shadow' when 1-2 sides */
    effect: 'glow' | 'shadow';
}
/**
 * Parse box-shadow and classify as glow (all-around) or shadow (directional).
 *
 * Classification: count the sides where blur extends beyond the offset.
 *   visible extent on a side = blur - abs(offset towards that side)
 *   3-4 visible sides → glow, 1-2 → shadow
 */
export declare function parseBoxShadowClassified(boxShadow: string | undefined): BoxShadowParsed | undefined;
/**
 * Parse box shadow to PPTX shadow options (for directional shadows)
 */
export declare function parseBoxShadow(boxShadow: string | undefined): any;
/**
 * Extract blur radius (in px) from CSS filter string (e.g., "blur(20px) brightness(1.1)")
 */
export declare function parseBlurFilter(filter: string | undefined): number | undefined;
/**
 * Extract rotation in degrees from CSS transform.
 * Handles:
 * - Literal: "rotate(45deg)", "rotate(-0.25turn)"
 * - Computed: "matrix(a, b, c, d, e, f)" (browser returns this for rotate(45deg))
 * Returns value in range [-360, 360] for pptxgenjs, or undefined if no rotation.
 */
export declare function parseTransformRotate(transform: string | undefined): number | undefined;
/**
 * Map CSS `-webkit-text-stroke` to pptxgen `outline` (text stroke in PPT).
 */
export declare function parseWebkitTextStroke(styles: ComputedStyles): {
    widthPt: number;
    colorHex: string;
} | undefined;
/**
 * Get text options for pptxgenjs
 */
/**
 * Map CSS writing-mode to OOXML a:bodyPr @vert (ST_TextVerticalType).
 * vertical-rl: columns progress right-to-left → eaVert (East Asian vertical).
 * vertical-lr: columns progress left-to-right → vert.
 */
export declare function getOoxmlBodyPrVert(writingMode: string | undefined): string | undefined;
export type TextBoxHint = {
    width?: number;
    height?: number;
};
export declare function getTextOptions(styles: ComputedStyles, platformFontContext?: PlatformFontContext, text?: string, box?: TextBoxHint): any;
/** Visible CSS border on any side (outline chips use border without fill). */
export declare function hasVisibleBorder(styles: ComputedStyles): boolean;
export type PillBoxFlags = {
    /** Explicit <br> / soft breaks / multi-line wrap — not a nowrap chip. */
    multiLine?: boolean;
    /** Short label (≤3 words) that may have wrapped inside a tight circle. */
    shortLabel?: boolean;
};
/**
 * Pill/chip badge: rounded box with fill and/or outline that should map to one roundRect+text.
 * Covers filled inline pills, outline chips, and compact flex-item badges (blockified flex children).
 * Multi-line callouts (`<br>`, wrapping body) are excluded — they need wrap + height fit.
 */
export declare function isInlinePillBox(styles: ComputedStyles, box?: TextBoxHint, flags?: PillBoxFlags): boolean;
/**
 * Keep intentional soft-break lines on one line each (HTML `<br>` callouts) and ensure
 * the box height fits N×lineSpacing + padding — otherwise PPT wraps further and spills.
 */
export declare function fitTextBoxToIntentionalLines(opts: {
    lines: string[];
    fontSizePt: number;
    lineSpacingPt: number;
    xInch: number;
    yInch: number;
    wInch: number;
    hInch: number;
    marginLeftPt: number;
    marginRightPt: number;
    marginTopPt: number;
    marginBottomPt: number;
    bold?: boolean;
    charSpacingPt?: number;
    maxGrowInch?: number;
    /** Prefer expanding to the right (left-border callouts must not drift past their accent). */
    preferGrowRight?: boolean;
}): {
    x: number;
    y: number;
    w: number;
    h: number;
    fontSizePt: number;
    lineSpacingPt: number;
};
/**
 * Fit auto-wrapping titles/body so estimated wrap height stays inside the measured
 * HTML box (and optional sibling ceiling — e.g. a later accent bar). Widen first,
 * then shrink font; prefer not growing downward into decorative bands.
 */
export declare function fitWrappedTextBox(opts: {
    text: string;
    fontSizePt: number;
    lineSpacingPt: number;
    xInch: number;
    yInch: number;
    wInch: number;
    hInch: number;
    marginLeftPt?: number;
    marginRightPt?: number;
    marginTopPt?: number;
    marginBottomPt?: number;
    bold?: boolean;
    charSpacingPt?: number;
    /** Do not let text bottom exceed this (later accent / sibling). */
    maxBottomInch?: number;
    maxGrowInch?: number;
    /** Do not expand left of this edge (opaque panel to the left). */
    minLeftInch?: number;
    /** Do not expand right of this edge (opaque panel to the right). */
    maxRightInch?: number;
    /** Prefer font shrink over growing into a nearby column wall. */
    preferShrinkFont?: boolean;
}): {
    x: number;
    y: number;
    w: number;
    h: number;
    fontSizePt: number;
    lineSpacingPt: number;
};
/** True when background-color is a visible fill (not transparent). */
export declare function isVisibleTextBackgroundColor(backgroundColor: string | undefined): boolean;
/**
 * Map CSS inline/element background-color to pptxgenjs text highlight (OOXML a:highlight).
 * PPT highlight is opaque; semi-transparent CSS backgrounds are composited on the backdrop.
 */
export declare function parseTextHighlightColor(backgroundColor: string | undefined, backdropColor?: string): string | undefined;
/**
 * Approximate how many spaces emulate CSS margin-left on an inline run (proportional to font size).
 */
export declare function marginLeftPxToLeadingSpaces(marginLeftPx: number, fontSizePx: number): number;
/**
 * PPT a:highlight only covers glyphs — pad inline highlighted runs with spaces (same run options).
 */
export declare function expandRunTextForInlineHighlightPadding(text: string, styles: ComputedStyles): string;
/** The element box a background paints into, in CSS px. */
export type GradientBox = {
    width: number;
    height: number;
};
/** Area coverage of a background-image: the color it paints and how much of the box it covers. */
export type GradientCoverage = {
    color: string;
    alpha: number;
};
/**
 * Measure what a background-image actually paints: its average color and the fraction of the
 * box that color covers. Layers composite source-over, first layer on top, exactly as CSS
 * paints them. Callers can then honour `background-color` showing through instead of guessing
 * from stop alpha alone.
 */
export declare function parseGradientCoverage(backgroundImage: string | undefined, backgroundSize?: string, box?: GradientBox): GradientCoverage | undefined;
/**
 * Extract first url() from background-image (e.g. "linear-gradient(...), url('...')")
 * Returns the URL string or undefined if no url found
 */
export declare function parseBackgroundImageUrl(backgroundImage: string | undefined): string | undefined;
/**
 * Parse complete gradient information (new function for style enhancement)
 * Returns full gradient data with angle, color stops, etc.
 */
export declare function parseGradientFull(backgroundImage: string | undefined, box?: GradientBox, backgroundSize?: string): GradientData | undefined;
/**
 * Get shape fill options for pptxgenjs
 */
export declare function getFillOptions(styles: ComputedStyles, box?: GradientBox): any;
/**
 * Parse border radius from CSS to inches
 */
export declare function parseBorderRadius(borderRadius: string | undefined, widthPx?: number, heightPx?: number): number | undefined;
/**
 * Parse individual corner radii from CSS border-radius
 * Returns [topLeft, topRight, bottomRight, bottomLeft] in inches
 * CSS border-radius format:
 * - 1 value: all corners
 * - 2 values: [top-left & bottom-right, top-right & bottom-left]
 * - 3 values: [top-left, top-right & bottom-left, bottom-right]
 * - 4 values: [top-left, top-right, bottom-right, bottom-left]
 */
export declare function parseCornerRadii(borderRadius: string | undefined, widthPx?: number, heightPx?: number): [number, number, number, number];
/**
 * Get border/line options for pptxgenjs
 * Handles rgba alpha → PowerPoint transparency (0 = opaque, 100 = full transparent)
 */
export declare function getLineOptions(styles: ComputedStyles): any;
/**
 * Get table cell border options for pptxgenjs
 * Returns border: [top, right, bottom, left] - each side is {type, pt, color} or null
 * pptxgenjs table borders do not support transparency; semi-transparent CSS borders are
 * composited onto the cell's effective background (from inspector).
 */
export declare function getTableCellBorderOptions(styles: any, effectiveBackgroundColor?: string): any[] | undefined;
