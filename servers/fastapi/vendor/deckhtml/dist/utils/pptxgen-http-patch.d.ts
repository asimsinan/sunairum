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
/**
 * Enable http:// media downloads inside pptxgenjs (images and any other
 * remote rel.path it embeds). Idempotent.
 */
export declare function ensurePptxgenAllowsHttp(): void;
