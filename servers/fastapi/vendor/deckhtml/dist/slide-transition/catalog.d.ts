/**
 * PowerPoint slide-to-slide transition catalog (OOXML `p:transition`).
 *
 * These are transitions between slides — not element entrance animations
 * (`data-animation` / `p:timing`).
 *
 * Three tiers, mirroring what PowerPoint itself writes:
 *
 * - **base** — ISO/IEC 29500 `p:*` child elements (`p:fade`, `p:push`, …).
 *   Understood by every OOXML renderer.
 * - **ext** — Office extension transitions, wrapped in `mc:AlternateContent`
 *   with a base `mc:Fallback`:
 *   - `p14:*` (PowerPoint 2010) — vortex, flip, ripple, glitter, …
 *   - `p15:prstTrans` (PowerPoint 2013) — preset transitions: fallOver,
 *     drape, curtains, wind, prestige, fracture, crush, peelOff,
 *     pageCurlSingle/Double, airplane, origami
 *   - `p159:morph` (PowerPoint 2019 / Microsoft 365)
 *
 * Renderers without the extension play the base fallback instead.
 */
export type TransitionSpeed = 'slow' | 'med' | 'fast';
export type SideDirection = 'l' | 'r' | 'u' | 'd';
export type CornerDirection = 'ld' | 'lu' | 'rd' | 'ru';
export type EightDirection = SideDirection | CornerDirection;
export type LeftRight = 'l' | 'r';
export type Orient = 'horz' | 'vert';
export type InOut = 'in' | 'out';
export type CornerOrCenter = CornerDirection | 'center';
export type GlitterPattern = 'diamond' | 'hexagon';
export type ShredPattern = 'strip' | 'rectangle';
export type MorphOption = 'byObject' | 'byWord' | 'byChar';
/** Extension namespace for `tier: 'ext'` effects. */
export type TransitionExtNamespace = 'p14' | 'p15' | 'p159';
export declare const TRANSITION_EXT_NS_URIS: Record<TransitionExtNamespace, string>;
export interface TransitionFallbackSpec {
    /** Base catalog effect name used in `mc:Fallback`. */
    effect: string;
    params?: Partial<ResolvedTransitionParams>;
}
export interface SlideTransitionEffectDef {
    /** User-facing name (CLI / API). */
    name: string;
    /** Short description. */
    description: string;
    /** OOXML child element local name under `p:transition`. */
    ooxml: string;
    /**
     * `base` (default): plain `<p:xxx/>` child.
     * `ext`: `<ns:xxx/>` inside `mc:AlternateContent` with a base fallback.
     */
    tier?: 'base' | 'ext';
    /** Extension namespace prefix (required when tier is `ext`). */
    ns?: TransitionExtNamespace;
    /** Build attribute string for the OOXML child (may be empty). */
    attrs?: (opts: ResolvedTransitionParams) => string;
    /** Base fallback for ext effects (renderer without the extension). */
    fallback?: (opts: ResolvedTransitionParams) => TransitionFallbackSpec;
    /** Eligible for generation-time random pick (excludes meta `random`). */
    randomPool?: boolean;
}
export interface ResolvedTransitionParams {
    speed: TransitionSpeed;
    /** Side / corner / in-out / left-right / center direction resolved for this effect. */
    dir?: string;
    orient?: Orient;
    thruBlk?: boolean;
    spokes?: number;
    /** glitter / shred shape pattern. */
    pattern?: string;
    /** morph option: byObject / byWord / byChar. */
    option?: string;
    isContent?: boolean;
    isInverted?: boolean;
    hasBounce?: boolean;
    invX?: boolean;
    invY?: boolean;
}
export interface ResolvedSlideTransition {
    effect: string;
    speed: TransitionSpeed;
    params: ResolvedTransitionParams;
    /** Serialized OOXML fragment: `<p:transition …>…</p:transition>` (base) or
     *  `<mc:AlternateContent>…</mc:AlternateContent>` (ext). */
    xml: string;
}
/** Canonical catalog of slide transition effects. */
export declare const SLIDE_TRANSITION_EFFECTS: readonly SlideTransitionEffectDef[];
/** All user-facing effect names (stable order). */
export declare function listSlideTransitionEffectNames(): string[];
/** Effect names of one tier (`base` = ISO; `ext` = Office extensions). */
export declare function listSlideTransitionEffectNamesByTier(tier: 'base' | 'ext'): string[];
export declare function getSlideTransitionEffect(name: string): SlideTransitionEffectDef | undefined;
export declare function isSlideTransitionEffectName(name: string): boolean;
/** Effects eligible when generation-time random is requested. */
export declare function listRandomPoolEffects(): SlideTransitionEffectDef[];
export interface BuildTransitionXmlOptions {
    speed?: TransitionSpeed;
    /** Override direction / orient / etc. after resolve. */
    params?: Partial<ResolvedTransitionParams>;
}
/** Build the transition OOXML fragment for a catalog effect. */
export declare function buildTransitionXml(effect: SlideTransitionEffectDef, options?: BuildTransitionXmlOptions): string;
/**
 * Fill in directional / orient params for effects that need them.
 * Uses `pick` so callers can inject a seeded RNG.
 */
export declare function resolveEffectParams(effect: SlideTransitionEffectDef, pick: <T>(items: readonly T[]) => T, overrides?: Partial<ResolvedTransitionParams>): ResolvedTransitionParams;
