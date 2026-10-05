"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DEFAULT_VIEWPORT_HEIGHT = exports.DEFAULT_VIEWPORT_WIDTH = void 0;
exports.parseWidth = parseWidth;
exports.resolveViewport = resolveViewport;
const viewport_1 = require("../../utils/viewport");
Object.defineProperty(exports, "DEFAULT_VIEWPORT_HEIGHT", { enumerable: true, get: function () { return viewport_1.DEFAULT_VIEWPORT_HEIGHT; } });
Object.defineProperty(exports, "DEFAULT_VIEWPORT_WIDTH", { enumerable: true, get: function () { return viewport_1.DEFAULT_VIEWPORT_WIDTH; } });
function parseWidth(value) {
    const width = parseInt(value, 10);
    if (!Number.isFinite(width) || width <= 0) {
        throw new Error(`Invalid --width: ${value}. Must be a positive integer.`);
    }
    return width;
}
/**
 * Resolve viewport dimensions (16:9).
 * When widthOverride is set, height is scaled proportionally.
 * When widthOverride is omitted and required is false, returns undefined so
 * the converter can auto-detect from HTML meta / CSS / SVG.
 */
function resolveViewport(widthOverride, required = true) {
    if (widthOverride !== undefined) {
        const width = parseWidth(widthOverride);
        const height = Math.round((width * viewport_1.DEFAULT_VIEWPORT_HEIGHT) / viewport_1.DEFAULT_VIEWPORT_WIDTH);
        return { width, height };
    }
    if (!required) {
        return undefined;
    }
    return {
        width: viewport_1.DEFAULT_VIEWPORT_WIDTH,
        height: viewport_1.DEFAULT_VIEWPORT_HEIGHT,
    };
}
