"use strict";
/**
 * API Module
 * Main conversion function for programmatic use
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.inspectHtmlFonts = inspectHtmlFonts;
exports.convertHtmlToPptx = convertHtmlToPptx;
const fs_1 = require("fs");
const path_1 = require("path");
const loader_1 = require("./loader");
const inspector_1 = require("./inspector");
const multi_slide_inspect_1 = require("./multi-slide-inspect");
const generator_1 = require("./generator");
const coordinate_1 = require("./utils/coordinate");
const async_pool_1 = require("./utils/async-pool");
const chineseFonts_1 = require("./utils/chineseFonts");
const style_1 = require("./utils/style");
const textScript_1 = require("./utils/textScript");
const platformFontMap_1 = require("./utils/platformFontMap");
const quiet_1 = require("./utils/quiet");
const deck_font_embedder_1 = require("./utils/deck-font-embedder");
const conversion_report_1 = require("./conversion-report");
const diagnostics_1 = require("./utils/diagnostics");
const ooxml_verify_1 = require("./utils/ooxml-verify");
const ooxml_normalize_1 = require("./utils/ooxml-normalize");
const apply_1 = require("./animation/apply");
const viewport_1 = require("./utils/viewport");
const resolve_1 = require("./slide-transition/resolve");
const layout_faithful_1 = require("./utils/layout-faithful");
const font_closure_1 = require("./utils/font-closure");
const ENGINE_VERSION = (() => {
    try {
        const pkg = JSON.parse((0, fs_1.readFileSync)((0, path_1.join)(__dirname, '..', 'package.json'), 'utf8'));
        return pkg.version ?? '0.0.0';
    }
    catch {
        return '0.0.0';
    }
})();
function resolveInputPaths(options) {
    if (options.inputs?.length)
        return options.inputs;
    if (options.input)
        return [options.input];
    throw new Error('At least one input file is required (use input or inputs).');
}
function collectFontsFromElements(elements, platformFontContext, usedFontsMap) {
    const documentUsesChineseFont = !platformFontContext && elements.some((el) => (0, chineseFonts_1.isChineseFont)(el.styles?.fontFamily ?? '') ||
        el.richText?.some((run) => (0, chineseFonts_1.isChineseFont)(run.styles?.fontFamily ?? '')));
    const registerFont = (fontFamily, styles, boldOverride) => {
        if (!fontFamily)
            return;
        const bold = boldOverride ?? (0, style_1.isBold)(styles.fontWeight);
        const italic = (0, style_1.isItalic)(styles.fontStyle);
        const key = `${fontFamily}|${bold}|${italic}`;
        if (usedFontsMap.has(key))
            return;
        usedFontsMap.set(key, { fontFamily, bold, italic });
    };
    const collectTextScripts = (text, containerText) => {
        const hints = (0, textScript_1.detectContainerScriptHints)(containerText || text);
        return (0, textScript_1.splitTextByScript)(text, hints).map((seg) => seg.script);
    };
    const getElementText = (el) => {
        if (el.richText?.length)
            return el.richText.map((run) => run.text).join('');
        return el.content ?? '';
    };
    const addFont = (styles, texts, containerText) => {
        if (!styles?.fontFamily)
            return;
        const faFreeFace = (0, style_1.normalizeFontAwesomeFreeFamily)(styles.fontFamily, styles.fontWeight?.toString());
        if (faFreeFace) {
            registerFont(faFreeFace, styles, false);
            return;
        }
        const faFace = (0, style_1.normalizeFontAwesomeFamily)(styles.fontFamily, styles.fontWeight?.toString());
        if (faFace) {
            registerFont(faFace, styles, false);
            return;
        }
        const scripts = new Set(texts.flatMap((text) => collectTextScripts(text, containerText)));
        if (scripts.size === 0)
            scripts.add('latin');
        const stackHasChinese = (0, chineseFonts_1.isChineseFont)(styles.fontFamily);
        if (!platformFontContext && !stackHasChinese && documentUsesChineseFont)
            return;
        for (const textScript of scripts) {
            const faces = (0, style_1.parseScriptFontFaces)(styles.fontFamily, {
                platformFontContext,
                specifiedFontFamily: styles.fontFamilySpecified,
                textScript,
            });
            registerFont(faces.latin, styles);
            if (faces.ea !== faces.latin) {
                registerFont(faces.ea, styles);
            }
            if (faces.cs && faces.cs !== faces.latin && faces.cs !== faces.ea) {
                registerFont(faces.cs, styles);
            }
        }
    };
    elements.forEach((el) => {
        const containerText = getElementText(el);
        addFont(el.styles, [containerText], containerText);
        el.richText?.forEach((run) => addFont(run.styles, [run.text], containerText));
        el.tableData?.rows.forEach((row) => {
            row.cells.forEach((cell) => {
                addFont(cell.styles ?? el.styles, [cell.text], cell.text);
            });
        });
    });
}
async function processSingleInput(loader, inputPath, options, platformFontContext, usedFontsMap, runtime, diagnostics, identityDiagnostics) {
    const inputIsSvg = inputPath.toLowerCase().endsWith('.svg');
    const viewport = (0, viewport_1.resolveConversionViewport)(inputPath, options);
    (0, coordinate_1.setViewportPixels)(viewport.width, viewport.height);
    const page = await loader.loadHTML(inputPath, viewport, {
        allowLocalResources: options.allowLocalResources,
        resourcePolicy: options.resourcePolicy,
        diagnostics,
    });
    try {
        if (inputIsSvg) {
            const svgValidation = await page.evaluate(() => {
                const parserError = document.querySelector('parsererror');
                if (parserError) {
                    const text = parserError.textContent?.replace(/\s+/g, ' ').trim() ?? '';
                    return { ok: false, reason: text || 'SVG XML parse error' };
                }
                const svgRoot = document.documentElement instanceof SVGSVGElement
                    ? document.documentElement
                    : document.querySelector('svg');
                if (!svgRoot) {
                    return { ok: false, reason: 'No SVG root element found in document' };
                }
                return { ok: true };
            });
            if (!svgValidation.ok) {
                throw new Error(`Cannot convert invalid SVG: ${svgValidation.reason}\n` +
                    'Fix XML syntax errors in the SVG file and try again.');
            }
        }
        const inspector = new inspector_1.ElementInspector(page);
        const autoDetect = options.autoDetectSlides !== false;
        const discovered = await inspector.discoverSlideContainers(options.slideSelector, autoDetect);
        let slidesMap;
        let slideCoordsNormalized = false;
        const excludedCounter = { value: 0 };
        if (discovered.count >= 2) {
            if (options.splitByHeight) {
                console.warn('⚠️  splitByHeight is ignored when multiple slide containers are detected.');
            }
            const ruleHint = discovered.rule ?? discovered.selector;
            console.log(`📑 Multi-slide mode: ${discovered.count} pages (rule: ${ruleHint})`);
            if (discovered.activeDeck) {
                console.log(`🎴 Active-gated deck detected (class: .${discovered.activeDeck.activeClass}, ${discovered.count} slides)`);
            }
            const inspectOptions = {
                inputIsSvg,
                excludeSelector: options.excludeSelector,
                slideIdAttribute: options.slideIdAttribute,
                identityAttribute: options.identityAttribute,
                identityDiagnostics,
                excludedCount: excludedCounter,
                iframes: options.iframes,
                iframeLoadTimeoutMs: options.iframeLoadTimeoutMs,
                allowLocalResources: options.allowLocalResources,
                resourcePolicy: options.resourcePolicy,
                iframeDiagnostics: identityDiagnostics,
            };
            const slideConcurrency = runtime?.slideInspectConcurrency ?? (0, async_pool_1.resolveSlideInspectConcurrency)();
            if (slideConcurrency > 1 && discovered.count > 1) {
                console.log(`⚡ Parallel inspect: ${slideConcurrency} Playwright pages (CPU cores − 2)`);
                await loader.close().catch(() => { });
                slidesMap = await (0, multi_slide_inspect_1.inspectSlidesParallel)(loader, {
                    inputPath,
                    viewport,
                    allowLocalResources: options.allowLocalResources,
                    resourcePolicy: options.resourcePolicy,
                    diagnostics,
                    slideSelector: options.slideSelector,
                    autoDetectSlides: autoDetect,
                    discovery: discovered,
                    inspectOptions,
                    concurrency: slideConcurrency,
                });
            }
            else {
                slidesMap = await inspector.inspectSlidesIsolated(discovered, inspectOptions);
            }
            slideCoordsNormalized = true;
            for (const elements of slidesMap.values()) {
                collectFontsFromElements(elements, platformFontContext, usedFontsMap);
            }
        }
        else {
            const elements = await inspector.inspectElements(options.slideSelector, {
                inputIsSvg,
                excludeSelector: options.excludeSelector,
                slideIdAttribute: options.slideIdAttribute,
                identityAttribute: options.identityAttribute,
                identityDiagnostics,
                excludedCount: excludedCounter,
                iframes: options.iframes,
                iframeLoadTimeoutMs: options.iframeLoadTimeoutMs,
                allowLocalResources: options.allowLocalResources,
                resourcePolicy: options.resourcePolicy,
                iframeDiagnostics: identityDiagnostics,
            });
            if (elements.length === 0) {
                elements.push({
                    type: 'text',
                    tag: 'p',
                    x: 0,
                    y: 0,
                    width: 0,
                    height: 0,
                    styles: {},
                    content: '',
                });
            }
            collectFontsFromElements(elements, platformFontContext, usedFontsMap);
            slidesMap = await inspector.detectSlides(elements, options.slideSelector, options.splitByHeight);
        }
        const animationDiagnostics = [];
        for (const [slideIndex, elements] of slidesMap) {
            animationDiagnostics.push(...(0, apply_1.applyAnimationsToElements)(elements, {
                animationsOption: options.animations,
                slideId: String(slideIndex + 1),
            }));
        }
        return {
            slidesMap,
            slideCoordsNormalized,
            excludedCount: excludedCounter.value,
            animationDiagnostics,
        };
    }
    finally {
        await loader.close().catch(() => { });
    }
}
function mergeSlidesMaps(target, source, slideOffset) {
    for (const [idx, elements] of source) {
        target.set(slideOffset + idx, elements);
    }
    return slideOffset + source.size;
}
function reportUsedFonts(usedFontsDeduped, fontStats) {
    if (usedFontsDeduped.length === 0)
        return;
    console.log(`\n📝 Fonts used in this presentation:`);
    usedFontsDeduped.forEach((name) => {
        console.log(`  - ${name}`);
    });
    const embed = fontStats?.embed;
    if (embed && (embed.matched.length > 0 || embed.unmatched.length > 0)) {
        console.log(`\n🔤 Cloud embed font library (${embed.indexMeta.familyCount} families):`);
        for (const item of embed.matched) {
            const note = item.used === item.matchedFamily
                ? 'matched'
                : `matched → ${item.matchedFamily}`;
            console.log(`  ✓ ${item.used} (${note})`);
        }
        for (const name of embed.unmatched) {
            console.log(`  ✗ ${name} (not in library)`);
        }
        if (embed.matched.length > 0) {
            console.log('\n💡 Cloud: use --mode cloud --embed-fonts to embed matched fonts into the PPTX so anyone opening the file sees the same typography.');
        }
    }
    console.log('\n💡 Make sure these fonts are installed on the system where the PPTX will be opened.\n');
}
/**
 * Web-safe / generic system font families that are always considered available
 * and therefore never trigger `strict.failOnMissingFonts` (DH-P0-003).
 */
const WEB_SAFE_FONTS = new Set([
    'arial',
    'helvetica',
    'helvetica neue',
    'times',
    'times new roman',
    'georgia',
    'courier',
    'courier new',
    'verdana',
    'tahoma',
    'trebuchet ms',
    'geneva',
    'palatino',
    'garamond',
    'bookman',
    'comic sans ms',
    'impact',
    'system-ui',
    'system',
    'sans-serif',
    'serif',
    'monospace',
    'cursive',
    'fantasy',
    'ui-sans-serif',
    'ui-serif',
    'ui-monospace',
    '-apple-system',
    'blinkmacsystemfont',
    'segoe ui',
    'roboto',
    'noto sans',
    'noto serif',
    'open sans',
    'lato',
    'montserrat',
    'source sans pro',
    'inter',
]);
function isWebSafeFont(family) {
    return WEB_SAFE_FONTS.has(family.trim().toLowerCase());
}
/**
 * Resolve the effective strict-mode configuration (DH-P0-003).
 *
 * When `strict` is present, every gate defaults to its strictest value unless
 * the caller explicitly relaxes it.
 */
function resolveStrictConfig(strict) {
    if (!strict)
        return null;
    return {
        requireElementIdentity: strict.requireElementIdentity ?? true,
        allowRaster: strict.allowRaster ?? false,
        allowUnsupported: strict.allowUnsupported ?? false,
        allowRemoteResources: strict.allowRemoteResources ?? false,
        failOnMissingFonts: strict.failOnMissingFonts ?? true,
        allowUnmappedAnimations: strict.allowUnmappedAnimations ?? false,
    };
}
/**
 * Enforce strict-mode gates after a conversion (DH-P0-003).
 *
 * Throws ConversionError (carrying the offending diagnostics) when any gate is
 * violated. Never returns a seemingly-successful PPTX for a strict run that
 * actually degraded.
 */
function enforceStrictMode(args) {
    const { strict, report, resourceDiagnostics, fontStats, identityDiagnostics, animationDiagnostics } = args;
    const failures = [];
    // requireElementIdentity: every converted semantic element must declare an identity.
    // We check the report's per-element records (the source of truth for what was
    // actually mapped) rather than the raw inspected set, so structural containers
    // that were ignored or never produced a PPTX object don't trigger the gate.
    if (strict.requireElementIdentity) {
        const missing = [];
        for (const slide of report.slides) {
            for (const rec of slide.elements) {
                if (rec.mapping_mode === 'ignored')
                    continue;
                if (!rec.element_id) {
                    missing.push({ slide: slide.slide_id, kind: rec.kind });
                }
            }
        }
        if (missing.length > 0) {
            failures.push({
                rule_id: diagnostics_1.RULE_IDS.IDENTITY_MISSING,
                severity: 'error',
                message: `strict mode: ${missing.length} converted element(s) lack a declared identity (e.g. "${missing[0].kind}" on slide ${missing[0].slide ?? 1}). Set data-element-id on every semantic element or relax requireElementIdentity.`,
                recovery: 'Add data-element-id to every visible semantic element, or set strict.requireElementIdentity=false.',
            });
        }
    }
    // allowRaster: no raster fallbacks allowed.
    if (!strict.allowRaster) {
        if (report.summary.raster > 0) {
            failures.push({
                rule_id: diagnostics_1.RULE_IDS.RASTER_FALLBACK,
                severity: 'error',
                message: `strict mode: ${report.summary.raster} element(s) fell back to raster. Set strict.allowRaster=true to permit raster fallbacks.`,
                recovery: 'Replace rasterized content with native/vector equivalents, or set strict.allowRaster=true.',
            });
        }
    }
    // allowUnsupported: no unsupported elements allowed.
    if (!strict.allowUnsupported) {
        if (report.summary.unsupported > 0) {
            failures.push({
                rule_id: diagnostics_1.RULE_IDS.KIND_UNSUPPORTED,
                severity: 'error',
                message: `strict mode: ${report.summary.unsupported} element(s) are unsupported. Set strict.allowUnsupported=true to permit unsupported kinds.`,
                recovery: 'Replace unsupported elements with text/image/shape/table/group, or set strict.allowUnsupported=true.',
            });
        }
    }
    // allowUnmappedAnimations: every declared/captured animation must map onto
    // the native PPTX entrance subset.
    if (!strict.allowUnmappedAnimations) {
        const unmapped = animationDiagnostics.filter((d) => d.rule_id === diagnostics_1.RULE_IDS.ANIMATION_UNMAPPED);
        if (unmapped.length > 0) {
            failures.push({
                rule_id: diagnostics_1.RULE_IDS.ANIMATION_UNMAPPED,
                severity: 'error',
                message: `strict mode: ${unmapped.length} animation(s) could not be mapped onto the native PPTX entrance subset. First: ${unmapped[0].message}`,
                recovery: 'Use a supported entrance effect (fade-in, fly-in-*, zoom-in, spin, wipe-*, appear), or set strict.allowUnmappedAnimations=true.',
            });
        }
    }
    // allowRemoteResources: no remote resource access allowed.
    if (!strict.allowRemoteResources) {
        const remoteBlocked = resourceDiagnostics.filter((d) => d.rule_id === diagnostics_1.RULE_IDS.RESOURCE_REMOTE_BLOCKED);
        if (remoteBlocked.length > 0) {
            failures.push({
                rule_id: diagnostics_1.RULE_IDS.RESOURCE_REMOTE_BLOCKED,
                severity: 'error',
                message: `strict mode: ${remoteBlocked.length} remote resource request(s) were blocked. Set strict.allowRemoteResources=true to permit remote resources.`,
                recovery: 'Inline remote resources locally, or set strict.allowRemoteResources=true.',
            });
        }
    }
    // failOnMissingFonts: no unresolved fonts allowed.
    if (strict.failOnMissingFonts) {
        const unmatched = (fontStats.embed?.unmatched ?? []).filter((f) => !isWebSafeFont(f));
        if (unmatched.length > 0) {
            failures.push({
                rule_id: diagnostics_1.RULE_IDS.FONT_MISSING,
                severity: 'error',
                message: `strict mode: ${unmatched.length} font family(ies) could not be resolved: ${unmatched.join(', ')}. Set strict.failOnMissingFonts=false to permit font fallbacks.`,
                recovery: 'Install the missing fonts, embed them via the cloud pipeline, or set strict.failOnMissingFonts=false.',
            });
        }
    }
    if (failures.length > 0) {
        const additional = [
            ...identityDiagnostics,
            ...resourceDiagnostics.map((d) => ({
                rule_id: d.rule_id,
                severity: d.severity,
                message: d.message,
                recovery: d.recovery,
            })),
        ];
        throw new diagnostics_1.ConversionError(failures[0], additional);
    }
}
/**
 * Inspect HTML inputs and collect slide/element/font statistics without generating PPTX.
 */
async function inspectHtmlFonts(options) {
    return (0, quiet_1.runQuietly)(Boolean(options.quiet), async () => {
        const inputPaths = resolveInputPaths(options);
        const platformFontContext = (0, platformFontMap_1.buildPlatformFontContext)(options);
        const loader = new loader_1.HTMLLoader();
        const mergedSlidesMap = new Map();
        const usedFontsMap = new Map();
        let slideCoordsNormalized = false;
        const resourceDiagnostics = [];
        const identityDiagnostics = [];
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
            let slideOffset = 0;
            for (let i = 0; i < inputPaths.length; i++) {
                const inputPath = inputPaths[i];
                const result = await processSingleInput(loader, inputPath, options, platformFontContext, usedFontsMap, undefined, resourceDiagnostics, identityDiagnostics);
                slideCoordsNormalized = slideCoordsNormalized || result.slideCoordsNormalized;
                slideOffset = mergeSlidesMaps(mergedSlidesMap, result.slidesMap, slideOffset);
            }
            const usedFontsDeduped = [
                ...new Set(Array.from(usedFontsMap.values()).map((d) => d.fontFamily)),
            ].sort();
            return {
                usedFonts: usedFontsDeduped,
                slideCount: mergedSlidesMap.size,
                stats: {
                    elements: (0, conversion_report_1.buildElementStats)(mergedSlidesMap),
                    fonts: (0, conversion_report_1.buildFontStats)(usedFontsMap),
                    simplified: (0, conversion_report_1.buildSimplifiedStats)(mergedSlidesMap),
                },
            };
        }
        finally {
            await loader.close().catch(() => { });
        }
    });
}
/**
 * Convert one or more HTML/SVG files to a single PPTX.
 * Each input file becomes one slide by default; use slideSelector or splitByHeight
 * within a file to produce multiple slides from that file.
 */
async function convertHtmlToPptx(options) {
    return (0, quiet_1.runQuietly)(Boolean(options.quiet), async () => {
        const inputPaths = resolveInputPaths(options);
        const platformFontContext = (0, platformFontMap_1.buildPlatformFontContext)(options);
        const loader = new loader_1.HTMLLoader();
        const mergedSlidesMap = new Map();
        const usedFontsMap = new Map();
        let slideCoordsNormalized = false;
        const resourceDiagnostics = [];
        const identityDiagnostics = [];
        await loader.init({
            executablePath: options.browser?.executablePath,
            userDataDir: options.browser?.userDataDir,
            headless: options.browser?.headless,
            args: options.browser?.args,
        }, {
            browser: options.browser?.browser,
            browserContext: options.browser?.browserContext,
        });
        const inspectConcurrency = (0, async_pool_1.resolveSlideInspectConcurrency)();
        let totalExcludedCount = 0;
        const animationDiagnostics = [];
        const parallelInputs = inputPaths.length > 1 && inspectConcurrency > 1;
        if (parallelInputs) {
            const fileConcurrency = Math.min(inspectConcurrency, inputPaths.length);
            console.log(`⚡ Parallel inputs: ${fileConcurrency} HTML files at a time (CPU cores − 2)`);
            const indexed = inputPaths.map((path, index) => ({ path, index }));
            const completed = await (0, async_pool_1.runAsyncPool)(indexed, fileConcurrency, async ({ path, index }) => {
                console.log(`\n📄 Processing ${index + 1}/${inputPaths.length}: ${path}`);
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
                    const result = await processSingleInput(fileLoader, path, options, platformFontContext, usedFontsMap, { slideInspectConcurrency: 1 }, resourceDiagnostics, identityDiagnostics);
                    return { index, result };
                }
                finally {
                    await fileLoader.close().catch(() => { });
                }
            });
            completed.sort((a, b) => a.index - b.index);
            let slideOffset = 0;
            for (const { result } of completed) {
                slideCoordsNormalized = slideCoordsNormalized || result.slideCoordsNormalized;
                totalExcludedCount += result.excludedCount;
                animationDiagnostics.push(...result.animationDiagnostics);
                slideOffset = mergeSlidesMaps(mergedSlidesMap, result.slidesMap, slideOffset);
            }
        }
        else {
            let slideOffset = 0;
            for (let i = 0; i < inputPaths.length; i++) {
                const inputPath = inputPaths[i];
                if (inputPaths.length > 1) {
                    console.log(`\n📄 Processing ${i + 1}/${inputPaths.length}: ${inputPath}`);
                }
                const result = await processSingleInput(loader, inputPath, options, platformFontContext, usedFontsMap, undefined, resourceDiagnostics, identityDiagnostics);
                slideCoordsNormalized = slideCoordsNormalized || result.slideCoordsNormalized;
                totalExcludedCount += result.excludedCount;
                animationDiagnostics.push(...result.animationDiagnostics);
                slideOffset = mergeSlidesMaps(mergedSlidesMap, result.slidesMap, slideOffset);
            }
        }
        const usedFontsDeduped = [...new Set(Array.from(usedFontsMap.values()).map((d) => d.fontFamily))].sort();
        const fontStats = (0, conversion_report_1.buildFontStats)(usedFontsMap);
        const slideTransitionPlan = (0, resolve_1.resolveSlideTransitionPlan)(options.slideTransitions);
        const layoutFaithfulMode = (0, layout_faithful_1.resolveLayoutFaithfulMode)(options.layoutFaithful);
        const allEls = [];
        for (const els of mergedSlidesMap.values())
            allEls.push(...els);
        const closure = (0, font_closure_1.checkFontClosure)(allEls, layoutFaithfulMode);
        for (const d of closure.diagnostics) {
            identityDiagnostics.push(d);
        }
        if (!closure.ok) {
            throw new diagnostics_1.ConversionError(closure.diagnostics.find((d) => d.severity === 'error') || {
                rule_id: diagnostics_1.RULE_IDS.LAYOUT_FAITHFUL_FONT,
                severity: 'error',
                message: 'Layout-faithful font closure failed',
            }, closure.diagnostics);
        }
        if ((0, layout_faithful_1.isLayoutFaithfulStrict)(layoutFaithfulMode)) {
            for (const el of allEls) {
                if (el.type !== 'text' || !el.content?.trim())
                    continue;
                if (el.needsScreenshot && el.screenshotSelector)
                    continue;
                if (el.layoutFaithfulUnsupportedReason === 'vertical_writing' ||
                    el.layoutFaithfulUnsupportedReason === 'rtl_or_bidi' ||
                    el.layoutFaithfulUnsupportedReason === 'unsupported_transform') {
                    throw new diagnostics_1.ConversionError({
                        rule_id: diagnostics_1.RULE_IDS.LAYOUT_FAITHFUL_UNSUPPORTED,
                        severity: 'error',
                        element_id: el.elementId ?? null,
                        message: `Strict layout-faithful: unsupported text (${el.layoutFaithfulUnsupportedReason})`,
                        recovery: 'Simplify the layout or use supported text geometry.',
                    });
                }
            }
        }
        const generator = new generator_1.PPTXGenerator({
            platformFontContext,
            splitByHeight: options.splitByHeight,
            slideSelector: options.slideSelector,
            slideCoordsNormalized,
            slideTransitionPlan,
        });
        generator.report.ignoredCount = totalExcludedCount;
        for (const d of identityDiagnostics)
            generator.report.diagnostics.push(d);
        for (const d of animationDiagnostics)
            generator.report.diagnostics.push(d);
        for (const d of resourceDiagnostics) {
            generator.report.diagnostics.push({
                rule_id: d.rule_id,
                severity: d.severity,
                message: d.message,
                recovery: d.recovery,
            });
        }
        const data = await generator.generate(mergedSlidesMap);
        for (const note of generator.getLayoutFaithfulNotes()) {
            generator.report.diagnostics.push({
                rule_id: note.reason === 'font_shrink'
                    ? diagnostics_1.RULE_IDS.LAYOUT_FAITHFUL_SHRINK
                    : diagnostics_1.RULE_IDS.LAYOUT_FAITHFUL_FALLBACK,
                severity: 'info',
                element_id: note.elementId ?? null,
                message: note.message,
            });
        }
        const slideCount = generator.getSlideCount();
        const conversionReport = generator.report.build('@deckflow/deckhtml', ENGINE_VERSION, 'succeeded');
        // Embed every resolvable deck face (FA + Source/Inter/Barlow/…) so openers
        // do not substitute system fonts and reflow frozen Chromium line boxes.
        const dataWithFaFonts = await (0, ooxml_normalize_1.normalizeUniqueShapeIds)(await (0, deck_font_embedder_1.embedDeckFonts)(data));
        reportUsedFonts(usedFontsDeduped, fontStats);
        // Aggregate unified diagnostics (DH-P0-009): identity + resource + report-level.
        const unifiedDiagnostics = new diagnostics_1.DiagnosticsCollector();
        unifiedDiagnostics.pushMany(identityDiagnostics);
        unifiedDiagnostics.pushMany(animationDiagnostics);
        for (const d of resourceDiagnostics) {
            unifiedDiagnostics.push({
                rule_id: d.rule_id,
                severity: d.severity,
                message: d.message,
                recovery: d.recovery,
            });
        }
        unifiedDiagnostics.pushMany(conversionReport.diagnostics ?? []);
        // DH-P0-010: OOXML self-check — reopen the generated package and verify
        // slide count, object_ref closure, full-page image and remote relationships.
        // Always run the check (cheap) and surface diagnostics; strict mode hard-fails.
        let ooxmlDiagnostics = [];
        try {
            const verification = await (0, ooxml_verify_1.verifyOoxml)(dataWithFaFonts, conversionReport);
            ooxmlDiagnostics = verification.diagnostics;
            unifiedDiagnostics.pushMany(ooxmlDiagnostics);
        }
        catch (err) {
            ooxmlDiagnostics = [{
                    rule_id: diagnostics_1.RULE_IDS.OOXML_REOPEN_FAILURE,
                    severity: 'error',
                    message: `OOXML self-check threw: ${err instanceof Error ? err.message : String(err)}`,
                }];
            unifiedDiagnostics.pushMany(ooxmlDiagnostics);
        }
        // DH-P0-003: enforce strict-mode gates before returning a successful result.
        const strictConfig = resolveStrictConfig(options.strict);
        if (strictConfig) {
            enforceStrictMode({
                strict: strictConfig,
                report: conversionReport,
                resourceDiagnostics,
                fontStats,
                identityDiagnostics,
                animationDiagnostics,
            });
            // DH-P0-010: in strict mode, OOXML self-check errors are hard failures.
            const ooxmlErrors = ooxmlDiagnostics.filter((d) => d.severity === 'error');
            if (ooxmlErrors.length > 0) {
                throw new diagnostics_1.ConversionError(ooxmlErrors[0], ooxmlDiagnostics);
            }
        }
        return {
            data: dataWithFaFonts,
            usedFonts: usedFontsDeduped,
            slideCount,
            shapeMap: generator.getShapeMap(),
            stats: {
                elements: (0, conversion_report_1.buildElementStats)(mergedSlidesMap),
                fonts: fontStats,
                simplified: (0, conversion_report_1.buildSimplifiedStats)(mergedSlidesMap),
            },
            resourceDiagnostics,
            identityDiagnostics,
            diagnostics: unifiedDiagnostics.toJSON(),
            report: conversionReport,
        };
    });
}
exports.default = convertHtmlToPptx;
