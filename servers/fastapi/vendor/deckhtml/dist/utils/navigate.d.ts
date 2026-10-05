/**
 * Resilient Playwright navigation helpers.
 * Avoid hard-failing on hung CDN / image requests (networkidle never settles).
 */
import type { Page } from 'playwright-core';
export interface GotoAndSettleOptions {
    /** Timeout for document navigation (domcontentloaded). Default 30s. */
    navigationTimeoutMs?: number;
    /** Best-effort wait for idle network; never throws. Default 10s. */
    networkIdleTimeoutMs?: number;
    /** Cap for document.fonts.ready. Default 3s. */
    fontTimeoutMs?: number;
    /** Post-load settle for CSS animations. Default 2s. */
    settleMs?: number;
}
/**
 * Navigate to a document and settle fonts/network without blocking forever
 * on unreachable subresources.
 */
export declare function gotoAndSettle(page: Page, documentUrl: string, options?: GotoAndSettleOptions): Promise<void>;
