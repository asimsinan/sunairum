import { DEFAULT_VIEWPORT_HEIGHT, DEFAULT_VIEWPORT_WIDTH } from '../../utils/viewport';
export { DEFAULT_VIEWPORT_WIDTH, DEFAULT_VIEWPORT_HEIGHT };
export declare function parseWidth(value: string): number;
/**
 * Resolve viewport dimensions (16:9).
 * When widthOverride is set, height is scaled proportionally.
 * When widthOverride is omitted and required is false, returns undefined so
 * the converter can auto-detect from HTML meta / CSS / SVG.
 */
export declare function resolveViewport(widthOverride?: string, required?: boolean): {
    width: number;
    height: number;
} | undefined;
