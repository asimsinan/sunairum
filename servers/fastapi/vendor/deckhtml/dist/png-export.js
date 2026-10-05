"use strict";
/**
 * HTML → PNG export via Playwright viewport screenshots.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.convertHtmlToPng = convertHtmlToPng;
const loader_1 = require("./loader");
const inspector_1 = require("./inspector");
const coordinate_1 = require("./utils/coordinate");
const async_pool_1 = require("./utils/async-pool");
const quiet_1 = require("./utils/quiet");
const conversion_report_1 = require("./conversion-report");
const viewport_1 = require("./utils/viewport");
function resolveInputPaths(options) {
    if (options.inputs?.length)
        return options.inputs;
    if (options.input)
        return [options.input];
    throw new Error('At least one input file is required (use input or inputs).');
}
async function captureViewportPng(page, viewport, slideSelector) {
    await page.emulateMedia({ media: 'screen' });
    const screenshotOptions = {
        type: 'png',
        animations: 'disabled',
    };
    if (slideSelector) {
        return page.locator(slideSelector).first().screenshot(screenshotOptions);
    }
    return page.screenshot({
        ...screenshotOptions,
        clip: { x: 0, y: 0, width: viewport.width, height: viewport.height },
    });
}
async function getDocumentScrollHeight(page) {
    return page.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight ?? 0));
}
function needsPerSlideCapture(discovery, splitByHeight, scrollHeight, viewportHeight) {
    if (discovery.count >= 2)
        return true;
    if (discovery.activeDeck)
        return true;
    if (splitByHeight && discovery.count < 2) {
        return scrollHeight > viewportHeight + 1;
    }
    return false;
}
async function exportSingleInputToPng(loader, inputPath, options) {
    const viewport = (0, viewport_1.resolveConversionViewport)(inputPath, options);
    (0, coordinate_1.setViewportPixels)(viewport.width, viewport.height);
    const page = await loader.loadHTML(inputPath, viewport, {
        allowLocalResources: options.allowLocalResources ?? true,
    });
    try {
        const inspector = new inspector_1.ElementInspector(page);
        const autoDetect = options.autoDetectSlides !== false;
        const discovery = await inspector.discoverSlideContainers(options.slideSelector, autoDetect);
        const splitByHeight = Boolean(options.splitByHeight);
        const scrollHeight = await getDocumentScrollHeight(page);
        if (needsPerSlideCapture(discovery, splitByHeight, scrollHeight, viewport.height)) {
            const images = [];
            if (discovery.count >= 2) {
                if (!options.quiet) {
                    const ruleHint = discovery.rule ?? discovery.selector;
                    console.error(`🖼  PNG export: ${discovery.count} slides (isolated capture, rule: ${ruleHint})`);
                }
                for (let i = 0; i < discovery.count; i++) {
                    await inspector.prepareSlideForRasterExport(i, discovery);
                    try {
                        const slideSelector = inspector.slideIndexSelector(i);
                        const captureSelector = await inspector.applyRasterExportFrame(viewport, slideSelector);
                        images.push(await captureViewportPng(page, viewport, captureSelector ?? slideSelector));
                    }
                    finally {
                        await inspector.restoreRasterExportFrame();
                        await inspector.restoreSlideForRasterExport();
                    }
                }
                return images;
            }
            const pageCount = Math.max(1, Math.ceil(scrollHeight / viewport.height));
            if (!options.quiet) {
                console.error(`🖼  PNG export: ${pageCount} pages (split by height)`);
            }
            for (let i = 0; i < pageCount; i++) {
                await inspector.applyViewportClipForRaster(i * viewport.height, viewport);
                try {
                    const captureSelector = await inspector.applyRasterExportFrame(viewport);
                    images.push(await captureViewportPng(page, viewport, captureSelector));
                }
                finally {
                    await inspector.restoreViewportClipForRaster();
                }
            }
            return images;
        }
        if (!options.quiet) {
            console.error('🖼  PNG export: single page');
        }
        const captureSelector = await inspector.applyRasterExportFrame(viewport);
        return [await captureViewportPng(page, viewport, captureSelector)];
    }
    finally {
        await page.evaluate((ids) => {
            for (const id of ids) {
                document.getElementById(id)?.remove();
            }
        }, ['deckhtml-raster-clip-style', 'deckhtml-raster-frame-style']);
        await loader.close().catch(() => { });
    }
}
/**
 * Convert HTML input(s) to one or more PNG buffers using Playwright screenshots.
 * Multi-slide decks and multi-file inputs produce one image per page, in order.
 * Multiple HTML files are processed concurrently (CPU cores − 2), matching PPTX.
 */
async function convertHtmlToPng(options) {
    return (0, quiet_1.runQuietly)(Boolean(options.quiet), async () => {
        const inputPaths = resolveInputPaths(options);
        const concurrency = (0, async_pool_1.resolveSlideInspectConcurrency)();
        const parallelInputs = inputPaths.length > 1 && concurrency > 1;
        let images;
        if (parallelInputs) {
            const fileConcurrency = Math.min(concurrency, inputPaths.length);
            if (!options.quiet) {
                console.error(`⚡ Parallel PNG: ${fileConcurrency} HTML files at a time (CPU cores − 2)`);
            }
            const indexed = inputPaths.map((path, index) => ({ path, index }));
            const completed = await (0, async_pool_1.runAsyncPool)(indexed, fileConcurrency, async ({ path, index }) => {
                if (!options.quiet) {
                    console.error(`\n📄 Processing ${index + 1}/${inputPaths.length}: ${path}`);
                }
                const fileLoader = new loader_1.HTMLLoader();
                await fileLoader.init({
                    executablePath: options.browser?.executablePath,
                    userDataDir: options.browser?.userDataDir,
                    headless: options.browser?.headless,
                    args: options.browser?.args,
                }, {
                    browser: options.browser?.browser,
                    browserContext: options.browser?.browserContext,
                });
                try {
                    const pages = await exportSingleInputToPng(fileLoader, path, options);
                    return { index, pages };
                }
                finally {
                    await fileLoader.close().catch(() => { });
                }
            });
            completed.sort((a, b) => a.index - b.index);
            images = completed.flatMap(({ pages }) => pages);
        }
        else {
            const loader = new loader_1.HTMLLoader();
            await loader.init({
                executablePath: options.browser?.executablePath,
                userDataDir: options.browser?.userDataDir,
                headless: options.browser?.headless,
                args: options.browser?.args,
            }, {
                browser: options.browser?.browser,
                browserContext: options.browser?.browserContext,
            });
            try {
                images = [];
                for (let i = 0; i < inputPaths.length; i++) {
                    const inputPath = inputPaths[i];
                    if (inputPaths.length > 1 && !options.quiet) {
                        console.error(`\n📄 Processing ${i + 1}/${inputPaths.length}: ${inputPath}`);
                    }
                    const pages = await exportSingleInputToPng(loader, inputPath, options);
                    images.push(...pages);
                }
            }
            finally {
                await loader.close().catch(() => { });
            }
        }
        return {
            images,
            slideCount: images.length,
            stats: conversion_report_1.EMPTY_CONVERSION_STATS,
        };
    });
}
