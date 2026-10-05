import { AnimationConversionOptions, AnimationTrigger, ElementAnimation, NormalizedAnimationEffect } from '../types';
/** Parsed first/last keyframe geometry, produced browser-side. */
export interface KeyframeSnapshot {
    opacity: number | null;
    translateXPx: number;
    translateYPx: number;
    scaleX: number;
    scaleY: number;
    rotateDeg: number;
    /** Frame touched properties outside opacity/transform (e.g. color, width). */
    hasNonMotionProps: boolean;
}
/** Raw CSS animation capture for one element (browser-side). */
export interface CssAnimationRaw {
    name: string;
    durationMs: number;
    delayMs: number;
    /** null = infinite */
    iterationCount: number | null;
    first: KeyframeSnapshot;
    last: KeyframeSnapshot;
}
/** Intercepted anime.js animate()/timeline.add() call (browser-side). */
export interface AnimeCallRaw {
    durationMs?: number;
    delayMs?: number;
    /** Unknown easing/delay shapes are captured verbatim for diagnostics. */
    staggered?: boolean;
    params: Record<string, unknown>;
}
/** Parse "600" | "600ms" | "0.6s" into milliseconds. */
export declare function parseTimeMs(raw: string | undefined | null): number | undefined;
/** Map declared trigger words onto PPTX triggers; undefined when absent/unknown. */
export declare function normalizeTrigger(raw: string | undefined | null): AnimationTrigger | undefined;
/** Normalize a declared `data-animation` effect string. */
export declare function normalizeDeclaredEffect(raw: string): NormalizedAnimationEffect;
/**
 * Infer the entrance effect from first/last @keyframes frames.
 * Returns 0..2 effects: fade combined with a single-axis motion is emitted as
 * two entries played in parallel; anything more complex is `unmapped`.
 */
export declare function normalizeCssAnimation(raw: CssAnimationRaw): NormalizedAnimationEffect[];
/** Infer effects from one intercepted anime.js call. */
export declare function normalizeAnimeParams(call: AnimeCallRaw): NormalizedAnimationEffect[];
export interface BuildAnimationsInput {
    declared?: {
        effect: string;
        durationMs?: number;
        delayMs?: number;
        trigger?: string;
    };
    css?: CssAnimationRaw;
    animeCalls?: AnimeCallRaw[];
    options?: AnimationConversionOptions;
}
export interface BuiltAnimations {
    animations: ElementAnimation[];
    /** One entry per source animation that could not be mapped. */
    unmapped: {
        source: ElementAnimation['source'];
        raw: string;
        reason: string;
    }[];
}
/**
 * Merge all capture sources for one element into a single animation list.
 * An explicit declaration wins over css/animejs captures for the same element
 * (authors use it to override ambient animations).
 */
export declare function buildElementAnimations(input: BuildAnimationsInput): BuiltAnimations;
/** True when the snapshot carries no motion (used to skip trivial captures). */
export declare function isTrivialKeyframes(first: KeyframeSnapshot, last: KeyframeSnapshot): boolean;
