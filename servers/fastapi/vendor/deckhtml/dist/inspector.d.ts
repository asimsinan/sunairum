/**
 * Element Inspector Module
 * Traverses DOM tree and extracts element information
 */
import { Page } from 'playwright-core';
import { ElementInfo } from './types';
/** Declarative rule for auto-detecting multi-page slide hosts. */
export interface SlideProbeRule {
    /** Human-readable label for logging. */
    label: string;
    /** CSS selector for candidate slide hosts. */
    selector: string;
    /**
     * When set, only candidates without an ancestor matching this selector are kept
     * (e.g. top-level `section` only).
     */
    topLevelAncestorSelector?: string;
    /**
     * When true, slide hosts may include size-qualified direct siblings of probe
     * matches (e.g. header.hero next to section). Named slide-class rules default false.
     */
    expandSiblingHosts?: boolean;
    /**
     * Optional regular expression (matched against individual CSS class tokens) that
     * a candidate must satisfy. This keeps broad fallback probes from treating
     * incidental names such as `.slideshow` or `.slider` as slide hosts.
     */
    classTokenPattern?: string;
    /** Require visible textual or media-like content before accepting a fallback host. */
    requireMeaningfulContent?: boolean;
}
/** Metadata for slide decks gated by a mutually-exclusive CSS class (e.g. `.active`). */
export interface ActiveGatedDeckInfo {
    activeClass: string;
}
export interface SlideContainerDiscovery {
    selector: string;
    count: number;
    /** Matched probe rule label, or `explicit` / `none`. */
    rule?: string;
    /** Present when slides are stacked and visibility is toggled via a CSS class. */
    activeDeck?: ActiveGatedDeckInfo;
}
export interface InspectElementsOptions {
    inputIsSvg?: boolean;
    /** CSS selector matching runtime/navigation elements to exclude (DH-P0-005). */
    excludeSelector?: string;
    /** Attribute name carrying a stable per-slide id (DH-P0-005). */
    slideIdAttribute?: string;
    /** Attribute name carrying a stable element identity (default: data-element-id) (DH-P0-001). */
    identityAttribute?: string;
    /** Collector for identity diagnostics (duplicates) (DH-P0-001). */
    identityDiagnostics?: import('./utils/diagnostics').Diagnostic[];
    /** Mutable accumulator for excluded element count (DH-P0-002). */
    excludedCount?: {
        value: number;
    };
    /**
     * How to handle `<iframe>` elements (default: `'inspect'`).
     * Inspect opens the iframe document in a new page sized to the iframe box.
     */
    iframes?: 'inspect' | 'screenshot' | 'skip';
    /** Timeout for loading iframe documents (default: 8000ms). */
    iframeLoadTimeoutMs?: number;
    /** Current iframe nesting depth (internal; default 0). */
    iframeDepth?: number;
    /** Max iframe nesting depth (default 3). */
    iframeMaxDepth?: number;
    /** Allow local file:// subresources when loading iframe documents. */
    allowLocalResources?: boolean;
    /** Explicit resource policy for iframe child pages. */
    resourcePolicy?: import('./utils/resource-policy').ResourcePolicy;
    /** Collector for iframe-related diagnostics. */
    iframeDiagnostics?: import('./utils/diagnostics').Diagnostic[];
}
/**
 * Ordered probe rules for multi-page HTML. First rule with enough qualified
 * candidates wins; all matches share the same height check, isolation, and inspect pipeline.
 */
export declare const SLIDE_PROBE_RULES: SlideProbeRule[];
export declare class ElementInspector {
    private page;
    constructor(page: Page);
    /**
     * Measure the effective content width of the current page (matches configured viewport width).
     */
    getPageContentWidth(): Promise<number>;
    /**
     * Extract font URLs from @font-face rules in the page
     */
    extractFontUrls(): Promise<Map<string, Array<{
        url: string;
        weight?: number;
    }>>>;
    /**
     * Parse @font-face rules from CSS content
     */
    private parseFontFaceRules;
    /**
     * Discover slide container elements in the page.
     * Tags each match with data-deckhtml-slide-index for stable isolation.
     */
    discoverSlideContainers(selector?: string, autoDetect?: boolean): Promise<SlideContainerDiscovery>;
    /** Attach active-gated deck metadata when tagged slide hosts match deck heuristics. */
    private enrichDiscoveryWithActiveDeck;
    private emptySlideDiscovery;
    /**
     * Try each {@link SLIDE_PROBE_RULES} entry in order; tag qualified hosts and
     * return a selector that matches only those tagged nodes.
     */
    private discoverByProbeRules;
    /**
     * Qualify slide hosts from probe matches. Named slide-class rules use probe hits
     * only; generic section rule may expand to size-qualified siblings (e.g. header.hero).
     */
    private finalizeSlidesFromProbeParents;
    private cleanupSlideCandidates;
    /**
     * Detect slide decks where exactly one stacked sibling is visible and a CSS class
     * (e.g. `.active`) gates visibility across co-located hosts.
     */
    private detectActiveGatedDeck;
    private waitForLayoutSettle;
    /** Wait for slide-local animations after isolation before element inspect. */
    private waitForSlideAnimationSettle;
    /**
     * Multi-slide preprocessing: hide every node outside the slide container
     * (keep the container, its descendants, and ancestor chain visible).
     */
    private isolateOutsideSlideContainer;
    /**
     * Capture CSS animation declarations before styles are frozen for inspection:
     * - `@keyframes` first/last frames (computed animation-* props)
     * - class-gated entrance `transition`s (opacity/transform) via enter-class replay
     *
     * Elements get a data-dh-anim-css marker; raw data lives on
     * window.__deckhtmlCssAnimations and is folded into animationRaw.cssRaw by
     * readAnimationRaw during inspect.
     */
    private captureCssAnimations;
    /** Scroll-reveal hooks leave `.reveal` at opacity:0 until scrolled; fix before inspect. */
    private prepareSlideContainerForInspect;
    private clearPptxMappedAttributes;
    private restoreSlideIsolation;
    private cleanupSlideContainerTags;
    private getSlideContainerOrigin;
    private normalizeElementCoords;
    /**
     * Body page-bg is emitted at the viewport origin (0,0). After subtracting the
     * slide container origin it drifts off-slide and PowerPoint prompts for repair.
     */
    private anchorFullSlidePageBg;
    /**
     * Inspect one slide after isolation (multi-slide path).
     */
    inspectOneSlideIsolated(slideIndex: number, discovery: SlideContainerDiscovery, options?: InspectElementsOptions): Promise<ElementInfo[]>;
    /**
     * Inspect each slide container in isolation and return per-slide element maps.
     */
    inspectSlidesIsolated(discovery: SlideContainerDiscovery, options?: InspectElementsOptions): Promise<Map<number, ElementInfo[]>>;
    /**
     * Isolate one slide for raster capture (PNG multi-slide / active-gated decks).
     */
    prepareSlideForRasterExport(slideIndex: number, discovery: SlideContainerDiscovery): Promise<void>;
    /** Restore DOM after {@link prepareSlideForRasterExport}. */
    restoreSlideForRasterExport(): Promise<void>;
    /**
     * Clip the document to one viewport-height slice for splitByHeight raster export.
     */
    applyViewportClipForRaster(offsetY: number, viewport: {
        width: number;
        height: number;
    }): Promise<void>;
    /** Restore DOM after {@link applyViewportClipForRaster}. */
    restoreViewportClipForRaster(): Promise<void>;
    /**
     * Pin the visible page to the export viewport so screenshots match slide layout.
     * Returns the CSS selector of the slide host used for capture.
     */
    applyRasterExportFrame(viewport: {
        width: number;
        height: number;
    }, slideSelector?: string): Promise<string | null>;
    slideIndexSelector(slideIndex: number): string;
    /** Restore DOM after {@link applyRasterExportFrame}. */
    restoreRasterExportFrame(): Promise<void>;
    /**
     * Inspect all visible elements in the page
     */
    inspectElements(slideSelector?: string, options?: InspectElementsOptions): Promise<ElementInfo[]>;
    /**
     * Replace iframe placeholders with inspected child elements, screenshots, or remove them.
     */
    private resolveIframes;
    /**
     * Open the iframe document in a new page sized to the iframe CSS box and inspect it.
     */
    private inspectIframeInNewPage;
    /**
     * Resolve what to load into the child page for an iframe placeholder.
     */
    private resolveIframeLoadTarget;
    /**
     * Translate + scale child-page element coordinates into the parent slide space.
     */
    private offsetIframeElements;
    /**
     * Emit the iframe element's own border/fill as a shape so the frame chrome
     * is preserved after the placeholder is replaced by child content.
     *
     * When `bodyBg` is provided (extracted from the child page's rasterized
     * `<body>` background), the chrome shape adopts it as its fill so the visible
     * background respects the iframe's border-radius. Without this, the body
     * background would be emitted as a separate sharp rectangle image that covers
     * the chrome shape's rounded corners.
     */
    private buildIframeChromeShape;
    /**
     * Rasterize the iframe element as it appears on the parent page.
     */
    private screenshotIframePlaceholder;
    /**
     * Detect slide boundaries based on selector or height
     */
    detectSlides(elements: ElementInfo[], slideSelector?: string, splitByHeight?: boolean): Promise<Map<number, ElementInfo[]>>;
    /**
     * Simple selector matching helper
     */
    private matchesSelector;
}
