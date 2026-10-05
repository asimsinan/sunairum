"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.registerConvertCommand = registerConvertCommand;
const path_1 = __importDefault(require("path"));
const api_1 = require("../../api");
const png_export_1 = require("../../png-export");
const platformFontMap_1 = require("../../utils/platformFontMap");
const png_output_path_1 = require("../../utils/png-output-path");
const input_1 = require("../utils/input");
const output_1 = require("../utils/output");
const conversion_report_1 = require("../../conversion-report");
const mode_1 = require("../utils/mode");
const size_1 = require("../utils/size");
const write_1 = require("../utils/write");
const viewport_1 = require("../../utils/viewport");
const catalog_1 = require("../../slide-transition/catalog");
const DEFAULT_TIMEOUT = 600;
const VALID_PLATFORMS = ['win', 'mac', 'ios', 'android', 'linux'];
function resolvePlatformOption(platform) {
    if (!platform)
        return (0, platformFontMap_1.detectCurrentPlatformTarget)();
    if (!VALID_PLATFORMS.includes(platform)) {
        throw new Error(`Invalid --platform: ${platform}. Use win, mac, ios, android, or linux.`);
    }
    return platform;
}
function toCloudPlatform(platform) {
    return platform === 'mac' || platform === 'ios' ? 'mac' : 'win';
}
/**
 * Map CLI flags onto ConversionOptions.slideTransitions.
 * `--no-slide-transitions` wins; else `--slide-transition <name[,name…]>`; else random.
 */
function resolveCliSlideTransitions(options) {
    if (options.slideTransitions === false)
        return false;
    const name = options.slideTransition?.trim();
    if (!name)
        return true; // default: random
    const lower = name.toLowerCase();
    if (lower === 'none' || lower === 'off' || lower === 'false')
        return false;
    if (lower === 'random')
        return 'random';
    const parts = name
        .split(',')
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
    if (parts.length === 0)
        return true;
    for (const part of parts) {
        if (part === 'random') {
            throw new Error('Invalid --slide-transition: "random" cannot be mixed with named effects; ' +
                'use --slide-transition random alone, or a comma-separated catalog list');
        }
        if (!(0, catalog_1.isSlideTransitionEffectName)(part)) {
            const known = (0, catalog_1.listSlideTransitionEffectNames)().join(', ');
            throw new Error(`Invalid --slide-transition effect "${part}". Available: ${known}, random, none`);
        }
    }
    // Preserve comma-separated form for the resolver (single or cycle).
    return parts.join(',');
}
/**
 * Map `--iframes <mode>` onto ConversionOptions.iframes.
 * Accepts inspect / screenshot / skip; undefined when unset (API default).
 */
function resolveIframesOption(mode) {
    if (!mode)
        return undefined;
    const lower = mode.trim().toLowerCase();
    if (lower === 'inspect' || lower === 'screenshot' || lower === 'skip') {
        return lower;
    }
    throw new Error(`Invalid --iframes: ${mode}. Use inspect, screenshot, or skip.`);
}
/**
 * Parse `--iframe-load-timeout-ms <ms>` into a positive integer; undefined when unset.
 */
function resolveIframeLoadTimeoutMs(value) {
    if (!value)
        return undefined;
    const ms = parseInt(value, 10);
    if (Number.isNaN(ms) || ms < 1) {
        throw new Error(`Invalid --iframe-load-timeout-ms: ${value}. Use a positive integer.`);
    }
    return ms;
}
function buildCloudParams(options, platform, viewport) {
    const params = {
        needEmbedFonts: Boolean(options.embedFonts),
        platform,
    };
    if (viewport) {
        params.width = viewport.width;
        params.height = viewport.height;
    }
    return params;
}
async function runLocalConvert(ctx, inputPaths, outputPath, viewport, format, platform, executablePath, force, excludeSelector, identityAttribute, animations, slideTransitions, iframesMode, iframeLoadTimeoutMsStr) {
    const iframes = resolveIframesOption(iframesMode);
    const iframeLoadTimeoutMs = resolveIframeLoadTimeoutMs(iframeLoadTimeoutMsStr);
    const resolvedViewport = viewport ??
        (0, viewport_1.detectViewportFromFile)(inputPaths[0]) ?? {
        width: viewport_1.DEFAULT_VIEWPORT_WIDTH,
        height: viewport_1.DEFAULT_VIEWPORT_HEIGHT,
    };
    const viewportOpts = viewport
        ? {
            viewportWidth: viewport.width,
            viewportHeight: viewport.height,
        }
        : {};
    if (format === 'png') {
        (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `Rendering PNG from ${inputPaths.length} file(s)`);
        (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `Viewport: ${resolvedViewport.width}x${resolvedViewport.height}${viewport ? '' : ' (auto)'}`);
        const result = await (0, png_export_1.convertHtmlToPng)({
            inputs: inputPaths,
            ...viewportOpts,
            allowLocalResources: true,
            quiet: ctx.quiet,
            excludeSelector,
            identityAttribute,
            browser: executablePath ? { executablePath } : undefined,
            iframes,
            iframeLoadTimeoutMs,
        });
        const outputPaths = (0, png_output_path_1.buildPngOutputPaths)(outputPath, result.images.length);
        for (let i = 0; i < result.images.length; i++) {
            const target = outputPaths[i];
            await (0, write_1.atomicWriteFile)(target, result.images[i], { overwrite: force });
            (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `Writing ${target}`);
        }
        return {
            ok: true,
            input: inputPaths,
            output: outputPaths[0],
            outputs: outputPaths,
            format,
            mode: 'local',
            slideCount: result.slideCount,
            stats: result.stats,
        };
    }
    if (format !== 'pptx') {
        throw new Error(`Format "${format}" is not supported in local mode. Use --mode cloud.`);
    }
    if (inputPaths.length > 1) {
        (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `Merging ${inputPaths.length} HTML files into one PPTX`);
    }
    else {
        (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `Rendering ${inputPaths[0]}`);
    }
    (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `Viewport: ${resolvedViewport.width}x${resolvedViewport.height}${viewport ? '' : ' (auto)'}`);
    (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `Font mapping: platform=${platform} (script auto-detected from text)`);
    const result = await (0, api_1.convertHtmlToPptx)({
        inputs: inputPaths,
        ...viewportOpts,
        allowLocalResources: true,
        quiet: ctx.quiet,
        platform,
        excludeSelector,
        identityAttribute,
        animations,
        slideTransitions,
        browser: executablePath ? { executablePath } : undefined,
        iframes,
        iframeLoadTimeoutMs,
    });
    await (0, write_1.atomicWriteFile)(outputPath, result.data, { overwrite: force });
    (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `Writing ${outputPath}`);
    // Always write shape-map next to PPTX for closed-loop visual verify.
    if (result.shapeMap && result.shapeMap.length > 0) {
        const shapeMapPath = `${outputPath}.shape-map.json`;
        await (0, write_1.atomicWriteFile)(shapeMapPath, `${JSON.stringify({ shapes: result.shapeMap }, null, 2)}\n`, { overwrite: true });
        (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `Writing ${shapeMapPath}`);
    }
    return {
        ok: true,
        input: inputPaths,
        output: outputPath,
        format,
        mode: 'local',
        slideCount: result.slideCount,
        stats: result.stats,
        conversionReport: result.report,
        shapeMap: result.shapeMap,
    };
}
async function runCloudConvert(ctx, inputPaths, outputPath, options, platform, viewport, format) {
    if (format === 'pdf') {
        throw new Error('PDF output is not yet supported.');
    }
    const deck = await ctx.getDeck();
    const spaceId = ctx.config.get('spaceId');
    const params = buildCloudParams(options, toCloudPlatform(platform), viewport);
    const taskName = path_1.default.basename(inputPaths[0], path_1.default.extname(inputPaths[0]));
    (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, `API base: ${ctx.config.apiBase}`);
    if (!ctx.hasCredentials()) {
        (0, output_1.logProgress)(ctx.quiet, 'Guest mode (X-Auth-UUID only): cloud usage is rate-limited. Run `deckhtml auth login` or `deckhtml config set api-key <key>` for full access.');
    }
    (0, output_1.logVerbose)(ctx.verbose, ctx.quiet, spaceId ? `Space ID: ${spaceId}` : 'Space ID: auto (GET /user/self)');
    (0, output_1.logProgress)(ctx.quiet, `Uploading ${inputPaths.length} file(s)...`);
    const taskInput = {
        ...(spaceId ? { spaceId } : {}),
        files: inputPaths,
        name: taskName,
        params: params,
        upload: {
            onProgress: (p) => (0, output_1.logProgress)(ctx.quiet, `Uploading: ${(p * 100).toFixed(1)}%`),
        },
    };
    const task = format === 'png'
        ? await deck.convertHtmlToPng(taskInput)
        : await deck.convertHtmlToPptx(taskInput);
    (0, output_1.logProgress)(ctx.quiet, `Task created: ${task.id}`);
    // Guest mode (no token/api-key): the backend parks the task in pending and
    // waits for an explicit start. If create triggered 401 → login → retry,
    // credentials are now set and authenticated tasks auto-start.
    if (!ctx.hasCredentials()) {
        (0, output_1.logProgress)(ctx.quiet, 'Starting guest task...');
        await deck.tasks.start(task.id);
    }
    (0, output_1.logProgress)(ctx.quiet, 'Converting...');
    const completed = await deck.tasks.wait(task.id, {
        timeout: DEFAULT_TIMEOUT,
        useEventStream: true,
        onProgress: (next) => {
            if (next.status === 'running') {
                (0, output_1.logProgress)(ctx.quiet, `Status: ${next.status}`);
            }
        },
    });
    if (completed.status !== 'completed') {
        throw new Error(completed.error ?? `Conversion failed (${completed.status})`);
    }
    const download = await deck.tasks.down(task.id);
    const writeResult = await (0, output_1.writeTaskOutput)(completed, outputPath, download);
    const finalOutput = writeResult.kind === 'file' || writeResult.kind === 'json'
        ? writeResult.path
        : writeResult.path;
    // Font / simplified stats are PPTX-oriented (embed tips, rasterized elements).
    // PNG skips probing so local and cloud stay quiet and consistent.
    if (format !== 'pptx') {
        return {
            ok: true,
            input: inputPaths,
            output: finalOutput,
            format,
            mode: 'cloud',
        };
    }
    (0, output_1.logProgress)(ctx.quiet, 'Probing fonts used in HTML...');
    const inspect = await (0, api_1.inspectHtmlFonts)({
        inputs: inputPaths,
        viewportWidth: viewport?.width,
        viewportHeight: viewport?.height,
        allowLocalResources: true,
        quiet: true,
        platform,
    });
    return {
        ok: true,
        input: inputPaths,
        output: finalOutput,
        format,
        mode: 'cloud',
        slideCount: inspect.slideCount,
        stats: inspect.stats,
    };
}
function registerConvertCommand(program, ctx) {
    program
        .argument('[inputs...]', 'HTML file(s), URL, or "-" for stdin')
        .option('-o, --output <path>', 'Output path (.pptx / .png; format inferred from extension)')
        .option('--mode <mode>', 'Execution mode: auto, local, or cloud', 'auto')
        .option('--width <pixels>', 'Playwright viewport width (height scales at 16:9). When omitted, auto-detect from HTML deck-size / viewport meta / CSS size vars / slide hosts, else 1280')
        .option('--platform <platform>', 'Target platform: local supports win, mac, ios, android, linux; cloud uses mac or win (ios→mac, others→win)')
        .option('--embed-fonts', 'Embed fonts into the PPTX (local: deck faces from DECKHTML_FONTS_DIR/assets; cloud: library). Local mode already embeds by default.', false)
        .option('--report', 'Generate conversion report (+ shape-map) next to output', false)
        .option('--executable-path <path>', 'Chromium executable to use for local conversion (overrides DECKHTML_CHROMIUM_EXECUTABLE_PATH)')
        .option('--exclude <selector>', 'CSS selector matching runtime/navigation elements to exclude from conversion')
        .option('--identity-attribute <name>', 'Attribute carrying a stable element identity (default: data-element-id)')
        .option('--force', 'Overwrite an existing output file instead of refusing (default: refuse)', false)
        .option('--no-animations', 'Disable entrance-animation export (data-animation*, CSS @keyframes/transitions, anime.js interception)')
        .option('--slide-transition <name>', 'Slide-to-slide transition effect(s). Comma-separated names cycle in order (default: random). Use "none" to disable')
        .option('--no-slide-transitions', 'Disable slide-to-slide transition effects (p:transition)')
        .option('--iframes <mode>', 'How to handle iframe elements: inspect (default), screenshot, or skip. Local mode only')
        .option('--iframe-load-timeout-ms <ms>', 'Timeout for loading iframe documents in a new page (default: 8000)')
        .action(async (inputs, options) => {
        if (inputs.length === 0) {
            return;
        }
        try {
            const modeInput = options.mode.toLowerCase();
            if (!['auto', 'local', 'cloud'].includes(modeInput)) {
                throw new Error(`Invalid --mode: ${options.mode}. Use auto, local, or cloud.`);
            }
            const resolved = await (0, input_1.resolveInputs)(inputs);
            const { paths, cleanup } = await (0, input_1.materializeInputs)(resolved);
            try {
                if (resolved.kind === 'stdin' && !options.output) {
                    throw new Error('--output is required when reading HTML from stdin.');
                }
                const format = (0, input_1.resolveOutputFormat)(options.output);
                const mode = (0, mode_1.resolveMode)(modeInput, ctx.hasCredentials());
                (0, mode_1.validateCloudOnlyFlags)(mode, {
                    embedFonts: options.embedFonts,
                });
                const platform = resolvePlatformOption(options.platform);
                const outputPath = (0, input_1.deriveOutputPath)(paths, format, options.output);
                // Omit viewport when --width is unset so API auto-detects from HTML/SVG.
                const explicitViewport = (0, size_1.resolveViewport)(options.width, false);
                const localViewport = explicitViewport;
                const cloudViewport = explicitViewport ??
                    (0, viewport_1.detectViewportFromFile)(paths[0]) ??
                    undefined;
                const startedAt = Date.now();
                let envelope;
                const slideTransitions = resolveCliSlideTransitions(options);
                if (mode === 'cloud') {
                    envelope = await runCloudConvert(ctx, paths, outputPath, options, platform, cloudViewport, format);
                }
                else {
                    envelope = await runLocalConvert(ctx, paths, outputPath, localViewport, format, platform, options.executablePath, options.force, options.exclude, options.identityAttribute, options.animations, slideTransitions, options.iframes, options.iframeLoadTimeoutMs);
                }
                if (options.report) {
                    const reportPath = `${outputPath}.report.json`;
                    const reportViewport = (mode === 'local' ? localViewport : cloudViewport) ??
                        (0, viewport_1.detectViewportFromFile)(paths[0]) ?? {
                        width: viewport_1.DEFAULT_VIEWPORT_WIDTH,
                        height: viewport_1.DEFAULT_VIEWPORT_HEIGHT,
                    };
                    // Prefer the new structured per-element report (DH-P0-002) when available
                    // (local mode); fall back to the aggregate stats report for cloud mode.
                    const report = envelope.conversionReport ??
                        (0, conversion_report_1.buildConversionReport)({
                            input: paths,
                            output: outputPath,
                            format,
                            mode: envelope.mode,
                            slideCount: envelope.slideCount ?? 0,
                            stats: envelope.stats ?? conversion_report_1.EMPTY_CONVERSION_STATS,
                            platform,
                            viewport: reportViewport,
                            durationMs: Date.now() - startedAt,
                        });
                    await (0, write_1.atomicWriteFile)(reportPath, `${JSON.stringify(report, null, 2)}\n`, {
                        overwrite: options.force,
                    });
                    envelope.report = reportPath;
                }
                envelope = (0, output_1.attachSimplifiedToEnvelope)(envelope);
                if (format === 'pptx') {
                    (0, output_1.printSimplifiedNotice)(envelope.simplified, envelope.mode, ctx.quiet, ctx.jsonOutput);
                    (0, output_1.printFontEmbedNotice)(envelope.stats?.fonts, envelope.mode, Boolean(options.embedFonts), ctx.quiet, ctx.jsonOutput);
                }
                (0, output_1.printSuccess)(envelope, ctx.jsonOutput);
                process.exit(0);
            }
            finally {
                await cleanup();
            }
        }
        catch (error) {
            ctx.error(error);
        }
    });
}
