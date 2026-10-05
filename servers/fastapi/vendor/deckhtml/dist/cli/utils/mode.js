"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.resolveMode = resolveMode;
exports.validateCloudOnlyFlags = validateCloudOnlyFlags;
function resolveMode(requested, hasCredentials) {
    if (requested === 'local')
        return 'local';
    // Cloud mode no longer requires credentials up front: the SDK always sends
    // X-Auth-UUID and the server treats UUID-only requests as rate-limited
    // guests. A 401 response triggers the login / API-key guidance flow.
    if (requested === 'cloud')
        return 'cloud';
    return hasCredentials ? 'cloud' : 'local';
}
/**
 * Previously blocked `--embed-fonts` in local mode. Local conversion embeds
 * deck fonts via `embedDeckFonts` unconditionally, so the flag is allowed
 * (and treated as a no-op request for the cloud library path).
 */
function validateCloudOnlyFlags(_mode, _flags) {
    // no-op: --embed-fonts is valid in local and cloud
}
