"use strict";
/**
 * Placeholder images for unavailable media resources.
 *
 * Resolution order (per media type):
 * 1. Custom directory — PLACEHOLDER_ASSETS_DIR env var, if set
 * 2. Package defaults — assets/placeholders/ at package root
 * 3. Built-in embedded PNGs — #eeeeee defaults shipped in code
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.resolveDefaultPlaceholderAssetsDir = resolveDefaultPlaceholderAssetsDir;
exports.resolvePlaceholderSearchDirs = resolvePlaceholderSearchDirs;
exports.getPlaceholderForMediaType = getPlaceholderForMediaType;
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
const placeholder_defaults_1 = require("./placeholder-defaults");
const PLACEHOLDER_FILENAMES = {
    image: 'image-unavailable.png',
    video: 'video-unavailable.png',
    audio: 'audio-unavailable.png',
};
const dataUrlCache = new Map();
/** Package-bundled PNG directory (user-replaceable without rebuild). */
function resolveDefaultPlaceholderAssetsDir() {
    return node_path_1.default.join(__dirname, '..', '..', 'assets', 'placeholders');
}
/**
 * Directories to try, in order. Custom dir first when configured.
 */
function resolvePlaceholderSearchDirs() {
    const dirs = [];
    if (process.env.PLACEHOLDER_ASSETS_DIR) {
        dirs.push(node_path_1.default.resolve(process.env.PLACEHOLDER_ASSETS_DIR));
    }
    const defaultDir = resolveDefaultPlaceholderAssetsDir();
    if (!dirs.includes(defaultDir)) {
        dirs.push(defaultDir);
    }
    return dirs;
}
function tryLoadPngFromDir(dir, type) {
    const filePath = node_path_1.default.join(dir, PLACEHOLDER_FILENAMES[type]);
    try {
        if (!node_fs_1.default.existsSync(filePath))
            return null;
        const buffer = node_fs_1.default.readFileSync(filePath);
        return `data:image/png;base64,${buffer.toString('base64')}`;
    }
    catch {
        return null;
    }
}
function loadPlaceholderDataUrl(type) {
    const cached = dataUrlCache.get(type);
    if (cached)
        return cached;
    for (const dir of resolvePlaceholderSearchDirs()) {
        const fromFile = tryLoadPngFromDir(dir, type);
        if (fromFile) {
            dataUrlCache.set(type, fromFile);
            return fromFile;
        }
    }
    const embedded = placeholder_defaults_1.EMBEDDED_DEFAULT_PLACEHOLDERS[type];
    dataUrlCache.set(type, embedded);
    return embedded;
}
function getPlaceholderForMediaType(type) {
    return loadPlaceholderDataUrl(type);
}
