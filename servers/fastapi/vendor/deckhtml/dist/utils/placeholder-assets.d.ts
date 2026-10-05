/**
 * Placeholder images for unavailable media resources.
 *
 * Resolution order (per media type):
 * 1. Custom directory — PLACEHOLDER_ASSETS_DIR env var, if set
 * 2. Package defaults — assets/placeholders/ at package root
 * 3. Built-in embedded PNGs — #eeeeee defaults shipped in code
 */
export type PlaceholderMediaType = 'image' | 'video' | 'audio';
/** Package-bundled PNG directory (user-replaceable without rebuild). */
export declare function resolveDefaultPlaceholderAssetsDir(): string;
/**
 * Directories to try, in order. Custom dir first when configured.
 */
export declare function resolvePlaceholderSearchDirs(): string[];
export declare function getPlaceholderForMediaType(type: PlaceholderMediaType): string;
