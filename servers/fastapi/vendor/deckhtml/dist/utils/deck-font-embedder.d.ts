/** Directories that may contain TTF/OTF faces for non-FA embedding. */
export declare function resolveDeckFontDirs(): string[];
/** Resolve a typeface name to a local TTF/OTF/EOT buffer + source label. */
export declare function resolveFontBytesForTypeface(typeface: string, fontDirs: string[], packageAssetsDir: string): {
    bytes: Buffer;
    source: string;
} | null;
/**
 * Embed every resolvable typeface referenced by the PPTX into the package.
 * Returns the original buffer when nothing could be embedded.
 */
export declare function embedDeckFonts(pptxData: Buffer): Promise<Buffer>;
