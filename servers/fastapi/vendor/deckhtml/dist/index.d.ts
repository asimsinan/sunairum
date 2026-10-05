/**
 * Main entry point
 * Re-exports API for programmatic use
 */
export { convertHtmlToPptx, inspectHtmlFonts } from './api';
export { convertHtmlToPng, type PngConversionResult } from './png-export';
export { buildPngOutputPaths } from './utils/png-output-path';
export * from './types';
export { resolveLayoutFaithfulMode, applyChromiumSoftBreaks, classifyLayoutFaithfulEligibility, boundFontShrink, LAYOUT_FAITHFUL_MAX_FONT_SHRINK, LAYOUT_FAITHFUL_GEOM_TOL_PX, } from './utils/layout-faithful';
export { checkFontClosure } from './utils/font-closure';
export { pxToEmuX, pxToEmuY, emuRoundTripErrorPxX, EMU_PER_INCH, setViewportPixels, } from './utils/coordinate';
export { listSlideTransitionEffectNames, listSlideTransitionEffectNamesByTier, listRandomPoolEffects, getSlideTransitionEffect, isSlideTransitionEffectName, SLIDE_TRANSITION_EFFECTS, } from './slide-transition/catalog';
export { resolveSlideTransition, resolveSlideTransitionPlan } from './slide-transition/resolve';
export { buildConversionReport, buildElementStats, buildFontStats, buildSimplifiedStats, EMPTY_CONVERSION_STATS, type ConversionReport, type ConversionStats, type ConversionElementStats, type ConversionFontStats, type ConversionSimplifiedStats, type ElementTypeCounts, type FontEmbedMatch, type FontEmbedProbeResult, type SimplifiedElementEntry, type SlideElementStats, type SlideSimplifiedStats, } from './conversion-report';
export { probeEmbeddableFonts, matchEmbeddableFont, EMBED_FONT_INDEX_META, } from './utils/embedFonts';
export { embedFontAwesomeFonts } from './utils/fa-font-embedder';
export { embedDeckFonts, resolveDeckFontDirs, resolveFontBytesForTypeface, } from './utils/deck-font-embedder';
export { normalizeFontAwesomeFreeFamily, normalizeFontAwesomeFamily, parseGradientCoverage, type GradientCoverage, } from './utils/style';
export { isChineseFont, matchChineseFontAlias, splitFontStack, extractCoreFontName, type IsChineseFontOptions, } from './utils/chineseFonts';
export { buildPlatformFontContext, DEFAULT_PLATFORM_TARGET, detectCurrentPlatformTarget, type GenericFontKind, type GenericFontName, type PlatformFontContext, type PlatformFontLang, type PlatformFontMappingEntry, type PlatformTarget, GENERIC_FONT_OS_MAP, detectStackGenericKind, detectStackGenericName, genericKindFromToken, genericNameFromToken, getPlatformFontMapping, getPlatformFontMappingByName, getPlatformMappedFont, getPlatformMappedFontByToken, getPlatformMappedFontStack, isGenericFontToken, } from './utils/platformFontMap';
