/**
 * Element Converter Module
 * Converts DOM elements to pptxgenjs objects
 */
import { ElementInfo, UsedFontDescriptor } from './types';
import { PlatformFontContext } from './utils/platformFontMap';
import { StyleEnhancementRegistry } from './enhancer/registry';
export declare class ElementConverter {
    private registry;
    private fontResolver?;
    private platformFontContext?;
    /** HTML-measured pill boxes on the current slide (flex-row collision caps). */
    private pillPeerRects;
    private pillPeerSlideIndex;
    /** Emitted wrapping titles — thin accent bars must not paint through them. */
    private textBands;
    /** Thin HTML accent bars (underlines) — title wrap must not spill into them. */
    private accentBands;
    /** Large opaque panels — wrapping titles must not grow into them. */
    private columnWalls;
    /** Bottom-right page chrome — callouts must not grow into this band. */
    private chromeBands;
    private textBandSlideIndex;
    /** One measured shrink factor shared by repeated semantic text peers. */
    private peerTypographyScales;
    /** The same discipline for chips, whose size is settled by the pill path. */
    private pillPeerScales;
    /**
     * Clearance between title ink (incl. serif descenders) and a thin accent rule.
     * 4px was too tight for Georgia/Times — PPT drew the bar through q/g/y.
     */
    private static readonly ACCENT_DESCENDER_CLEAR_PX;
    /** L1 diagnostics from this conversion (fallback / shrink). */
    readonly layoutFaithfulNotes: Array<{
        elementId?: string;
        reason: string;
        message: string;
    }>;
    constructor(registry: StyleEnhancementRegistry, fontResolver?: (d: UsedFontDescriptor) => string, platformFontContext?: PlatformFontContext);
    /**
     * Reset per-slide pill peers from measured HTML boxes so early chips cannot
     * grow into later siblings in the same flex row.
     */
    beginSlide(slideIndex: number, elements?: ElementInfo[], slideStartY?: number): void;
    /**
     * The size a row of chips will agree on.
     *
     * A chip may only grow into the gap that happens to sit beside it, so the
     * last chip in a row -- with open space to its right -- kept its authored
     * size while its neighbours were squeezed: three chips written identically
     * exported at 8.2pt, 7.0pt and 9.0pt. Each had negotiated alone. This settles
     * the question once for the whole row, before any member is laid out, the way
     * `measurePeerTypographyScales` already does for repeated cards.
     *
     * Runs after `pillPeerRects` is filled, because the answer depends on where
     * the neighbours are.
     */
    private measurePillPeerScales;
    /**
     * What the pill path would do to this element's font, as a factor of the
     * authored size, or undefined when the element is not a chip.
     */
    private pillFontScaleFor;
    private semanticPeerKey;
    /**
     * Chromium lays repeated cards as a peer system; PowerPoint must not shrink
     * each card independently. Compute the strictest bounded factor once and
     * reuse it across the semantic group.
     */
    private measurePeerTypographyScales;
    private recordTextBand;
    /** Top of the first accent bar below this text (overlapping X). */
    private accentCeilingBelow;
    /** Horizontal walls from opaque panels overlapping this text band in Y. */
    private columnWallsBeside;
    /** Push thin accent bars below overlapping title text bottoms. */
    private nudgeAccentBelowTitles;
    /** All measured HTML text rects on the current slide (drift headroom walls). */
    private textNeighborRects;
    /**
     * Rightmost edge a frozen text box may grow to without touching another
     * frozen text box or opaque panel that overlaps it vertically.
     */
    private layoutDriftRightLimit;
    /** Top of the first page-chrome band below this box (overlapping X). */
    private chromeCeilingBelow;
    /** Clamp a fitted box so it does not cover page chrome. */
    private clampBoxAwayFromChrome;
    /**
     * O27: native charts paint the full host AABB. When body copy overlaps the
     * chart host (absolute bottom inset), push the chart below the text band.
     */
    private clampChartAwayFromTextBands;
    private pillCollisionBounds;
    /** Resolve script faces with Bold/Italic suffix only when registry has exact match */
    private resolveScriptFontFaces;
    private getContainerText;
    private splitTextRunByScript;
    private buildScriptSplitTextPieces;
    /**
     * Convert element to pptxgenjs object properties
     * Returns an array of converted elements (main element + any border decorations)
     */
    convertElement(element: ElementInfo, slideStartY?: number, slideIndex?: number, elementIndex?: number): any[];
    /**
     * Get base properties (position, size, and rotation from CSS transform)
     */
    private getBaseProperties;
    /**
     * Placeholder text box for OMML equation injection (Phase 2 XML).
     */
    private convertMathElement;
    /**
     * Get line options for the "common" sides when one side is special
     * Returns style from the majority (top/right/bottom when left is special)
     * Returns undefined when only one side has border (no common)
     */
    private getCommonLineOptions;
    /**
     * Determine border type: uniform (4 sides equal), single (some sides), none
     */
    private getBorderType;
    /**
     * Convert icon element (Font Awesome icons)
     */
    private convertIconElement;
    /**
     * Convert text element
     */
    private convertTextElement;
    private buildPlaceholderImage;
    /**
     * Convert chart element (data-chart-payload on data-pptx="chart" hosts).
     */
    private convertChartElement;
    /**
     * Convert image element
     */
    private convertImageElement;
    /**
     * Convert video/audio to a slide image (placeholder when media unavailable).
     */
    private convertMediaPlaceholderElement;
    /**
     * Convert canvas/SVG element (dataUrl is PNG from canvas or from SVG export) -> slide image
     */
    private convertCanvasElement;
    /**
     * Convert table element
     */
    private convertTableElement;
    /**
     * Box used for single-side border strips. Prefer the emitted fill/text geometry so
     * accent bars stay glued to callout plates after any fit/grow.
     */
    private resolveBorderDecorationBase;
    /**
     * Get which sides are "special" (differ from majority) for single-side border
     * Returns array of { side: 0|1|2|3, widthPx, colorResult, borderStyle } for sides needing decorations
     */
    private getSpecialBorderSides;
    /**
     * Create border decoration elements for special single-side borders only
     * Main element gets common border; special sides get separate shapes (custGeom when rounded)
     */
    private createBorderDecorations;
    /**
     * Convert shape element (div with background/border)
     */
    private convertShapeElement;
}
