"use strict";
/**
 * Resilient Playwright navigation helpers.
 * Avoid hard-failing on hung CDN / image requests (networkidle never settles).
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.gotoAndSettle = gotoAndSettle;
/**
 * Navigate to a document and settle fonts/network without blocking forever
 * on unreachable subresources.
 */
async function gotoAndSettle(page, documentUrl, options) {
    const navigationTimeoutMs = options?.navigationTimeoutMs ?? 30000;
    const networkIdleTimeoutMs = options?.networkIdleTimeoutMs ?? 10000;
    const fontTimeoutMs = options?.fontTimeoutMs ?? 3000;
    const settleMs = options?.settleMs ?? 2000;
    // domcontentloaded: do not wait for images/stylesheets (load/networkidle can hang).
    await page.goto(documentUrl, {
        waitUntil: 'domcontentloaded',
        timeout: navigationTimeoutMs,
    });
    // Best-effort: let healthy CDN assets finish; ignore hung connections.
    await page
        .waitForLoadState('networkidle', { timeout: networkIdleTimeoutMs })
        .catch(() => { });
    await Promise.race([
        page.evaluate(() => document.fonts.ready),
        page.waitForTimeout(fontTimeoutMs),
    ]);
    if (settleMs > 0) {
        await page.waitForTimeout(settleMs);
    }
}
