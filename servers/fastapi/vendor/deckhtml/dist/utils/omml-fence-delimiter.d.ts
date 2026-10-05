/**
 * mathml2omml emits fence operators (e.g. KaTeX `\begin{cases}` → `<mo fence="true">{</mo>`)
 * as plain `<m:r><m:t>{</m:t></m:r>`. PowerPoint needs `<m:d>` with `<m:begChr>` for stretchy braces.
 */
/**
 * Replace plain delimiter runs with stretchy `<m:d>` fences (cases matrices and `\left/\right`).
 */
export declare function fixOmmlFenceDelimiterRuns(omml: string): string;
