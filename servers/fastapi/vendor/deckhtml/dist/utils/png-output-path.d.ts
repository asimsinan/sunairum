/**
 * Build output PNG path(s) from the `-o` base path.
 *
 * - 1 page: same as base (ensures `.png`)
 * - N pages: insert a 1-based index before the extension
 *   (width = digit count of N: 1–9 → `1`…`9`, 10–99 → `01`…`99`, …)
 */
export declare function buildPngOutputPaths(basePath: string, count: number): string[];
