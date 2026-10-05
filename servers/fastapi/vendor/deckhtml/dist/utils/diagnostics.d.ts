/**
 * Structured conversion diagnostics (DH-P0-009).
 *
 * A Diagnostic is the stable, machine-readable form of every issue deckhtml
 * surfaces during a conversion. rule_id stays semantically stable across patch
 * versions so callers can branch on it.
 */
export type DiagnosticSeverity = 'error' | 'warning' | 'info';
export interface Diagnostic {
    rule_id: string;
    severity: DiagnosticSeverity;
    /** Slide id or 1-based index, when applicable. */
    slide_id?: string | null;
    /** Caller-declared element identity, when applicable. */
    element_id?: string | null;
    message: string;
    /** Suggested remediation. */
    recovery?: string | null;
}
/** Minimum rule families deckhtml guarantees (DH-P0-009). */
export declare const RULE_IDS: {
    readonly IDENTITY_MISSING: "DECKHTML_IDENTITY_MISSING";
    readonly IDENTITY_DUPLICATE: "DECKHTML_IDENTITY_DUPLICATE";
    readonly IDENTITY_NOT_EXPORTED: "DECKHTML_IDENTITY_NOT_EXPORTED";
    readonly KIND_AMBIGUOUS: "DECKHTML_KIND_AMBIGUOUS";
    readonly KIND_UNSUPPORTED: "DECKHTML_KIND_UNSUPPORTED";
    readonly STYLE_UNSUPPORTED: "DECKHTML_STYLE_UNSUPPORTED";
    readonly RESOURCE_REMOTE_BLOCKED: "DECKHTML_REMOTE_RESOURCE_BLOCKED";
    readonly RESOURCE_MISSING: "DECKHTML_RESOURCE_MISSING";
    readonly RESOURCE_ESCAPED: "DECKHTML_RESOURCE_ESCAPED";
    readonly BROWSER_UNAVAILABLE: "DECKHTML_BROWSER_UNAVAILABLE";
    readonly BROWSER_CRASHED: "DECKHTML_BROWSER_CRASHED";
    readonly BROWSER_TIMEOUT: "DECKHTML_BROWSER_TIMEOUT";
    readonly FONT_MISSING: "DECKHTML_FONT_MISSING";
    readonly FONT_FALLBACK: "DECKHTML_FONT_FALLBACK";
    readonly RASTER_FALLBACK: "DECKHTML_RASTER_FALLBACK";
    readonly GEOMETRY_INVALID: "DECKHTML_GEOMETRY_INVALID";
    readonly GEOMETRY_UNSTABLE: "DECKHTML_GEOMETRY_UNSTABLE";
    readonly OOXML_WRITE_FAILURE: "DECKHTML_OOXML_WRITE_FAILURE";
    readonly OOXML_REOPEN_FAILURE: "DECKHTML_OOXML_REOPEN_FAILURE";
    readonly MAPPING_CLOSURE_FAILURE: "DECKHTML_MAPPING_CLOSURE_FAILURE";
    readonly OUTPUT_EXISTS: "DECKHTML_OUTPUT_EXISTS";
    readonly ANIMATION_UNMAPPED: "DECKHTML_ANIMATION_UNMAPPED";
    readonly IFRAME_INSPECT_FAILED: "DECKHTML_IFRAME_INSPECT_FAILED";
    readonly IFRAME_NESTED_TOO_DEEP: "DECKHTML_IFRAME_NESTED_TOO_DEEP";
    readonly IFRAME_PARENT_COUPLED: "DECKHTML_IFRAME_PARENT_COUPLED";
    readonly LAYOUT_FAITHFUL_UNSUPPORTED: "DECKHTML_LAYOUT_FAITHFUL_UNSUPPORTED";
    readonly LAYOUT_FAITHFUL_FONT: "DECKHTML_LAYOUT_FAITHFUL_FONT";
    readonly LAYOUT_FAITHFUL_FALLBACK: "DECKHTML_LAYOUT_FAITHFUL_FALLBACK";
    readonly LAYOUT_FAITHFUL_SHRINK: "DECKHTML_LAYOUT_FAITHFUL_SHRINK";
};
/**
 * Error thrown for hard failures. Carries a primary Diagnostic plus optional
 * additional diagnostics so callers can still harvest structured info from a
 * thrown ConversionError.
 */
export declare class ConversionError extends Error {
    readonly primary: Diagnostic;
    readonly diagnostics: Diagnostic[];
    constructor(primary: Diagnostic, additional?: Diagnostic[]);
    /** True when at least one diagnostic is severity 'error'. */
    get hasErrors(): boolean;
}
/**
 * Mutable collector that dedupes diagnostics by (rule_id, element_id, message)
 * and exposes helpers to push standard families. Keeps api.ts terse.
 */
export declare class DiagnosticsCollector {
    private readonly items;
    private readonly seen;
    private key;
    push(d: Diagnostic): void;
    pushMany(ds: Diagnostic[]): void;
    add(ruleId: string, severity: DiagnosticSeverity, message: string, opts?: Partial<Diagnostic>): void;
    list(): readonly Diagnostic[];
    get count(): number;
    get errorCount(): number;
    get warningCount(): number;
    get infoCount(): number;
    toJSON(): Diagnostic[];
}
