/**
 * HTML Loader Module
 * Uses Playwright to load and render HTML files.
 *
 * Browser launch is fully caller-controlled (DH-P0-006):
 *   - `executablePath` resolution order:
 *       1. explicit `executablePath` option
 *       2. `DECKHTML_CHROMIUM_EXECUTABLE_PATH` env
 *       3. Playwright's bundled Chromium (from `npx playwright install chromium`)
 *       4. system Chrome / Edge discovered via `chrome-launcher`
 *   - `userDataDir` (option or DECKHTML_BROWSER_DATA_DIR env) opts into a persistent
 *     profile. By default a fresh temp directory is created per process and removed
 *     on exit — the loader never writes to ~/browser-data unless asked to.
 *   - `headless` defaults to true.
 *   - Callers may inject their own `browser` (Browser) or `browserContext`
 *     (BrowserContext); the loader will not close a caller-owned browser.
 */
import { Browser, Page, BrowserContext } from 'playwright-core';
/** Caller-controlled browser launch options. */
export interface BrowserLaunchOptions {
    /** Explicit Chromium executable path. Resolution order: option → DECKHTML_CHROMIUM_EXECUTABLE_PATH → Playwright bundle → system Chrome via chrome-launcher. */
    executablePath?: string;
    /** Persistent profile directory. Defaults to DECKHTML_BROWSER_DATA_DIR env, then a per-process temp dir. */
    userDataDir?: string;
    /** Headless mode (default true). */
    headless?: boolean;
    /** Additional Chromium args. */
    args?: string[];
}
/** A caller-supplied browser instance. The loader will reuse it without owning it. */
export interface BrowserInjectionOptions {
    /** Inject an existing Playwright Browser; loader will not launch or close it. */
    browser?: Browser;
    /** Inject an existing Playwright BrowserContext; loader will not launch or close it. */
    browserContext?: BrowserContext;
}
/**
 * Explicitly close the process-owned browser and remove its temp profile.
 * Call this in test teardown or when a long-running host is done with deckhtml.
 */
export declare function closeOwnedBrowser(): Promise<void>;
/**
 * Structured diagnostic thrown when the browser cannot be launched.
 */
export declare class BrowserUnavailableError extends Error {
    readonly recovery?: string | undefined;
    readonly ruleId = "DECKHTML_BROWSER_UNAVAILABLE";
    constructor(message: string, recovery?: string | undefined);
}
export declare class HTMLLoader {
    private browser;
    private page;
    /** True when the loader is using a caller-injected context (do not close). */
    private borrowedContext;
    /**
     * Initialize browser instance.
     */
    init(launchOptions?: BrowserLaunchOptions, injection?: BrowserInjectionOptions): Promise<void>;
    /**
     * Load HTML file and prepare for inspection
     */
    loadHTML(inputPath: string, viewport?: {
        width: number;
        height: number;
    }, options?: {
        allowLocalResources?: boolean;
        resourcePolicy?: import('./utils/resource-policy').ResourcePolicy;
        diagnostics?: import('./utils/resource-policy').ResourceDiagnostic[];
    }): Promise<Page>;
    /**
     * Open a new Playwright page, load HTML, and return it (caller closes the page).
     */
    loadHTMLInNewPage(inputPath: string, viewport?: {
        width: number;
        height: number;
    }, options?: {
        allowLocalResources?: boolean;
        resourcePolicy?: import('./utils/resource-policy').ResourcePolicy;
        diagnostics?: import('./utils/resource-policy').ResourceDiagnostic[];
    }): Promise<Page>;
    private prepareLoadedPage;
    /**
     * Get the current page instance
     */
    getPage(): Page;
    /**
     * Close this loader's page. Does not close a caller-injected browser or the
     * process-owned shared context (other loaders / parallel inspect may still
     * need it). The owned context is closed on process exit or via closeOwnedBrowser().
     */
    close(): Promise<void>;
}
