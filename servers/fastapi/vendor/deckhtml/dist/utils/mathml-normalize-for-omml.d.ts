/**
 * KaTeX wraps content in <semantics> (annotation stripped elsewhere). mathml2omml
 * logs "Type not supported" for semantics/annotation; unwrap to the visible row.
 */
export declare function unwrapMathMlSemantics(mathml: string): string;
/**
 * KaTeX emits `\nabla` / `\partial` as `<mi mathvariant="normal">`. mathml2omml then
 * attaches `m:sty m:val="undefined"` and PowerPoint may render U+2207 as italic 𝛻 (U+1D6FB).
 */
export declare function normalizeKatexOperatorMiToMo(mathml: string): string;
/**
 * When every row of an `<mtable>` is a single cell containing `lhs = rhs`, split into two
 * columns (`columnalign="right left"`) so mathml2omml emits an OMML matrix with aligned `=`.
 */
export declare function splitSingleColumnMtableRowsAtEquals(mathml: string): string;
export declare function normalizeFenceMoDelimitersForOmml(mathml: string): string;
/**
 * MathJax/KaTeX often emit accents via `<mover>` without `accent="true"`.
 * Without that flag, mathml2omml emits `<m:limUpp>` and PowerPoint floats the
 * mark far above the base (classic `\hat{d}` / `\dot{r}` bug).
 *
 * Mark common single-glyph overscripts as accents and normalize a few chars so
 * mathml2omml emits `<m:acc>` instead of limUpp.
 */
export declare function normalizeMoverDotAccentForOmml(mathml: string): string;
/**
 * Aligned/tabular MathML may emit `<mo>&</mo>` or `<malignmark/>` as column alignment
 * markers inside `<mtable>`. mathml2omml passes them through as a visible "&".
 */
export declare function stripMathMlTableAlignmentMarkers(mathml: string): string;
/**
 * Normalize MathML before mathml2omml so n-ary integrals keep a single integrand.
 */
export declare function normalizeMathMlNaryIntegrandForOmml(mathml: string): string;
