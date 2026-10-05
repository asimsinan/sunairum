/**
 * Resource loading policy for Playwright and PPTX media validation (DH-P0-007).
 *
 * Caller controls network access and local file roots. Blocked, missing, and
 * escaped resources are reported as structured diagnostics instead of being
 * silently allowed or denied.
 */
import type { Page, Route } from 'playwright-core';
export type ResourcePolicyMode = 'local' | 'remote';
export interface DocumentUrlInfo {
    documentUrl: string;
    mode: ResourcePolicyMode;
}
/** Structured per-resource diagnostic. */
export interface ResourceDiagnostic {
    rule_id: string;
    severity: 'error' | 'warning' | 'info';
    url: string;
    message: string;
    recovery?: string;
}
/**
 * Caller-controlled resource policy.
 */
export interface ResourcePolicy {
    /** 'deny' blocks http://, https://, ws://, wss://. Default: 'allow' (backward compat). */
    network?: 'deny' | 'allow';
    /** Local file roots that file:// subresources may load from. Empty = only the document itself. */
    allowedRoots?: string[];
    /** When false, reject symlinks and '..' traversal. Default: false. */
    followSymlinks?: boolean;
    /** Allow remote fonts. Defaults to network policy. */
    allowRemoteFonts?: boolean;
    /** Allow remote images. Defaults to network policy. */
    allowRemoteImages?: boolean;
    /** Allow remote scripts. Defaults to network policy. */
    allowRemoteScripts?: boolean;
    /** Allow remote styles. Defaults to network policy. */
    allowRemoteStyles?: boolean;
}
export interface ResourcePolicyOptions {
    /** Legacy shorthand: when true, allow all file:// subresources (no route blocking). */
    allowLocalResources?: boolean;
    /** Explicit policy. When present, takes precedence over allowLocalResources. */
    policy?: ResourcePolicy;
    /** Diagnostics collector (pushed to by the route handler). */
    diagnostics?: ResourceDiagnostic[];
}
/**
 * Resolve how the HTML document will be loaded.
 */
export declare function resolveDocumentUrl(inputPath: string): DocumentUrlInfo;
/**
 * Normalize file:// URLs for stable comparison across platforms.
 */
export declare function normalizeFileUrl(url: string): string;
/**
 * Whether a subresource request should be allowed under the active policy.
 * Pushes a diagnostic for every denial.
 */
export declare function isResourceRequestAllowed(requestUrl: string, documentUrl: string, policy: Required<Pick<ResourcePolicy, 'network' | 'allowedRoots' | 'followSymlinks' | 'allowRemoteFonts' | 'allowRemoteImages' | 'allowRemoteScripts' | 'allowRemoteStyles'>>, diagnostics: ResourceDiagnostic[], kind: 'font' | 'image' | 'script' | 'style' | 'other'): boolean;
/**
 * Playwright route handler enforcing the resource policy.
 */
export declare function createPlaywrightRouteHandler(documentUrl: string, policy: Required<Pick<ResourcePolicy, 'network' | 'allowedRoots' | 'followSymlinks' | 'allowRemoteFonts' | 'allowRemoteImages' | 'allowRemoteScripts' | 'allowRemoteStyles'>>, diagnostics: ResourceDiagnostic[]): (route: Route) => Promise<void>;
/**
 * Register resource policy route on a Playwright page (call before goto).
 */
export declare function setupResourcePolicyOnPage(page: Page, inputPath: string, options?: ResourcePolicyOptions): Promise<DocumentUrlInfo>;
/**
 * Validate that a URL returns a valid image (not 404 HTML, etc.)
 */
export declare function validateImageUrl(url: string): Promise<boolean>;
export type ResolvedImageSource = {
    kind: 'data';
    data: string;
} | {
    kind: 'path';
    path: string;
};
/**
 * Resolve an image URL for pptxgenjs.
 * Keeps the original http:// or https:// URL (no protocol upgrade).
 * Call ensurePptxgenAllowsHttp() before write so pptxgenjs can fetch http://.
 */
export declare function resolveImageSourceForPptx(url: string): Promise<ResolvedImageSource | null>;
/**
 * Validate inline data:image/... URLs.
 */
export declare function validateDataImageUrl(dataUrl: string): boolean;
