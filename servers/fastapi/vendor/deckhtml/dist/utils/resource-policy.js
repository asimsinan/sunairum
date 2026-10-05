"use strict";
/**
 * Resource loading policy for Playwright and PPTX media validation (DH-P0-007).
 *
 * Caller controls network access and local file roots. Blocked, missing, and
 * escaped resources are reported as structured diagnostics instead of being
 * silently allowed or denied.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.resolveDocumentUrl = resolveDocumentUrl;
exports.normalizeFileUrl = normalizeFileUrl;
exports.isResourceRequestAllowed = isResourceRequestAllowed;
exports.createPlaywrightRouteHandler = createPlaywrightRouteHandler;
exports.setupResourcePolicyOnPage = setupResourcePolicyOnPage;
exports.validateImageUrl = validateImageUrl;
exports.resolveImageSourceForPptx = resolveImageSourceForPptx;
exports.validateDataImageUrl = validateDataImageUrl;
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const url_1 = require("url");
/** Timeout for remote media probe/download used before pptxgenjs embed. */
const REMOTE_MEDIA_TIMEOUT_MS = 30000;
const RULE_REMOTE_BLOCKED = 'DECKHTML_REMOTE_RESOURCE_BLOCKED';
const RULE_FILE_OUTSIDE_ROOTS = 'DECKHTML_FILE_OUTSIDE_ROOTS';
const RULE_SYMLINK_ESCAPE = 'DECKHTML_SYMLINK_ESCAPE';
const RULE_PATH_TRAVERSAL = 'DECKHTML_PATH_TRAVERSAL';
/**
 * Resolve how the HTML document will be loaded.
 */
function resolveDocumentUrl(inputPath) {
    if (fs.existsSync(inputPath)) {
        const absolutePath = path.resolve(inputPath);
        return {
            documentUrl: (0, url_1.pathToFileURL)(absolutePath).href,
            mode: 'local',
        };
    }
    return {
        documentUrl: inputPath,
        mode: 'remote',
    };
}
/**
 * Normalize file:// URLs for stable comparison across platforms.
 */
function normalizeFileUrl(url) {
    try {
        const parsed = new URL(url);
        if (parsed.protocol !== 'file:')
            return url;
        const filePath = (0, url_1.fileURLToPath)(parsed);
        const resolved = path.resolve(filePath);
        return (0, url_1.pathToFileURL)(resolved).href;
    }
    catch {
        return url;
    }
}
function isSymlink(filePath) {
    try {
        return fs.lstatSync(filePath).isSymbolicLink();
    }
    catch {
        return false;
    }
}
function resolveRealPath(filePath) {
    try {
        return fs.realpathSync(filePath);
    }
    catch {
        return null;
    }
}
function containsPathTraversal(filePath) {
    // Reject any '..' segment in the raw path before normalization collapses it.
    // This catches both literal '../' traversal and URL-encoded '%2E%2E'.
    const decoded = decodeURIComponent(filePath);
    const segments = decoded.split(/[/\\]/);
    if (segments.includes('..'))
        return true;
    // Also reject the normalized form escaping above the filesystem root.
    const normalized = path.normalize(decoded);
    const normalizedSegments = normalized.split(/[/\\]/);
    return normalizedSegments.includes('..');
}
function isUnderRoots(filePath, roots, followSymlinks) {
    // Check the raw path for traversal BEFORE path.resolve collapses '..'.
    if (containsPathTraversal(filePath)) {
        return {
            allowed: false,
            reason: {
                rule_id: RULE_PATH_TRAVERSAL,
                message: `Path traversal ('..') is not allowed: ${filePath}`,
            },
        };
    }
    const resolved = path.resolve(filePath);
    if (!followSymlinks && isSymlink(resolved)) {
        return {
            allowed: false,
            reason: {
                rule_id: RULE_SYMLINK_ESCAPE,
                message: `Symlink rejected by resource policy: ${filePath}`,
                recovery: 'Set followSymlinks: true or replace the symlink with a real file.',
            },
        };
    }
    // When followSymlinks is true, resolve to the real target before root check.
    const checkedPath = followSymlinks ? (resolveRealPath(resolved) ?? resolved) : resolved;
    if (roots.length === 0) {
        return { allowed: false, reason: { rule_id: RULE_FILE_OUTSIDE_ROOTS, message: `No allowed roots configured; file:// subresource rejected: ${filePath}` } };
    }
    for (const root of roots) {
        const absRoot = path.resolve(root);
        const rel = path.relative(absRoot, checkedPath);
        if (rel && !rel.startsWith('..') && !path.isAbsolute(rel)) {
            return { allowed: true };
        }
        // Also allow the root itself.
        if (checkedPath === absRoot)
            return { allowed: true };
    }
    return {
        allowed: false,
        reason: {
            rule_id: RULE_FILE_OUTSIDE_ROOTS,
            message: `File outside allowed roots: ${filePath}`,
            recovery: `Add the file's directory to resourcePolicy.allowedRoots.`,
        },
    };
}
function remoteAllowedForKind(kind, policy) {
    if (kind === 'font')
        return policy.allowRemoteFonts;
    if (kind === 'image')
        return policy.allowRemoteImages;
    if (kind === 'script')
        return policy.allowRemoteScripts;
    if (kind === 'style')
        return policy.allowRemoteStyles;
    return policy.network === 'allow';
}
function classifyRoute(route) {
    const type = route.request().resourceType();
    if (type === 'font')
        return 'font';
    if (type === 'image')
        return 'image';
    if (type === 'script')
        return 'script';
    if (type === 'stylesheet')
        return 'style';
    // Fallback by URL extension for data/manifest etc.
    const url = route.request().url().toLowerCase();
    if (/\.(woff2?|ttf|otf|eot)(\?|$)/.test(url))
        return 'font';
    if (/\.(png|jpe?g|gif|webp|svg|bmp|ico)(\?|$)/.test(url))
        return 'image';
    if (/\.(js|mjs)(\?|$)/.test(url))
        return 'script';
    if (/\.css(\?|$)/.test(url))
        return 'style';
    return 'other';
}
function normalizePolicy(raw, mode, documentDir) {
    const network = raw?.network ?? 'allow';
    const allowedRoots = raw?.allowedRoots ?? (documentDir ? [documentDir] : []);
    const followSymlinks = raw?.followSymlinks ?? false;
    return {
        network,
        allowedRoots,
        followSymlinks,
        allowRemoteFonts: raw?.allowRemoteFonts ?? network === 'allow',
        allowRemoteImages: raw?.allowRemoteImages ?? network === 'allow',
        allowRemoteScripts: raw?.allowRemoteScripts ?? network === 'allow',
        allowRemoteStyles: raw?.allowRemoteStyles ?? network === 'allow',
    };
}
/**
 * Whether a subresource request should be allowed under the active policy.
 * Pushes a diagnostic for every denial.
 */
function isResourceRequestAllowed(requestUrl, documentUrl, policy, diagnostics, kind) {
    const lower = requestUrl.toLowerCase();
    if (lower.startsWith('data:') || lower.startsWith('blob:')) {
        return true;
    }
    if (lower.startsWith('ws://') || lower.startsWith('wss://')) {
        if (policy.network === 'deny') {
            diagnostics.push({
                rule_id: RULE_REMOTE_BLOCKED,
                severity: 'error',
                url: requestUrl,
                message: 'WebSocket requests are blocked by the active resource policy (network: deny).',
                recovery: 'Set resourcePolicy.network: "allow" to permit WebSocket.',
            });
            return false;
        }
        return true;
    }
    if (lower.startsWith('http://') || lower.startsWith('https://')) {
        if (!remoteAllowedForKind(kind, policy)) {
            diagnostics.push({
                rule_id: RULE_REMOTE_BLOCKED,
                severity: 'error',
                url: requestUrl,
                message: `Remote ${kind} resource is not allowed by the active resource policy.`,
                recovery: `Set resourcePolicy.allowRemote${kind[0].toUpperCase() + kind.slice(1)}: true or resourcePolicy.network: "allow".`,
            });
            return false;
        }
        return true;
    }
    if (lower.startsWith('file:')) {
        // The document itself is always allowed.
        if (normalizeFileUrl(requestUrl) === normalizeFileUrl(documentUrl)) {
            return true;
        }
        // Check the raw URL for traversal BEFORE fileURLToPath collapses '..'.
        // URL parsing normalizes '..' segments, so we must inspect the original string.
        const rawDecoded = (() => {
            try {
                return decodeURIComponent(requestUrl);
            }
            catch {
                return requestUrl;
            }
        })();
        if (/(^|[\/\\])\.\.([\/\\]|$)/.test(rawDecoded) || /%2e%2e/i.test(requestUrl)) {
            diagnostics.push({
                rule_id: RULE_PATH_TRAVERSAL,
                severity: 'error',
                url: requestUrl,
                message: `Path traversal ('..') is not allowed: ${requestUrl}`,
            });
            return false;
        }
        let filePath;
        try {
            filePath = (0, url_1.fileURLToPath)(requestUrl);
        }
        catch {
            diagnostics.push({
                rule_id: RULE_PATH_TRAVERSAL,
                severity: 'error',
                url: requestUrl,
                message: `Unparsable file:// URL rejected: ${requestUrl}`,
            });
            return false;
        }
        const result = isUnderRoots(filePath, policy.allowedRoots, policy.followSymlinks);
        if (!result.allowed && result.reason) {
            diagnostics.push({
                rule_id: result.reason.rule_id,
                severity: 'error',
                url: requestUrl,
                message: result.reason.message,
                recovery: result.reason.recovery,
            });
            return false;
        }
        return true;
    }
    diagnostics.push({
        rule_id: RULE_REMOTE_BLOCKED,
        severity: 'warning',
        url: requestUrl,
        message: `Unsupported resource protocol rejected: ${requestUrl}`,
    });
    return false;
}
/**
 * Playwright route handler enforcing the resource policy.
 */
function createPlaywrightRouteHandler(documentUrl, policy, diagnostics) {
    return async (route) => {
        const requestUrl = route.request().url();
        const kind = classifyRoute(route);
        if (isResourceRequestAllowed(requestUrl, documentUrl, policy, diagnostics, kind)) {
            await route.continue();
            return;
        }
        await route.abort('blockedbyclient');
    };
}
/**
 * Register resource policy route on a Playwright page (call before goto).
 */
async function setupResourcePolicyOnPage(page, inputPath, options) {
    const info = resolveDocumentUrl(inputPath);
    const documentDir = info.mode === 'local'
        ? path.dirname((0, url_1.fileURLToPath)(info.documentUrl))
        : null;
    // Explicit policy takes precedence; otherwise map the legacy shorthand.
    let policy;
    if (options?.policy) {
        policy = options.policy;
    }
    else if (options?.allowLocalResources) {
        // Legacy loose mode: allow all file:// subresources and all remote.
        policy = { network: 'allow', allowedRoots: [], followSymlinks: true };
    }
    else {
        // Legacy strict-local mode: block file:// subresources except the document.
        policy = { network: 'allow', allowedRoots: [], followSymlinks: false };
    }
    const normalized = normalizePolicy(policy, info.mode, documentDir);
    const diagnostics = options?.diagnostics ?? [];
    // When policy allows everything (loose legacy mode with no roots and network allow),
    // skip route registration to preserve prior performance and behavior.
    const isLoose = !options?.policy &&
        options?.allowLocalResources === true;
    if (isLoose) {
        return info;
    }
    await page.route('**/*', createPlaywrightRouteHandler(info.documentUrl, normalized, diagnostics));
    return info;
}
/**
 * Validate that a URL returns a valid image (not 404 HTML, etc.)
 */
async function validateImageUrl(url) {
    return (await resolveImageSourceForPptx(url)) !== null;
}
/**
 * Resolve an image URL for pptxgenjs.
 * Keeps the original http:// or https:// URL (no protocol upgrade).
 * Call ensurePptxgenAllowsHttp() before write so pptxgenjs can fetch http://.
 */
async function resolveImageSourceForPptx(url) {
    if (!url)
        return null;
    if (url.startsWith('data:')) {
        return validateDataImageUrl(url) ? { kind: 'data', data: url } : null;
    }
    try {
        const response = await fetch(url, {
            method: 'GET',
            redirect: 'follow',
            signal: AbortSignal.timeout(REMOTE_MEDIA_TIMEOUT_MS),
        });
        if (!response.ok)
            return null;
        const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
        if (!contentType.startsWith('image/'))
            return null;
        const buffer = Buffer.from(await response.arrayBuffer());
        const start = buffer.subarray(0, Math.min(50, buffer.length)).toString('utf8');
        if (/^\s*<(!DOCTYPE|html|[\w-]+)/i.test(start))
            return null;
        // Pass through original URL (http:// or https://). pptxgenjs downloads it.
        return { kind: 'path', path: url };
    }
    catch {
        return null;
    }
}
/**
 * Validate inline data:image/... URLs.
 */
function validateDataImageUrl(dataUrl) {
    if (!dataUrl.startsWith('data:image/'))
        return false;
    const comma = dataUrl.indexOf(',');
    if (comma < 0)
        return false;
    const payload = dataUrl.slice(comma + 1).trim();
    if (payload.length < 16)
        return false;
    if (dataUrl.includes(';base64,')) {
        return /^[A-Za-z0-9+/=\s]+$/.test(payload) && payload.replace(/\s/g, '').length >= 16;
    }
    return payload.length >= 16;
}
