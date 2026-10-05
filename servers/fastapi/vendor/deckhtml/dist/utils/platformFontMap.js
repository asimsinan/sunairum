"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.GENERIC_FONT_OS_MAP = exports.DEFAULT_PLATFORM_TARGET = void 0;
exports.genericNameFromToken = genericNameFromToken;
exports.genericKindFromToken = genericKindFromToken;
exports.isGenericFontToken = isGenericFontToken;
exports.isPlatformFontContextActive = isPlatformFontContextActive;
exports.getPlatformFontMappingByName = getPlatformFontMappingByName;
exports.getPlatformFontMapping = getPlatformFontMapping;
exports.getPlatformMappedFontByToken = getPlatformMappedFontByToken;
exports.getPlatformMappedFont = getPlatformMappedFont;
exports.getPlatformMappedFontStack = getPlatformMappedFontStack;
exports.isGenericSansToken = isGenericSansToken;
exports.isGenericSerifToken = isGenericSerifToken;
exports.detectStackGenericKind = detectStackGenericKind;
exports.detectStackGenericName = detectStackGenericName;
exports.stackHasNamedFont = stackHasNamedFont;
exports.replaceGenericFontTokensInStack = replaceGenericFontTokensInStack;
exports.resolveFontFamilyForPlatform = resolveFontFamilyForPlatform;
exports.detectCurrentPlatformTarget = detectCurrentPlatformTarget;
exports.buildPlatformFontContext = buildPlatformFontContext;
/**
 * Platform / language generic font mapping for PPTX conversion.
 * Maps CSS generic font-family keywords to OS-specific fonts.
 *
 * Data: platformFontMap.data.ts (synced from @deckflow/html2pptx)
 */
const chineseFonts_1 = require("./chineseFonts");
const platformFontMap_data_1 = require("./platformFontMap.data");
Object.defineProperty(exports, "GENERIC_FONT_OS_MAP", { enumerable: true, get: function () { return platformFontMap_data_1.GENERIC_FONT_OS_MAP; } });
/** Default platform when callers omit `platform` (programmatic API). */
exports.DEFAULT_PLATFORM_TARGET = 'win';
/** CSS token (incl. vendor aliases) → CSV generic_name key. */
const TOKEN_TO_GENERIC_NAME = {
    serif: 'serif',
    'ui-serif': 'ui-serif',
    'sans-serif': 'sans-serif',
    'system-ui': 'system-ui',
    'ui-sans-serif': 'ui-sans-serif',
    '-apple-system': 'system-ui',
    blinkmacsystemfont: 'system-ui',
    monospace: 'monospace',
    'ui-monospace': 'ui-monospace',
    cursive: 'cursive',
    fantasy: 'fantasy',
    math: 'math',
};
/** generic_name → collapsed kind for applyPlatformScriptSlots. */
const GENERIC_NAME_TO_KIND = {
    serif: 'serif',
    'ui-serif': 'serif',
    'sans-serif': 'sans',
    'system-ui': 'sans',
    'ui-sans-serif': 'sans',
    monospace: 'monospace',
    'ui-monospace': 'monospace',
    cursive: 'cursive',
    fantasy: 'fantasy',
    math: 'math',
};
/** Default generic_name when resolving by collapsed kind only. */
const KIND_CANONICAL_NAME = {
    serif: 'serif',
    sans: 'sans-serif',
    monospace: 'monospace',
    cursive: 'cursive',
    fantasy: 'fantasy',
    math: 'math',
};
const ALL_GENERIC_TOKENS = new Set(Object.keys(TOKEN_TO_GENERIC_NAME));
function unquoteToken(token) {
    return token.trim().replace(/^['"]|['"]$/g, '');
}
function tokenCore(token) {
    return unquoteToken(token).toLowerCase();
}
function genericNameFromToken(token) {
    return TOKEN_TO_GENERIC_NAME[tokenCore(token)];
}
function genericKindFromToken(token) {
    const name = genericNameFromToken(token);
    return name ? GENERIC_NAME_TO_KIND[name] : undefined;
}
function isGenericFontToken(token) {
    return ALL_GENERIC_TOKENS.has(tokenCore(token));
}
function isPlatformFontContextActive(ctx) {
    return ctx?.platform != null;
}
function getPlatformFontMappingByName(genericName, ctx, lang = 'latin') {
    return platformFontMap_data_1.GENERIC_FONT_OS_MAP[ctx.platform][lang][genericName];
}
function getPlatformFontMapping(kind, ctx, lang = 'latin') {
    return getPlatformFontMappingByName(KIND_CANONICAL_NAME[kind], ctx, lang);
}
/** Primary PPTX font for a CSS generic token on the target platform/locale. */
function getPlatformMappedFontByToken(token, ctx, lang = 'latin') {
    const name = genericNameFromToken(token);
    if (!name)
        return undefined;
    return getPlatformFontMappingByName(name, ctx, lang).primary;
}
/** Primary PPTX font for a collapsed kind (uses canonical generic_name). */
function getPlatformMappedFont(kind, ctx, lang = 'latin') {
    return getPlatformFontMapping(kind, ctx, lang).primary;
}
/** Primary + fallback stack as a CSS-like comma-separated list. */
function getPlatformMappedFontStack(kind, ctx, lang = 'latin') {
    const { primary, fallbacks } = getPlatformFontMapping(kind, ctx, lang);
    return [primary, ...fallbacks].join(', ');
}
function isGenericSansToken(token) {
    return genericKindFromToken(token) === 'sans';
}
function isGenericSerifToken(token) {
    return genericKindFromToken(token) === 'serif';
}
/** Last generic kind in stack wins (CSS fallback order). */
function detectStackGenericKind(fontFamily) {
    if (!fontFamily)
        return undefined;
    let last;
    for (const tok of (0, chineseFonts_1.splitFontStack)(fontFamily)) {
        const kind = genericKindFromToken(tok);
        if (kind)
            last = kind;
    }
    return last;
}
/** Last generic token name in stack wins (preserves sans-serif vs system-ui distinction). */
function detectStackGenericName(fontFamily) {
    if (!fontFamily)
        return undefined;
    let last;
    for (const tok of (0, chineseFonts_1.splitFontStack)(fontFamily)) {
        const name = genericNameFromToken(tok);
        if (name)
            last = name;
    }
    return last;
}
function stackHasNamedFont(fontFamily) {
    if (!fontFamily)
        return false;
    return (0, chineseFonts_1.splitFontStack)(fontFamily).some((tok) => {
        const core = tokenCore(tok);
        return core && !ALL_GENERIC_TOKENS.has(core);
    });
}
function replaceGenericFontTokensInStack(fontFamily, ctx, lang = 'latin') {
    const tokens = (0, chineseFonts_1.splitFontStack)(fontFamily);
    if (!tokens.length)
        return fontFamily;
    let changed = false;
    const replaced = tokens.map((tok) => {
        const mapped = getPlatformMappedFontByToken(tok, ctx, lang);
        if (mapped) {
            changed = true;
            return mapped;
        }
        return tok;
    });
    return changed ? replaced.join(', ') : fontFamily;
}
/**
 * Merge specified + computed font stacks and apply platform generic mapping.
 */
function resolveFontFamilyForPlatform(computedFamily, specifiedFamily, ctx, lang = 'latin') {
    const specifiedName = detectStackGenericName(specifiedFamily);
    const computedName = detectStackGenericName(computedFamily);
    const specifiedKind = specifiedName ? GENERIC_NAME_TO_KIND[specifiedName] : undefined;
    const computedKind = computedName ? GENERIC_NAME_TO_KIND[computedName] : undefined;
    if (specifiedName && specifiedFamily && !stackHasNamedFont(specifiedFamily)) {
        return getPlatformFontMappingByName(specifiedName, ctx, lang).primary;
    }
    const base = computedFamily ?? specifiedFamily ?? '';
    if (!base) {
        const fallbackName = specifiedName ??
            computedName ??
            KIND_CANONICAL_NAME[specifiedKind ?? computedKind ?? 'sans'];
        return getPlatformFontMappingByName(fallbackName, ctx, lang).primary;
    }
    let resolved = replaceGenericFontTokensInStack(base, ctx, lang);
    if (specifiedName &&
        specifiedFamily &&
        stackHasNamedFont(specifiedFamily) &&
        !computedName) {
        resolved = replaceGenericFontTokensInStack(specifiedFamily, ctx, lang);
    }
    return resolved;
}
/** Map Node.js `process.platform` to a PPTX font-mapping target. */
function detectCurrentPlatformTarget() {
    switch (process.platform) {
        case 'win32':
            return 'win';
        case 'darwin':
            return 'mac';
        case 'linux':
            return 'linux';
        default:
            return exports.DEFAULT_PLATFORM_TARGET;
    }
}
function buildPlatformFontContext(options = {}) {
    return { platform: options.platform ?? exports.DEFAULT_PLATFORM_TARGET };
}
