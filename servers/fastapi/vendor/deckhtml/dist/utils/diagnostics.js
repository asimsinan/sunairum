"use strict";
/**
 * Structured conversion diagnostics (DH-P0-009).
 *
 * A Diagnostic is the stable, machine-readable form of every issue deckhtml
 * surfaces during a conversion. rule_id stays semantically stable across patch
 * versions so callers can branch on it.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.DiagnosticsCollector = exports.ConversionError = exports.RULE_IDS = void 0;
/** Minimum rule families deckhtml guarantees (DH-P0-009). */
exports.RULE_IDS = {
    IDENTITY_MISSING: 'DECKHTML_IDENTITY_MISSING',
    IDENTITY_DUPLICATE: 'DECKHTML_IDENTITY_DUPLICATE',
    IDENTITY_NOT_EXPORTED: 'DECKHTML_IDENTITY_NOT_EXPORTED',
    KIND_AMBIGUOUS: 'DECKHTML_KIND_AMBIGUOUS',
    KIND_UNSUPPORTED: 'DECKHTML_KIND_UNSUPPORTED',
    STYLE_UNSUPPORTED: 'DECKHTML_STYLE_UNSUPPORTED',
    RESOURCE_REMOTE_BLOCKED: 'DECKHTML_REMOTE_RESOURCE_BLOCKED',
    RESOURCE_MISSING: 'DECKHTML_RESOURCE_MISSING',
    RESOURCE_ESCAPED: 'DECKHTML_RESOURCE_ESCAPED',
    BROWSER_UNAVAILABLE: 'DECKHTML_BROWSER_UNAVAILABLE',
    BROWSER_CRASHED: 'DECKHTML_BROWSER_CRASHED',
    BROWSER_TIMEOUT: 'DECKHTML_BROWSER_TIMEOUT',
    FONT_MISSING: 'DECKHTML_FONT_MISSING',
    FONT_FALLBACK: 'DECKHTML_FONT_FALLBACK',
    RASTER_FALLBACK: 'DECKHTML_RASTER_FALLBACK',
    GEOMETRY_INVALID: 'DECKHTML_GEOMETRY_INVALID',
    GEOMETRY_UNSTABLE: 'DECKHTML_GEOMETRY_UNSTABLE',
    OOXML_WRITE_FAILURE: 'DECKHTML_OOXML_WRITE_FAILURE',
    OOXML_REOPEN_FAILURE: 'DECKHTML_OOXML_REOPEN_FAILURE',
    MAPPING_CLOSURE_FAILURE: 'DECKHTML_MAPPING_CLOSURE_FAILURE',
    OUTPUT_EXISTS: 'DECKHTML_OUTPUT_EXISTS',
    ANIMATION_UNMAPPED: 'DECKHTML_ANIMATION_UNMAPPED',
    IFRAME_INSPECT_FAILED: 'DECKHTML_IFRAME_INSPECT_FAILED',
    IFRAME_NESTED_TOO_DEEP: 'DECKHTML_IFRAME_NESTED_TOO_DEEP',
    IFRAME_PARENT_COUPLED: 'DECKHTML_IFRAME_PARENT_COUPLED',
    LAYOUT_FAITHFUL_UNSUPPORTED: 'DECKHTML_LAYOUT_FAITHFUL_UNSUPPORTED',
    LAYOUT_FAITHFUL_FONT: 'DECKHTML_LAYOUT_FAITHFUL_FONT',
    LAYOUT_FAITHFUL_FALLBACK: 'DECKHTML_LAYOUT_FAITHFUL_FALLBACK',
    LAYOUT_FAITHFUL_SHRINK: 'DECKHTML_LAYOUT_FAITHFUL_SHRINK',
};
/**
 * Error thrown for hard failures. Carries a primary Diagnostic plus optional
 * additional diagnostics so callers can still harvest structured info from a
 * thrown ConversionError.
 */
class ConversionError extends Error {
    constructor(primary, additional = []) {
        super(primary.message);
        this.name = 'ConversionError';
        this.primary = primary;
        this.diagnostics = [primary, ...additional];
    }
    /** True when at least one diagnostic is severity 'error'. */
    get hasErrors() {
        return this.diagnostics.some((d) => d.severity === 'error');
    }
}
exports.ConversionError = ConversionError;
/**
 * Mutable collector that dedupes diagnostics by (rule_id, element_id, message)
 * and exposes helpers to push standard families. Keeps api.ts terse.
 */
class DiagnosticsCollector {
    constructor() {
        this.items = [];
        this.seen = new Set();
    }
    key(d) {
        return `${d.rule_id}|${d.element_id ?? ''}|${d.slide_id ?? ''}|${d.message}`;
    }
    push(d) {
        const k = this.key(d);
        if (this.seen.has(k))
            return;
        this.seen.add(k);
        this.items.push(d);
    }
    pushMany(ds) {
        for (const d of ds)
            this.push(d);
    }
    add(ruleId, severity, message, opts = {}) {
        this.push({ rule_id: ruleId, severity, message, ...opts });
    }
    list() {
        return this.items;
    }
    get count() {
        return this.items.length;
    }
    get errorCount() {
        return this.items.filter((d) => d.severity === 'error').length;
    }
    get warningCount() {
        return this.items.filter((d) => d.severity === 'warning').length;
    }
    get infoCount() {
        return this.items.filter((d) => d.severity === 'info').length;
    }
    toJSON() {
        return this.items.slice();
    }
}
exports.DiagnosticsCollector = DiagnosticsCollector;
