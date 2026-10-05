#!/usr/bin/env ts-node
/**
 * Convert all HTML files in a benchmark/done subdirectory (sorted by name)
 * into a single out.pptx in that directory.
 *
 * Usage:
 *   ./src/bin/batch-done-convert.ts [dir] [local] [1280x720]
 *
 * Examples:
 *   ./src/bin/batch-done-convert.ts                    # all dirs under benchmark/done
 *   ./src/bin/batch-done-convert.ts local              # all dirs, allow file://
 *   ./src/bin/batch-done-convert.ts benchmark/done/0001
 *   ./src/bin/batch-done-convert.ts 0001 local
 */
export {};
