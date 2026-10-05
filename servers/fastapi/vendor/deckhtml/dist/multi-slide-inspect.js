"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.inspectSlidesParallel = inspectSlidesParallel;
const inspector_1 = require("./inspector");
const async_pool_1 = require("./utils/async-pool");
/**
 * Inspect each slide in its own Playwright page, with a bounded page pool.
 */
async function inspectSlidesParallel(loader, params) {
    const slidesMap = new Map();
    const indices = Array.from({ length: params.discovery.count }, (_, i) => i);
    const loadOptions = {
        allowLocalResources: params.allowLocalResources,
        resourcePolicy: params.resourcePolicy,
        diagnostics: params.diagnostics,
    };
    await (0, async_pool_1.runAsyncPool)(indices, params.concurrency, async (slideIndex) => {
        const page = await loader.loadHTMLInNewPage(params.inputPath, params.viewport, loadOptions);
        try {
            const inspector = new inspector_1.ElementInspector(page);
            await inspector.discoverSlideContainers(params.slideSelector, params.autoDetectSlides);
            const elements = await inspector.inspectOneSlideIsolated(slideIndex, params.discovery, params.inspectOptions);
            slidesMap.set(slideIndex, elements);
        }
        finally {
            await page.close().catch(() => { });
        }
    });
    return slidesMap;
}
