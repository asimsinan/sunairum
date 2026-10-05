"use strict";
/**
 * pptxgenjs (Node) downloads remote media with `https.get` for any URL that
 * starts with "http", so plain `http://` throws ERR_INVALID_PROTOCOL.
 *
 * Patch the real `node:https` module so http:// uses `http.get` and https://
 * stays on `https.get`. Never upgrade http → https.
 *
 * Uses createRequire so we mutate the cached module exports (not a TS
 * `import *` namespace object, which only exposes getters).
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.ensurePptxgenAllowsHttp = ensurePptxgenAllowsHttp;
const node_module_1 = require("node:module");
const nodeRequire = (0, node_module_1.createRequire)(__filename);
const http = nodeRequire('node:http');
const https = nodeRequire('node:https');
let patched = false;
function requestUrlString(target) {
    if (typeof target === 'string')
        return target;
    if (target instanceof URL)
        return target.href;
    if (target && typeof target === 'object') {
        const opts = target;
        if (typeof opts.href === 'string')
            return opts.href;
        if (typeof opts.protocol === 'string') {
            const host = opts.host ?? opts.hostname ?? '';
            const pathPart = opts.path ?? `${opts.pathname ?? ''}${opts.search ?? ''}`;
            return `${opts.protocol}//${host}${pathPart}`;
        }
    }
    return '';
}
/**
 * Enable http:// media downloads inside pptxgenjs (images and any other
 * remote rel.path it embeds). Idempotent.
 */
function ensurePptxgenAllowsHttp() {
    if (patched)
        return;
    patched = true;
    const originalGet = https.get.bind(https);
    const routedGet = ((...args) => {
        const urlStr = requestUrlString(args[0]);
        if (urlStr.startsWith('http://')) {
            return http.get(...args);
        }
        return originalGet(...args);
    });
    https.get = routedGet;
}
