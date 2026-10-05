/**
 * OOXML self-check & determinism (DH-P0-010).
 *
 * Reopens the generated PPTX buffer as a ZIP and verifies:
 *  - the package can be re-parsed;
 *  - slide count matches the conversion report;
 *  - every mapping record's object_ref name can be found in the slide XML;
 *  - no undisclosed full-page image (screenshot fallback) is present;
 *  - no undisclosed remote (external) relationships exist.
 *
 * The verifier is pure: it takes a Buffer + report and returns a list of
 * diagnostics. It does not throw on findings — callers (or strict mode) decide
 * whether to hard-fail.
 */
import type { DeckHtmlConversionReport } from '../conversion-report';
import { type Diagnostic } from './diagnostics';
export interface OoxmlVerificationResult {
    ok: boolean;
    diagnostics: Diagnostic[];
    /** Slide count discovered in the package (ppt/slides/slideN.xml). */
    packageSlideCount: number;
    /** True when a full-page image was detected on any slide. */
    hasFullPageImage: boolean;
    /** True when any external relationship was found. */
    hasRemoteRelationship: boolean;
}
/**
 * Verify a generated PPTX buffer against its conversion report (DH-P0-010).
 */
export declare function verifyOoxml(data: Buffer, report: DeckHtmlConversionReport): Promise<OoxmlVerificationResult>;
/**
 * Canonicalize a slide XML string for deterministic comparison (DH-P0-010).
 *
 * Strips volatile attributes (timestamps, temporary paths) and normalizes
 * whitespace so two runs over the same input produce equivalent canonical
 * strings. Binary-identical output is a stretch goal; canonical structural
 * equivalence is the minimum bar.
 */
export declare function canonicalizeSlideXml(xml: string): string;
/**
 * Compare two PPTX buffers for canonical OOXML equivalence (DH-P0-010).
 *
 * Returns `true` when every slide XML and rels entry is canonically equivalent
 * between the two runs. Binary identity is not required.
 */
export declare function isCanonicalEquivalent(dataA: Buffer, dataB: Buffer): Promise<boolean>;
