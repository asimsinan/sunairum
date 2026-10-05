"use strict";
/**
 * Main entry point
 * Re-exports API for programmatic use
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __exportStar = (this && this.__exportStar) || function(m, exports) {
    for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(exports, p)) __createBinding(exports, m, p);
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.genericKindFromToken = exports.detectStackGenericName = exports.detectStackGenericKind = exports.GENERIC_FONT_OS_MAP = exports.detectCurrentPlatformTarget = exports.DEFAULT_PLATFORM_TARGET = exports.buildPlatformFontContext = exports.extractCoreFontName = exports.splitFontStack = exports.matchChineseFontAlias = exports.isChineseFont = exports.parseGradientCoverage = exports.normalizeFontAwesomeFamily = exports.normalizeFontAwesomeFreeFamily = exports.resolveFontBytesForTypeface = exports.resolveDeckFontDirs = exports.embedDeckFonts = exports.embedFontAwesomeFonts = exports.EMBED_FONT_INDEX_META = exports.matchEmbeddableFont = exports.probeEmbeddableFonts = exports.EMPTY_CONVERSION_STATS = exports.buildSimplifiedStats = exports.buildFontStats = exports.buildElementStats = exports.buildConversionReport = exports.resolveSlideTransitionPlan = exports.resolveSlideTransition = exports.SLIDE_TRANSITION_EFFECTS = exports.isSlideTransitionEffectName = exports.getSlideTransitionEffect = exports.listRandomPoolEffects = exports.listSlideTransitionEffectNamesByTier = exports.listSlideTransitionEffectNames = exports.setViewportPixels = exports.EMU_PER_INCH = exports.emuRoundTripErrorPxX = exports.pxToEmuY = exports.pxToEmuX = exports.checkFontClosure = exports.LAYOUT_FAITHFUL_GEOM_TOL_PX = exports.LAYOUT_FAITHFUL_MAX_FONT_SHRINK = exports.boundFontShrink = exports.classifyLayoutFaithfulEligibility = exports.applyChromiumSoftBreaks = exports.resolveLayoutFaithfulMode = exports.buildPngOutputPaths = exports.convertHtmlToPng = exports.inspectHtmlFonts = exports.convertHtmlToPptx = void 0;
exports.isGenericFontToken = exports.getPlatformMappedFontStack = exports.getPlatformMappedFontByToken = exports.getPlatformMappedFont = exports.getPlatformFontMappingByName = exports.getPlatformFontMapping = exports.genericNameFromToken = void 0;
var api_1 = require("./api");
Object.defineProperty(exports, "convertHtmlToPptx", { enumerable: true, get: function () { return api_1.convertHtmlToPptx; } });
Object.defineProperty(exports, "inspectHtmlFonts", { enumerable: true, get: function () { return api_1.inspectHtmlFonts; } });
var png_export_1 = require("./png-export");
Object.defineProperty(exports, "convertHtmlToPng", { enumerable: true, get: function () { return png_export_1.convertHtmlToPng; } });
var png_output_path_1 = require("./utils/png-output-path");
Object.defineProperty(exports, "buildPngOutputPaths", { enumerable: true, get: function () { return png_output_path_1.buildPngOutputPaths; } });
__exportStar(require("./types"), exports);
var layout_faithful_1 = require("./utils/layout-faithful");
Object.defineProperty(exports, "resolveLayoutFaithfulMode", { enumerable: true, get: function () { return layout_faithful_1.resolveLayoutFaithfulMode; } });
Object.defineProperty(exports, "applyChromiumSoftBreaks", { enumerable: true, get: function () { return layout_faithful_1.applyChromiumSoftBreaks; } });
Object.defineProperty(exports, "classifyLayoutFaithfulEligibility", { enumerable: true, get: function () { return layout_faithful_1.classifyLayoutFaithfulEligibility; } });
Object.defineProperty(exports, "boundFontShrink", { enumerable: true, get: function () { return layout_faithful_1.boundFontShrink; } });
Object.defineProperty(exports, "LAYOUT_FAITHFUL_MAX_FONT_SHRINK", { enumerable: true, get: function () { return layout_faithful_1.LAYOUT_FAITHFUL_MAX_FONT_SHRINK; } });
Object.defineProperty(exports, "LAYOUT_FAITHFUL_GEOM_TOL_PX", { enumerable: true, get: function () { return layout_faithful_1.LAYOUT_FAITHFUL_GEOM_TOL_PX; } });
var font_closure_1 = require("./utils/font-closure");
Object.defineProperty(exports, "checkFontClosure", { enumerable: true, get: function () { return font_closure_1.checkFontClosure; } });
var coordinate_1 = require("./utils/coordinate");
Object.defineProperty(exports, "pxToEmuX", { enumerable: true, get: function () { return coordinate_1.pxToEmuX; } });
Object.defineProperty(exports, "pxToEmuY", { enumerable: true, get: function () { return coordinate_1.pxToEmuY; } });
Object.defineProperty(exports, "emuRoundTripErrorPxX", { enumerable: true, get: function () { return coordinate_1.emuRoundTripErrorPxX; } });
Object.defineProperty(exports, "EMU_PER_INCH", { enumerable: true, get: function () { return coordinate_1.EMU_PER_INCH; } });
Object.defineProperty(exports, "setViewportPixels", { enumerable: true, get: function () { return coordinate_1.setViewportPixels; } });
var catalog_1 = require("./slide-transition/catalog");
Object.defineProperty(exports, "listSlideTransitionEffectNames", { enumerable: true, get: function () { return catalog_1.listSlideTransitionEffectNames; } });
Object.defineProperty(exports, "listSlideTransitionEffectNamesByTier", { enumerable: true, get: function () { return catalog_1.listSlideTransitionEffectNamesByTier; } });
Object.defineProperty(exports, "listRandomPoolEffects", { enumerable: true, get: function () { return catalog_1.listRandomPoolEffects; } });
Object.defineProperty(exports, "getSlideTransitionEffect", { enumerable: true, get: function () { return catalog_1.getSlideTransitionEffect; } });
Object.defineProperty(exports, "isSlideTransitionEffectName", { enumerable: true, get: function () { return catalog_1.isSlideTransitionEffectName; } });
Object.defineProperty(exports, "SLIDE_TRANSITION_EFFECTS", { enumerable: true, get: function () { return catalog_1.SLIDE_TRANSITION_EFFECTS; } });
var resolve_1 = require("./slide-transition/resolve");
Object.defineProperty(exports, "resolveSlideTransition", { enumerable: true, get: function () { return resolve_1.resolveSlideTransition; } });
Object.defineProperty(exports, "resolveSlideTransitionPlan", { enumerable: true, get: function () { return resolve_1.resolveSlideTransitionPlan; } });
var conversion_report_1 = require("./conversion-report");
Object.defineProperty(exports, "buildConversionReport", { enumerable: true, get: function () { return conversion_report_1.buildConversionReport; } });
Object.defineProperty(exports, "buildElementStats", { enumerable: true, get: function () { return conversion_report_1.buildElementStats; } });
Object.defineProperty(exports, "buildFontStats", { enumerable: true, get: function () { return conversion_report_1.buildFontStats; } });
Object.defineProperty(exports, "buildSimplifiedStats", { enumerable: true, get: function () { return conversion_report_1.buildSimplifiedStats; } });
Object.defineProperty(exports, "EMPTY_CONVERSION_STATS", { enumerable: true, get: function () { return conversion_report_1.EMPTY_CONVERSION_STATS; } });
var embedFonts_1 = require("./utils/embedFonts");
Object.defineProperty(exports, "probeEmbeddableFonts", { enumerable: true, get: function () { return embedFonts_1.probeEmbeddableFonts; } });
Object.defineProperty(exports, "matchEmbeddableFont", { enumerable: true, get: function () { return embedFonts_1.matchEmbeddableFont; } });
Object.defineProperty(exports, "EMBED_FONT_INDEX_META", { enumerable: true, get: function () { return embedFonts_1.EMBED_FONT_INDEX_META; } });
var fa_font_embedder_1 = require("./utils/fa-font-embedder");
Object.defineProperty(exports, "embedFontAwesomeFonts", { enumerable: true, get: function () { return fa_font_embedder_1.embedFontAwesomeFonts; } });
var deck_font_embedder_1 = require("./utils/deck-font-embedder");
Object.defineProperty(exports, "embedDeckFonts", { enumerable: true, get: function () { return deck_font_embedder_1.embedDeckFonts; } });
Object.defineProperty(exports, "resolveDeckFontDirs", { enumerable: true, get: function () { return deck_font_embedder_1.resolveDeckFontDirs; } });
Object.defineProperty(exports, "resolveFontBytesForTypeface", { enumerable: true, get: function () { return deck_font_embedder_1.resolveFontBytesForTypeface; } });
var style_1 = require("./utils/style");
Object.defineProperty(exports, "normalizeFontAwesomeFreeFamily", { enumerable: true, get: function () { return style_1.normalizeFontAwesomeFreeFamily; } });
Object.defineProperty(exports, "normalizeFontAwesomeFamily", { enumerable: true, get: function () { return style_1.normalizeFontAwesomeFamily; } });
Object.defineProperty(exports, "parseGradientCoverage", { enumerable: true, get: function () { return style_1.parseGradientCoverage; } });
var chineseFonts_1 = require("./utils/chineseFonts");
Object.defineProperty(exports, "isChineseFont", { enumerable: true, get: function () { return chineseFonts_1.isChineseFont; } });
Object.defineProperty(exports, "matchChineseFontAlias", { enumerable: true, get: function () { return chineseFonts_1.matchChineseFontAlias; } });
Object.defineProperty(exports, "splitFontStack", { enumerable: true, get: function () { return chineseFonts_1.splitFontStack; } });
Object.defineProperty(exports, "extractCoreFontName", { enumerable: true, get: function () { return chineseFonts_1.extractCoreFontName; } });
var platformFontMap_1 = require("./utils/platformFontMap");
Object.defineProperty(exports, "buildPlatformFontContext", { enumerable: true, get: function () { return platformFontMap_1.buildPlatformFontContext; } });
Object.defineProperty(exports, "DEFAULT_PLATFORM_TARGET", { enumerable: true, get: function () { return platformFontMap_1.DEFAULT_PLATFORM_TARGET; } });
Object.defineProperty(exports, "detectCurrentPlatformTarget", { enumerable: true, get: function () { return platformFontMap_1.detectCurrentPlatformTarget; } });
Object.defineProperty(exports, "GENERIC_FONT_OS_MAP", { enumerable: true, get: function () { return platformFontMap_1.GENERIC_FONT_OS_MAP; } });
Object.defineProperty(exports, "detectStackGenericKind", { enumerable: true, get: function () { return platformFontMap_1.detectStackGenericKind; } });
Object.defineProperty(exports, "detectStackGenericName", { enumerable: true, get: function () { return platformFontMap_1.detectStackGenericName; } });
Object.defineProperty(exports, "genericKindFromToken", { enumerable: true, get: function () { return platformFontMap_1.genericKindFromToken; } });
Object.defineProperty(exports, "genericNameFromToken", { enumerable: true, get: function () { return platformFontMap_1.genericNameFromToken; } });
Object.defineProperty(exports, "getPlatformFontMapping", { enumerable: true, get: function () { return platformFontMap_1.getPlatformFontMapping; } });
Object.defineProperty(exports, "getPlatformFontMappingByName", { enumerable: true, get: function () { return platformFontMap_1.getPlatformFontMappingByName; } });
Object.defineProperty(exports, "getPlatformMappedFont", { enumerable: true, get: function () { return platformFontMap_1.getPlatformMappedFont; } });
Object.defineProperty(exports, "getPlatformMappedFontByToken", { enumerable: true, get: function () { return platformFontMap_1.getPlatformMappedFontByToken; } });
Object.defineProperty(exports, "getPlatformMappedFontStack", { enumerable: true, get: function () { return platformFontMap_1.getPlatformMappedFontStack; } });
Object.defineProperty(exports, "isGenericFontToken", { enumerable: true, get: function () { return platformFontMap_1.isGenericFontToken; } });
