import { GENERIC_FONT_OS_MAP, PlatformFontMappingEntry } from './platformFontMap.data';
/** PPTX target platforms with full mapping tables. */
export type PlatformTarget = 'win' | 'mac' | 'ios' | 'android' | 'linux';
/** Default platform when callers omit `platform` (programmatic API). */
export declare const DEFAULT_PLATFORM_TARGET: PlatformTarget;
export type PlatformFontLang = 'sc' | 'tc' | 'jp' | 'kr' | 'ar' | 'he' | 'latin';
/** CSS generic font-family keywords (each may map to a different OS font). */
export type GenericFontName = 'serif' | 'sans-serif' | 'monospace' | 'cursive' | 'fantasy' | 'system-ui' | 'ui-serif' | 'ui-sans-serif' | 'ui-monospace' | 'math';
/** Collapsed family category for script-slot logic (sans vs serif vs mono, etc.). */
export type GenericFontKind = 'serif' | 'sans' | 'monospace' | 'cursive' | 'fantasy' | 'math';
export interface PlatformFontContext {
    platform: PlatformTarget;
}
export declare function genericNameFromToken(token: string): GenericFontName | undefined;
export declare function genericKindFromToken(token: string): GenericFontKind | undefined;
export declare function isGenericFontToken(token: string): boolean;
export declare function isPlatformFontContextActive(ctx?: PlatformFontContext): ctx is PlatformFontContext;
export declare function getPlatformFontMappingByName(genericName: GenericFontName, ctx: PlatformFontContext, lang?: PlatformFontLang): PlatformFontMappingEntry;
export declare function getPlatformFontMapping(kind: GenericFontKind, ctx: PlatformFontContext, lang?: PlatformFontLang): PlatformFontMappingEntry;
/** Primary PPTX font for a CSS generic token on the target platform/locale. */
export declare function getPlatformMappedFontByToken(token: string, ctx: PlatformFontContext, lang?: PlatformFontLang): string | undefined;
/** Primary PPTX font for a collapsed kind (uses canonical generic_name). */
export declare function getPlatformMappedFont(kind: GenericFontKind, ctx: PlatformFontContext, lang?: PlatformFontLang): string;
/** Primary + fallback stack as a CSS-like comma-separated list. */
export declare function getPlatformMappedFontStack(kind: GenericFontKind, ctx: PlatformFontContext, lang?: PlatformFontLang): string;
export declare function isGenericSansToken(token: string): boolean;
export declare function isGenericSerifToken(token: string): boolean;
/** Last generic kind in stack wins (CSS fallback order). */
export declare function detectStackGenericKind(fontFamily: string | undefined): GenericFontKind | undefined;
/** Last generic token name in stack wins (preserves sans-serif vs system-ui distinction). */
export declare function detectStackGenericName(fontFamily: string | undefined): GenericFontName | undefined;
export declare function stackHasNamedFont(fontFamily: string | undefined): boolean;
export declare function replaceGenericFontTokensInStack(fontFamily: string, ctx: PlatformFontContext, lang?: PlatformFontLang): string;
/**
 * Merge specified + computed font stacks and apply platform generic mapping.
 */
export declare function resolveFontFamilyForPlatform(computedFamily: string | undefined, specifiedFamily: string | undefined, ctx: PlatformFontContext, lang?: PlatformFontLang): string;
/** Map Node.js `process.platform` to a PPTX font-mapping target. */
export declare function detectCurrentPlatformTarget(): PlatformTarget;
export declare function buildPlatformFontContext(options?: {
    platform?: PlatformTarget;
}): PlatformFontContext;
export { GENERIC_FONT_OS_MAP, type PlatformFontMappingEntry };
