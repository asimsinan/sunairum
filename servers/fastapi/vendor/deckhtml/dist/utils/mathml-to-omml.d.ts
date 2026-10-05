/**
 * Convert MathML to Office Math Markup Language (OMML) via mathml2omml (LGPL-3.0).
 */
export type MathmlToOmmlResult = {
    ok: true;
    omml: string;
} | {
    ok: false;
    error: string;
};
/**
 * Convert a MathML string (typically full `<math>…</math>`) to OMML (`<m:oMath>…</m:oMath>`).
 */
export declare function convertMathmlToOmml(mathml: string): Promise<MathmlToOmmlResult>;
