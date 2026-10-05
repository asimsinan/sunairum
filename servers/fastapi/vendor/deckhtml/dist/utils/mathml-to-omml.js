"use strict";
/**
 * Convert MathML to Office Math Markup Language (OMML) via mathml2omml (LGPL-3.0).
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.convertMathmlToOmml = convertMathmlToOmml;
const mathml_normalize_for_omml_1 = require("./mathml-normalize-for-omml");
const omml_fence_delimiter_1 = require("./omml-fence-delimiter");
let mml2ommlLoader = null;
function loadMml2Omml() {
    if (!mml2ommlLoader) {
        mml2ommlLoader = import('mathml2omml').then((mod) => mod.mml2omml);
    }
    return mml2ommlLoader;
}
/**
 * Convert a MathML string (typically full `<math>…</math>`) to OMML (`<m:oMath>…</m:oMath>`).
 */
async function convertMathmlToOmml(mathml) {
    const trimmed = mathml?.trim();
    if (!trimmed) {
        return { ok: false, error: 'Empty MathML' };
    }
    try {
        const mml2omml = await loadMml2Omml();
        const normalized = (0, mathml_normalize_for_omml_1.normalizeMathMlNaryIntegrandForOmml)((0, mathml_normalize_for_omml_1.unwrapMathMlSemantics)(trimmed));
        const rawOmml = mml2omml(normalized);
        const omml = (0, omml_fence_delimiter_1.fixOmmlFenceDelimiterRuns)(rawOmml);
        if (!omml || !/<m:oMath\b/i.test(omml)) {
            return { ok: false, error: 'Converter did not produce m:oMath' };
        }
        return { ok: true, omml };
    }
    catch (e) {
        const message = e instanceof Error ? e.message : String(e);
        return { ok: false, error: message };
    }
}
