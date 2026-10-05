"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ExitCode = void 0;
exports.outputError = outputError;
const api_error_1 = require("./api-error");
exports.ExitCode = {
    SUCCESS: 0,
    ERROR: 1,
    USAGE_ERROR: 2,
};
function outputError(error, jsonMode, code = 'ERROR', options = {}) {
    const apiDetails = (0, api_error_1.toApiErrorDetails)(error, options.apiBase);
    if (jsonMode) {
        console.error(JSON.stringify({
            ok: false,
            error: {
                code,
                message: error.message,
                ...(apiDetails
                    ? {
                        requestUrl: apiDetails.requestUrl,
                        statusCode: apiDetails.statusCode,
                        requestId: apiDetails.requestId,
                        response: apiDetails.responseData,
                    }
                    : {}),
            },
        }));
        return;
    }
    console.error(`Error: ${error.message}`);
    if (apiDetails) {
        for (const line of (0, api_error_1.formatApiErrorLines)(apiDetails, options.apiBase)) {
            console.error(line);
        }
    }
}
