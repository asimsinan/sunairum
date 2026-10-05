/**
 * PPTX Generator Module
 * Creates PowerPoint presentations using pptxgenjs
 */
import { ElementInfo, UsedFontDescriptor } from './types';
import { PlatformFontContext } from './utils/platformFontMap';
import { ReportCollector } from './conversion-report';
import type { SlideTransitionPlan } from './slide-transition/resolve';
export interface PPTXGeneratorOptions {
    fontResolver?: (d: UsedFontDescriptor) => string;
    platformFontContext?: PlatformFontContext;
    /** When true, slide N starts at N × viewport height (long HTML split). */
    splitByHeight?: boolean;
    /** CSS selector grouping multiple slides in one HTML file. */
    slideSelector?: string;
    /** Coordinates already normalized per slide (multi-slide isolation path). */
    slideCoordsNormalized?: boolean;
    /**
     * Slide-to-slide transition plan (disabled / fixed / per-slide random).
     */
    slideTransitionPlan?: SlideTransitionPlan;
    /**
     * When true, nudge opaque covers clear of title/subtitle text.
     * Default false — preserves HTML geometry (pixel fidelity).
     */
    repairTextOcclusions?: boolean;
}
export declare class PPTXGenerator {
    private pptx;
    private converter;
    private splitByHeight;
    private slideSelector?;
    private slideCoordsNormalized;
    private registry;
    /** Per-slide animation timing specs, registered as enhancements in generate(). */
    private animationSpecs;
    /** Slide-to-slide transition plan (disabled when mode === 'disabled'). */
    private slideTransitionPlan;
    /** Opt-in layout mutation to clear text under opaque covers. */
    private repairTextOcclusionsEnabled;
    /** Per-element report collector (DH-P0-002). */
    readonly report: ReportCollector;
    /** HTML → PPTX shape attribution for closed-loop visual verify. */
    private shapeMap;
    constructor(options?: PPTXGeneratorOptions);
    /** L1 layout-faithful notes collected during text emission. */
    getLayoutFaithfulNotes(): Array<{
        elementId?: string;
        reason: string;
        message: string;
    }>;
    /** Shape map collected during generate() for visual verify attribution. */
    getShapeMap(): import('./types').ShapeMapEntry[];
    /**
     * Generate PPTX from grouped slide elements
     */
    generate(slidesMap: Map<number, ElementInfo[]>): Promise<Buffer>;
    /**
     * Generate PPTX with XML post-processing for style enhancements
     */
    private generateWithEnhancements;
    /**
     * Convert stream to ArrayBuffer
     */
    private streamToArrayBuffer;
    /**
     * Embed fonts using pptx-embed-fonts library
     */
    /**
     * Create a single slide from elements
     */
    private createSlide;
    private recordShapeMapEntry;
    /**
     * Aggregate one element's animations into the per-slide timing spec.
     * A DOM element split into several PPTX shapes (shape background + text
     * box) carries its animationRaw on each ElementInfo; entries are merged by
     * objectName and identical effects deduped so the animation plays once.
     */
    private registerAnimationEntry;
    /**
     * For each slide, find animation groups (sets of elements sharing the same
     * `animationGroupId`) whose root carries mapped entrance animations, and
     * register one `animationGroup` enhancement per group. The post-processor
     * wraps every member shape (all stamped with the group objectName) into a
     * single <p:grpSp> so the entrance animation targets the group as a whole.
     *
     * Groups with only one member (root with no converted descendants) are
     * skipped — there is nothing to wrap, and the root shape already carries
     * the animation target name.
     */
    private registerAnimationGroupEnhancements;
    /**
     * Push a per-element record into the report collector (DH-P0-002).
     */
    private recordElement;
    private resolveMappingMode;
    /**
     * Add converted element to slide
     * @param shapeIndex - Index among p:sp only (for enhancements that target shapes); required for softEdge
     */
    private addElementToSlide;
    /**
     * Stable slide id for the report (DH-P0-002). Falls back to slide-NN.
     */
    private resolveSlideId;
    /**
     * Top Y origin for converting element coordinates on this slide.
     */
    private resolveSlideStartY;
    /**
     * Get slide count
     */
    getSlideCount(): number;
}
