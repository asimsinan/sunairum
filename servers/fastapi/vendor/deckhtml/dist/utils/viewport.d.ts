/**
 * Viewport defaults and HTML/SVG size auto-detection.
 *
 * Explicit ConversionOptions.viewportWidth/Height (or CLI --width) always win.
 * When omitted, we read declared slide size from the source so Playwright
 * loads at the design width (critical for fixed-px decks such as 1920×1080).
 */
export declare const DEFAULT_VIEWPORT_WIDTH = 1280;
export declare const DEFAULT_VIEWPORT_HEIGHT = 720;
export type ViewportSize = {
    width: number;
    height: number;
};
/** Parse the first `WxH` / `W×H` token in a string (e.g. meta deck-size). */
export declare function parseWxH(text: string): ViewportSize | null;
/**
 * Read `<meta name="deck-size" content="… 1920x1080">` (attribute order flexible).
 */
export declare function parseDeckSizeMeta(html: string): ViewportSize | null;
/**
 * Read `<meta name="viewport" content="width=1920, …">`.
 * Ignores `width=device-width`. Height defaults to 16:9 when omitted.
 */
export declare function parseViewportMeta(html: string): ViewportSize | null;
/**
 * Read CSS custom properties for slide size.
 * Recognizes `--deck|page|slide|canvas-width` paired with matching `-height` (px).
 */
export declare function parseDeckCssVariables(cssOrHtml: string): ViewportSize | null;
/**
 * Extract text content of `<style>` blocks from HTML.
 * Used so CSS rule scanners never run against markup / data-URI blobs
 * (those can be multi-MB lines without `{`/`}`, which makes `/[^{}@]+\{/` O(n²)).
 */
export declare function extractInlineStyleBlocks(html: string): string;
/**
 * Read fixed `width`/`height` px on common slide host / root selectors.
 * Scans only CSS (inline `<style>` blocks or pure stylesheet text), never raw HTML.
 */
export declare function parseFixedSlideHostSize(cssOrHtml: string): ViewportSize | null;
/**
 * Read `"stage": { "width": 1920, "height": 1080 }` from embedded JSON (player manifests).
 */
export declare function parseStageJson(html: string): ViewportSize | null;
/** Collect relative/local stylesheet hrefs from HTML link tags. */
export declare function collectLocalStylesheetHrefs(html: string): string[];
/**
 * Detect declared slide size from HTML source.
 * Order: deck-size meta → CSS size vars → viewport meta → stage JSON → fixed host px.
 * When `baseDir` is set, also reads local linked stylesheets for CSS signals.
 * CSS detectors only see `<style>` contents + linked stylesheets (not HTML body / data URIs).
 */
export declare function detectViewportFromHtml(html: string, options?: {
    baseDir?: string;
}): ViewportSize | null;
/** Read SVG viewBox / width+height for viewport auto-sizing. */
export declare function detectViewportFromSvg(svg: string): ViewportSize | null;
/**
 * Detect viewport from a file on disk. HTML uses deck-size / CSS vars / viewport
 * meta / stage / linked stylesheets; SVG uses viewBox or width/height attributes.
 */
export declare function detectViewportFromFile(inputPath: string): ViewportSize | null;
/**
 * Resolve Playwright viewport for one input.
 * Explicit options win; otherwise auto-detect from source; else 1280×720.
 */
export declare function resolveConversionViewport(inputPath: string, options?: {
    viewportWidth?: number;
    viewportHeight?: number;
}): ViewportSize;
